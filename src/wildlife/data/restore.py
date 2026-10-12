"""Restoring a backup.

A database can't be swapped while it's open, so restoring has two halves:

1. `request_restore()` (while WildLife runs): checks the backup thoroughly, then
   leaves a note in the data folder saying which backup to restore.
2. `apply_pending_restore()` (when WildLife next starts, before anything opens the
   database): makes a safety copy of the current data, puts the backup in place,
   brings back any photo files the library is missing from the backup's photo
   mirror, and removes the note. If anything goes wrong, the current data stays.
"""

from __future__ import annotations

import contextlib
import json
import logging
import shutil
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from wildlife.config.paths import DataPaths
from wildlife.data import snapshot
from wildlife.data.migrate import available_migrations
from wildlife.domain.errors import BackupError

log = logging.getLogger(__name__)
NOTE = "restore-pending.json"
# Where backups go, written beside the data on every backup: the setting itself is in the
# database, which can't be read if the database is what's damaged.
POINTER = "backup-location.txt"


@dataclass(frozen=True, slots=True)
class BackupInfo:
    path: Path
    created: datetime  # UTC
    kind: str  # auto | manual | exit | ...
    sightings: int
    photos: int
    schema_version: int | None


@dataclass(frozen=True, slots=True)
class RestoreOutcome:
    ok: bool
    message: str
    created: datetime | None = None  # when the restored backup was made
    photos_copied: int = 0
    safety_copy: Path | None = None


def describe(path: Path) -> BackupInfo:
    """What a snapshot holds, from its manifest (or the file itself if there's none)."""
    manifest = path.with_suffix(".json")
    meta: dict = {}
    if manifest.exists():
        try:
            meta = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            meta = {}
    try:
        created = datetime.fromisoformat(meta["created_utc"])
    except (KeyError, ValueError):
        created = datetime.fromtimestamp(path.stat().st_mtime, UTC)
    counts = meta.get("counts", {})
    return BackupInfo(
        path,
        created,
        meta.get("kind") or path.stem.rsplit("_", 1)[-1],
        counts.get("sighting", 0),
        meta.get("photos_in_library", counts.get("photo", 0)),
        meta.get("schema_version"),
    )


def check(path: Path) -> snapshot.Verification:
    """Raise BackupError (in plain words) unless `path` is a sound WildLife backup this
    version of WildLife can open."""
    if not path.exists():
        raise BackupError("That backup file isn't there any more. Is the drive connected?")
    try:
        result = snapshot.verify(path)
        conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
        try:
            version = conn.execute("PRAGMA user_version").fetchone()[0]
            has_sightings = conn.execute(
                "SELECT 1 FROM sqlite_schema WHERE type = 'table' AND name = 'sighting'"
            ).fetchone()
        finally:
            conn.close()
    except sqlite3.Error as exc:
        raise BackupError("That file isn't a WildLife backup.", detail=str(exc)) from exc
    if not has_sightings:
        raise BackupError("That file isn't a WildLife backup.")
    if not result.ok:
        raise BackupError(
            "That backup failed its check, so it can't be restored. Try an older one.",
            detail=str(result),
        )
    if version > available_migrations()[-1].version:
        raise BackupError("That backup was made by a newer version of WildLife. Update first.")
    return result


def remember_backup_folder(paths: DataPaths, folder: Path) -> None:
    (paths.root / POINTER).write_text(str(folder), encoding="utf-8")


def latest_backup(paths: DataPaths) -> BackupInfo | None:
    """The newest backup that passes its check, from the remembered backup folder and
    the default one. Used when the data file can't be opened at start-up."""
    folders = [paths.root / "backups"]
    with contextlib.suppress(OSError):  # no backup has been made since this was added
        folders.insert(0, Path((paths.root / POINTER).read_text(encoding="utf-8").strip()))
    snaps = []
    for folder in dict.fromkeys(folders):
        snapshots = folder / "snapshots"
        if snapshots.is_dir():
            snaps += [describe(p) for p in snapshots.glob("*.db")]
    for info in sorted(snaps, key=lambda i: i.created, reverse=True):
        try:
            check(info.path)
        except BackupError:
            continue
        return info
    return None


