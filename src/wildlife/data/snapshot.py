"""Consistent copies of the live database, and checking that a copy is sound.

Never copy the .db file with a normal file copy while the app is running: in
WAL mode recent changes may still be in the -wal file. SQLite's online backup
API produces a consistent snapshot instead.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

TABLES = ("sighting", "taxon", "place", "outing", "photo", "sighting_photo", "category", "setting")


@dataclass(frozen=True, slots=True)
class Verification:
    ok: bool
    integrity: str
    foreign_key_problems: int
    counts: dict[str, int]


def take_snapshot(conn: sqlite3.Connection, dest: Path) -> Path:
    """Write a consistent copy of `conn`'s database to `dest` (must not exist).

    The copy is written under a temporary name and renamed only once it's complete,
    so a copy interrupted part way (app killed, drive pulled out) never looks like a
    backup."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise FileExistsError(dest)
    part = dest.with_name(dest.name + ".part")
    part.unlink(missing_ok=True)  # left by an earlier interrupted copy
    target = sqlite3.connect(part)
    try:
        conn.backup(target)
        # One self-contained file: a WAL-mode copy would grow -wal/-shm side files
        # whenever it's opened (e.g. to verify it), and those would be left behind.
        target.execute("PRAGMA journal_mode = DELETE")
    finally:
        target.close()
    os.replace(part, dest)
    return dest


def remove(path: Path) -> None:
    """Delete a snapshot with its manifest and any side files."""
    for extra in ("", "-wal", "-shm"):
        Path(str(path) + extra).unlink(missing_ok=True)
    path.with_suffix(".json").unlink(missing_ok=True)


def open_read_only(path: Path) -> sqlite3.Connection:
    """Open a database file without any chance of changing it. The file is named by a
    URI, so characters such as # and % in a folder name are encoded (as_uri): otherwise
    "Backups #2" would be read as "Backups " and the wrong file opened."""
    return sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)


def photo_paths(path: Path) -> set[str]:
    """Every photo file (RAW originals too) a backup's data refers to, as library paths
    ('photos/2026/05/<hash>.jpg'), recycle bin included: restoring it needs them all.
    Raises sqlite3.Error if the backup can't be read."""
    conn = open_read_only(path)
    try:
        return {
            r[0]
            for r in conn.execute(
                "SELECT rel_path FROM photo UNION "
                "SELECT raw_rel_path FROM photo WHERE raw_rel_path IS NOT NULL"
            )
        }
    finally:
        conn.close()


def verify(path: Path) -> Verification:
    """Open a copy read-only and check it thoroughly."""
    conn = open_read_only(path)
    try:
        integrity = conn.execute("PRAGMA integrity_check").fetchone()[0]
        fk = conn.execute("PRAGMA foreign_key_check").fetchall()
        existing = {r[0] for r in conn.execute("SELECT name FROM sqlite_schema WHERE type='table'")}
        counts = {
            t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in TABLES
            if t in existing
        }
    finally:
        conn.close()
    return Verification(integrity == "ok" and not fk, integrity, len(fk), counts)


def timestamped_name(label: str) -> str:
    return f"{datetime.now(UTC).strftime('%Y-%m-%d_%H%M%S')}_{label}.db"
