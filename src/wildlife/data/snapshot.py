"""Consistent copies of the live database, and checking that a copy is sound.

Never copy the .db file with a normal file copy while the app is running: in
WAL mode recent changes may still be in the -wal file. SQLite's online backup
API produces a consistent snapshot instead.
"""

from __future__ import annotations

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
    """Write a consistent copy of `conn`'s database to `dest` (must not exist)."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise FileExistsError(dest)
    target = sqlite3.connect(dest)
    try:
        conn.backup(target)
        # One self-contained file: a WAL-mode copy would grow -wal/-shm side files
        # whenever it's opened (e.g. to verify it), and those would be left behind.
        target.execute("PRAGMA journal_mode = DELETE")
    finally:
        target.close()
    return dest


def remove(path: Path) -> None:
    """Delete a snapshot with its manifest and any side files."""
    for extra in ("", "-wal", "-shm"):
        Path(str(path) + extra).unlink(missing_ok=True)
    path.with_suffix(".json").unlink(missing_ok=True)


def verify(path: Path) -> Verification:
    """Open a copy read-only and check it thoroughly."""
    conn = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
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
