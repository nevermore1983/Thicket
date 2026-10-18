"""The health check: is everything where it should be?

It looks at the data file, every photo file, the photo folder, the thumbnail cache,
backups and the species list, and reports each in plain words, with a fix where
Thicket can make one safely (e.g. bringing lost photo files back from the backup).
It never deletes your photos: files it doesn't recognise are only reported.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from wildlife.config.paths import DataPaths
from wildlife.data.db import Database
from wildlife.data.files import copy_atomically, is_stale_part, remove_stale_parts
from wildlife.data.repositories import photos as photos_repo
from wildlife.services.backup import BackupService
from wildlife.services.species_catalogue import SpeciesCatalogue

log = logging.getLogger(__name__)
OK, WARNING, PROBLEM = "ok", "warning", "problem"
Progress = Callable[[int, int], None]


@dataclass(frozen=True, slots=True)
class Finding:
    level: str  # OK, WARNING or PROBLEM
    title: str
    detail: str = ""
    action: str | None = None  # a fix the UI can offer (see HealthService.fix)
    action_label: str = ""
    items: tuple[str, ...] = ()  # e.g. the files concerned (first few)


@dataclass
class HealthReport:
    findings: list[Finding] = field(default_factory=list)
    seconds: float = 0.0

    @property
    def worst(self) -> str:
        levels = {f.level for f in self.findings}
        return PROBLEM if PROBLEM in levels else WARNING if WARNING in levels else OK


def _n(n: int, one: str, many: str) -> str:
    """'1 photo file is' / '3 photo files are': counts that read naturally."""
    return f"{n:,} {one if n == 1 else many}"


def _size_text(n: int) -> str:
    if n >= 1e9:
        return f"{n / 1e9:.1f} GB"
    return f"{n / 1e6:.0f} MB" if n >= 1e6 else f"{max(n // 1000, 1) if n else 0} KB"


class HealthService:
    def __init__(
        self,
        paths: DataPaths,
        db: Database,
        backup: BackupService,
        catalogue: SpeciesCatalogue,
    ) -> None:
        self._paths, self._db, self._backup, self._catalogue = paths, db, backup, catalogue

    def check(self, progress: Progress = lambda d, t: None) -> HealthReport:
        started = datetime.now(UTC)
        report = HealthReport()
        report.findings.append(self._database())
        report.findings += self._photos(progress)
        report.findings.append(self._thumbnails())
        report.findings += self._backups()
        report.findings.append(self._species_list())
        report.seconds = (datetime.now(UTC) - started).total_seconds()
        log.info("Health check: %s in %.1f s", report.worst, report.seconds)
        return report

    # ---- the checks ----------------------------------------------------------------------
    def _database(self) -> Finding:
        with self._db.connection() as conn:
            integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
            keys = conn.execute("PRAGMA foreign_key_check").fetchall()
        if integrity == "ok" and not keys:
            return Finding(OK, "Your data file is sound", "Integrity and link checks passed.")
        return Finding(
            PROBLEM,
            "Your data file has errors",
            "Restore your most recent backup (Settings › Backup › Restore). Your current "
            "data is kept as a safety copy when you do.",
            "restore",
            "Restore…",
            (integrity[:200],) if integrity != "ok" else (f"{len(keys)} broken links",),
        )

    def _photos(self, progress: Progress) -> list[Finding]:
        with self._db.connection() as conn:
            live = photos_repo.live(conn)
            known = {
                r[0]
                for r in conn.execute(
                    "SELECT rel_path FROM photo UNION SELECT raw_rel_path FROM photo "
                    "WHERE raw_rel_path IS NOT NULL"
                )
            }
        missing: list[str] = []
        changed: list[str] = []
        for i, p in enumerate(live):
            if i % 200 == 0:
                progress(i, len(live))
            path = self._paths.root / p.rel_path
            if not path.exists():
                missing.append(p.rel_path)
            elif path.stat().st_size != p.file_size:
                changed.append(p.original_name)
            if p.raw_rel_path and not (self._paths.root / p.raw_rel_path).exists():
                missing.append(p.raw_rel_path)
        progress(len(live), len(live))
        out: list[Finding] = []
        if missing:
            mirror = self._backup.folder() / "photos"
            recoverable = sum(
                1 for rel in missing if (mirror / rel.removeprefix("photos/")).exists()
            )
            out.append(
                Finding(
                    PROBLEM,
                    f"{_n(len(missing), 'photo file is', 'photo files are')} missing",
                    (
                        f"{recoverable:,} of them are in your backup and can be brought back."
                        if recoverable
                        else "They aren't in your backup either. If you moved them, put them "
                        "back in Thicket's photo folder."
                    ),
                    "restore_photos" if recoverable else "find_photos",
                    "Bring back from backup" if recoverable else "Look in a folder…",
                    tuple(missing[:20]),
                )
            )
        else:
            out.append(Finding(OK, f"Every photo file is in place ({len(live):,})"))
        if changed:
            out.append(
                Finding(
                    WARNING,
                    f"{_n(len(changed), 'photo file was', 'photo files were')} changed outside Thicket",
                    "Another program saved over them. Thicket still shows them; the "
                    "backup keeps the version you imported.",
                    items=tuple(changed[:20]),
                )
            )
        partial, unknown = [], []
        if self._paths.photos.exists():
            for f in self._paths.photos.rglob("*"):
                if not f.is_file():
                    continue
                rel = f.relative_to(self._paths.root).as_posix()
                if f.suffix == ".part":
                    if is_stale_part(f):  # a recent one is a copy still running
                        partial.append(rel)
                elif rel not in known:
                    unknown.append(rel)
        if partial:
            out.append(
                Finding(
                    WARNING,
                    f"{_n(len(partial), 'unfinished copy', 'unfinished copies')} in the photo folder",
                    "Left by an import that was interrupted. They aren't photos in your "
                    "library and can be removed.",
                    "remove_partial",
                    "Remove them",
                    tuple(partial[:20]),
                )
            )
        if unknown:
            out.append(
                Finding(
                    WARNING,
                    f"{_n(len(unknown), 'file', 'files')} in the photo folder "
                    f"{'isn' if len(unknown) == 1 else 'aren'}'t in your library",
                    "Thicket leaves them alone. To add them, import them from Photos › Import.",
                    "open_photos_folder",
                    "Open folder",
                    tuple(unknown[:20]),
                )
            )
        return out

    def _thumbnails(self) -> Finding:
        files = [f for f in self._paths.thumbnails.rglob("*") if f.is_file()]
        size = sum(f.stat().st_size for f in files)
        return Finding(
            OK,
            f"Thumbnails: {len(files):,} small pictures, {_size_text(size)}",
            "Made as needed. Clearing them frees the space; they're remade when shown.",
            "clear_thumbnails" if files else None,
            "Clear" if files else "",
        )

    def _backups(self) -> list[Finding]:
        last = self._backup.last_result()
        out: list[Finding] = []
        if last is None or not last.ok:
            out.append(
                Finding(
                    PROBLEM,
                    "No working backup" if last is None else "The last backup failed",
                    last.message if last else "Make one now.",
                    "backup_now",
                    "Back up now",
                )
            )
        else:
            age = datetime.now(UTC) - datetime.fromisoformat(last.when)
            if age > timedelta(days=7):
                out.append(
                    Finding(
                        WARNING,
                        f"The last backup was {age.days} days ago",
                        "",
                        "backup_now",
                        "Back up now",
                    )
                )
            else:
                out.append(Finding(OK, "Backups are up to date"))
        if self._backup.uses_default_folder():
            out.append(
                Finding(
                    WARNING,
                    "Backups are on the same drive as your data",
                    "If the drive fails, both are lost. Choose another drive or a "
                    "cloud-synced folder.",
                    "choose_backup_folder",
                    "Choose folder…",
                )
            )
        return out

    def _species_list(self) -> Finding:
        if self._catalogue.needs_install():
            return Finding(
                WARNING,
                "The species list needs updating",
                "Restart Thicket to install the newer list.",
            )
        return Finding(OK, f"Species list {self._catalogue.installed_version()} installed")

    # ---- fixes ---------------------------------------------------------------------------
    def bring_back_photos(self) -> int:
        """Copy missing photo files back from the backup's photo mirror."""
        mirror = self._backup.folder() / "photos"
        with self._db.connection() as conn:
            rels = photos_repo.all_rel_paths(conn)
        copied = 0
        for rel in rels:
            dest = self._paths.root / rel
            source = mirror / rel.removeprefix("photos/")
            if dest.exists() or not source.exists():
                continue
            copy_atomically(source, dest)
            copied += 1
        log.info("Health check: brought back %d photo files from the backup", copied)
        return copied

    def remove_partial(self) -> int:
        return remove_stale_parts(self._paths.photos, recursive=True)

    def clear_thumbnails(self) -> int:
        removed = 0
        for f in self._paths.thumbnails.rglob("*"):
            if f.is_file():
                f.unlink(missing_ok=True)
                removed += 1
        return removed