def request_restore(paths: DataPaths, backup: Path) -> BackupInfo:
    """Check the backup, then note it to be restored when WildLife next starts."""
    check(backup)
    note = {"backup": str(backup), "requested_utc": datetime.now(UTC).isoformat()}
    (paths.root / NOTE).write_text(json.dumps(note, indent=2), encoding="utf-8")
    log.info("Restore requested: %s", backup)
    return describe(backup)


def cancel_restore(paths: DataPaths) -> None:
    (paths.root / NOTE).unlink(missing_ok=True)


def pending(paths: DataPaths) -> Path | None:
    note = paths.root / NOTE
    if not note.exists():
        return None
    try:
        return Path(json.loads(note.read_text(encoding="utf-8"))["backup"])
    except (OSError, ValueError, KeyError):
        return None


def apply_pending_restore(paths: DataPaths) -> RestoreOutcome | None:
    """Run a requested restore. Call before anything opens the database."""
    if not (paths.root / NOTE).exists():
        return None
    backup = pending(paths)
    cancel_restore(paths)  # whatever happens next, don't try again on every start
    if backup is None:
        return RestoreOutcome(False, "The restore note was unreadable, so nothing was changed.")
    try:
        check(backup)
        safety = _safety_copy(paths)
        staged = paths.database.with_name(paths.database.name + ".restoring")
        shutil.copyfile(backup, staged)
        if not snapshot.verify(staged).ok:
            staged.unlink(missing_ok=True)
            raise BackupError("The copied backup failed its check, so nothing was changed.")
        for leftover in ("-wal", "-shm"):  # belong to the old database: must not be replayed
            Path(str(paths.database) + leftover).unlink(missing_ok=True)
        staged.replace(paths.database)
    except (BackupError, OSError) as exc:
        message = (
            exc.user_message
            if isinstance(exc, BackupError)
            else ("The backup couldn't be copied in, so your data is as it was.")
        )
        log.exception("Restore failed")
        return RestoreOutcome(False, message)
    copied = _bring_back_photos(paths, backup.parent.parent / "photos")
    info = describe(backup)
    log.info("Restored %s (%d photo files brought back)", backup, copied)
    return RestoreOutcome(
        True,
        "Backup restored",
        created=info.created,
        photos_copied=copied,
        safety_copy=safety,
    )


def _safety_copy(paths: DataPaths) -> Path | None:
    """A consistent copy of the current data (WAL included), kept in safety-copies."""
    if not paths.database.exists():
        return None
    dest = paths.internal_backups / snapshot.timestamped_name("before-restore")
    conn = sqlite3.connect(paths.database)
    try:
        snapshot.take_snapshot(conn, dest)
    finally:
        conn.close()
    if not snapshot.verify(dest).ok:
        raise BackupError(
            "Couldn't make a safety copy of your current data, so nothing was changed."
        )
    return dest


def _bring_back_photos(paths: DataPaths, mirror: Path) -> int:
    """Copy photo files the restored data needs, and the library lacks, from the mirror."""
    conn = sqlite3.connect(f"file:{paths.database.as_posix()}?mode=ro", uri=True)
    try:
        rels = [
            r[0]
            for r in conn.execute(
                "SELECT rel_path FROM photo UNION SELECT raw_rel_path FROM photo WHERE raw_rel_path IS NOT NULL"
            )
        ]
    finally:
        conn.close()
    copied = 0
    for rel in rels:
        dest = paths.root / rel
        source = mirror / rel.removeprefix("photos/")
        if dest.exists() or not source.exists() or ".." in Path(rel).parts:
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        shutil.copy2(source, tmp)
        tmp.replace(dest)
        copied += 1
    return copied
