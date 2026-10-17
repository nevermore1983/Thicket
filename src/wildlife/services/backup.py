"""Automatic, verified backups.

Each backup is a consistent snapshot of the database (SQLite's backup API) plus
a mirror of the photo library. Photos never change once stored, so the mirror
only ever copies new files. Snapshots are kept on a rotating schedule:
the newest per day for 7 days, per week for 4 weeks, per month for 12 months,
plus every manual backup.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import threading
import time
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path

from wildlife import __version__
from wildlife.config.paths import DataPaths
from wildlife.data import restore, snapshot
from wildlife.data.db import Database
from wildlife.data.files import copy_atomically, remove_stale_parts
from wildlife.data.migrate import current_version
from wildlife.data.repositories import photos as photos_repo
from wildlife.data.repositories import taxa as meta_repo
from wildlife.domain.errors import BackupError
from wildlife.services.events import EventHub
from wildlife.services.settings import SettingsService

log = logging.getLogger(__name__)
KEEP_DAILY, KEEP_WEEKLY, KEEP_MONTHLY = 7, 4, 12
# "2026-10-11_093012_auto.db", or "2026-10-11_093012-2_manual.db" for a second one that
# second. Any other .db file in the folder isn't one of WildLife's backups: left alone.
SNAPSHOT_NAME = re.compile(r"^\d{4}-\d{2}-\d{2}_\d{6}(-\d+)?_[a-z]+$")
# A photo in the library (and its backup copy) is named by its content hash
LIBRARY_FILE = re.compile(r"^[0-9a-f]{64}\.[a-z0-9]+$")


@dataclass(frozen=True, slots=True)
class BackupResult:
    when: str  # UTC ISO time
    kind: str  # auto | manual | exit
    ok: bool
    snapshot: str
    sightings: int
    photos_copied: int
    seconds: float
    message: str


class BackupService:
    def __init__(
        self, paths: DataPaths, db: Database, events: EventHub, settings: SettingsService
    ) -> None:
        self._paths, self._db, self._events, self._settings = paths, db, events, settings
        self._changed_since_backup = False
        self._lock = threading.Lock()
        events.subscribe(self._on_change)

    def _on_change(self, event) -> None:
        if event.topic in ("sightings", "places", "photos", "taxa"):
            self._changed_since_backup = True

    # ---- where ---------------------------------------------------------------
    def folder(self) -> Path:
        chosen = self._settings.current.backup_folder
        return Path(chosen) / "WildLife Backups" if chosen else self._paths.root / "backups"

    def uses_default_folder(self) -> bool:
        return not self._settings.current.backup_folder

    # ---- status --------------------------------------------------------------
    def last_result(self) -> BackupResult | None:
        with self._db.connection() as conn:
            raw = meta_repo.get_meta(conn, "last_backup")
        return BackupResult(**json.loads(raw)) if raw else None

    def is_due(self, now: datetime | None = None) -> bool:
        if not self._settings.current.auto_backup:
            return False
        last = self.last_result()
        if last is None or not last.ok:
            return True
        now = now or datetime.now(UTC)
        return now - datetime.fromisoformat(last.when) > timedelta(hours=24)

    def needed_on_exit(self) -> bool:
        return self._settings.current.auto_backup and self._changed_since_backup

    # ---- doing it -------------------------------------------------------------
    def backup_now(self, kind: str = "manual") -> BackupResult:
        """Back up now. One backup runs at a time: a second request (the start-up
        backup, "Back up now", the backup on exit) waits for the first to finish."""
        with self._lock:
            # Cleared before the snapshot, so a change saved while this backup runs
            # still counts as "not backed up yet" (it's after the snapshot)
            changed, self._changed_since_backup = self._changed_since_backup, False
            try:
                return self._backup_now(kind)
            except BaseException:
                self._changed_since_backup |= changed  # nothing was backed up after all
                raise

    def _backup_now(self, kind: str) -> BackupResult:
        started = time.perf_counter()
        when = datetime.now(UTC)
        root = self.folder()
        try:
            (root / "snapshots").mkdir(parents=True, exist_ok=True)
            probe = root / ".write-test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
        except OSError as exc:
            result = self._record(
                BackupResult(
                    when.isoformat(),
                    kind,
                    False,
                    "",
                    0,
                    0,
                    time.perf_counter() - started,
                    f"The backup folder isn't available ({root}). Is the drive connected?",
                )
            )
            raise BackupError(result.message, detail=str(exc)) from exc

        stamp, n = when.strftime("%Y-%m-%d_%H%M%S"), 1
        name = f"{stamp}_{kind}"
        while (root / "snapshots" / f"{name}.db").exists():  # two backups within one second
            n += 1
            name = f"{stamp}-{n}_{kind}"
        target = root / "snapshots" / f"{name}.db"
        try:
            with self._db.connection() as conn:
                snapshot.take_snapshot(conn, target)
                schema = current_version(conn)
                rel_paths = photos_repo.all_rel_paths(conn)
            check = snapshot.verify(target)
            if not check.ok:
                target.unlink(missing_ok=True)
                raise BackupError(
                    "The backup copy failed its check, so it was discarded. Your data is fine.",
                    detail=str(check),
                )
            copied = self._mirror_photos(root / "photos", rel_paths)
            manifest = {
                "app_version": __version__,
                "schema_version": schema,
                "created_utc": when.isoformat(),
                "kind": kind,
                "integrity": check.integrity,
                "counts": check.counts,
                "photos_in_library": len(rel_paths),
            }
            (root / "snapshots" / f"{name}.json").write_text(
                json.dumps(manifest, indent=2), encoding="utf-8"
            )
            self._rotate(root / "snapshots")
            self._prune_mirror(root, rel_paths)
        except BackupError as exc:
            self._record(
                BackupResult(
                    when.isoformat(),
                    kind,
                    False,
                    "",
                    0,
                    0,
                    time.perf_counter() - started,
                    exc.user_message,
                )
            )
            raise
        except OSError as exc:
            result = self._record(
                BackupResult(
                    when.isoformat(),
                    kind,
                    False,
                    "",
                    0,
                    0,
                    time.perf_counter() - started,
                    "The backup couldn't be written. Check there is free space on the backup drive.",
                )
            )
            raise BackupError(result.message, detail=str(exc)) from exc
        try:
            restore.remember_backup_folder(self._paths, root)
        except OSError:
            log.warning("Couldn't note where backups are kept")
        result = BackupResult(
            when.isoformat(),
            kind,
            True,
            str(target),
            check.counts.get("sighting", 0),
            copied,
            round(time.perf_counter() - started, 2),
            "Backed up and verified",
        )
        log.info(
            "Backup %s: %s sightings, %s new photos, %.2f s",
            name,
            result.sightings,
            copied,
            result.seconds,
        )
        return self._record(result)

    def _record(self, result: BackupResult) -> BackupResult:
        with self._db.transaction() as conn:
            meta_repo.set_meta(conn, "last_backup", json.dumps(asdict(result)))
        self._events.publish("backup")
        return result

    def _mirror_photos(self, mirror: Path, rel_paths: list[str]) -> int:
        copied = 0
        for rel in rel_paths:
            source = self._paths.root / rel
            dest = mirror / rel.removeprefix("photos/")
            if dest.exists() or not source.exists():
                continue
            copy_atomically(source, dest)
            copied += 1
        return copied

    def _prune_mirror(self, root: Path, current: list[str]) -> int:
        """Remove photo copies from the backup that nothing needs any more: not your
        library, and not any backup still kept (so each one restores with all its
        photos). If any kept backup can't be read, nothing is removed this time."""
        needed = set(current)
        try:
            for snap in _snapshots_in(root / "snapshots"):
                needed |= snapshot.photo_paths(snap)
        except sqlite3.Error as exc:
            log.warning("Backup photo tidy-up skipped (a backup couldn't be read): %s", exc)
            return 0
        mirror, removed = root / "photos", 0
        for f in mirror.rglob("*") if mirror.exists() else []:
            if not (f.is_file() and LIBRARY_FILE.match(f.name)):
                continue  # only WildLife's own photo copies are ever removed
            if "photos/" + f.relative_to(mirror).as_posix() not in needed:
                try:
                    f.unlink()
                    removed += 1
                except OSError as exc:
                    log.info("Left backup copy %s: %s", f.name, exc)
        if removed:
            log.info("Backup: removed %d photo copies no kept backup needs", removed)
        return removed

    def _rotate(self, folder: Path) -> None:
        """Keep newest-per-day (7), per-week (4), per-month (12) automatic snapshots; all manual ones."""
        snaps = _snapshots_in(folder)
        keep: set[Path] = set()
        days: list[str] = []
        weeks: list[str] = []
        months: list[str] = []
        for snap in snaps:
            stamp, kind = (
                snap.stem.split("_")[0],
                snap.stem.rsplit("_", 1)[-1],
            )  # "2026-10-11_093012_auto"
            if kind == "manual":
                keep.add(snap)
                continue
            day = datetime.strptime(stamp, "%Y-%m-%d")
            buckets = (
                (days, stamp, KEEP_DAILY),
                (weeks, f"{day.isocalendar()[0]}-W{day.isocalendar()[1]}", KEEP_WEEKLY),
                (months, stamp[:7], KEEP_MONTHLY),
            )
            for seen, bucket, limit in buckets:
                if bucket not in seen and len(seen) < limit:
                    seen.append(bucket)
                    keep.add(snap)
        for snap in snaps:
            if snap not in keep:
                snapshot.remove(snap)
        remove_stale_parts(folder)  # snapshots interrupted before they finished
        remove_stale_parts(folder.parent / "photos", recursive=True)

    def snapshots(self) -> list[Path]:
        return _snapshots_in(self.folder() / "snapshots")

    # ---- restoring -------------------------------------------------------------------
    def backups(self) -> list[restore.BackupInfo]:
        """The backups in the backup folder, newest first."""
        return [restore.describe(p) for p in self.snapshots()]

    def request_restore(self, backup: Path) -> restore.BackupInfo:
        """Check `backup` and arrange for it to be restored when WildLife restarts."""
        return restore.request_restore(self._paths, backup)


def _snapshots_in(folder: Path) -> list[Path]:
    """WildLife's own backups in `folder`, newest first (their names start with a
    sortable timestamp). Other .db files there are someone else's: never touched."""
    if not folder.exists():
        return []
    return sorted((p for p in folder.glob("*.db") if SNAPSHOT_NAME.match(p.stem)), reverse=True)
