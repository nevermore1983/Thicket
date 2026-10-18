"""Bringing a database up to the latest schema.

Migrations are numbered SQL files in this package (0001_initial.sql, ...).
The database remembers its version in `PRAGMA user_version`. On startup we
apply every newer file, each in its own transaction, so a failure leaves the
database exactly as it was. Before touching a database that already holds
data, the caller-supplied `backup` function runs first.
"""

from __future__ import annotations

import logging
import re
import sqlite3
from collections.abc import Callable
from dataclasses import dataclass
from importlib import resources

from wildlife.domain.errors import DatabaseError

log = logging.getLogger(__name__)
_NAME = re.compile(r"^(\d{4})_[a-z0-9_]+\.sql$")


@dataclass(frozen=True, slots=True)
class Migration:
    version: int
    name: str
    sql: str


def available_migrations() -> list[Migration]:
    """All migration files shipped with the app, oldest first."""
    found = []
    for entry in resources.files("wildlife.data.migrations").iterdir():
        if m := _NAME.match(entry.name):
            found.append(Migration(int(m[1]), entry.name, entry.read_text(encoding="utf-8")))
    found.sort(key=lambda mig: mig.version)
    versions = [mig.version for mig in found]
    if versions != list(range(1, len(found) + 1)):
        raise RuntimeError(f"Migration numbers must be 1..n with no gaps, got {versions}")
    return found


def current_version(conn: sqlite3.Connection) -> int:
    return conn.execute("PRAGMA user_version").fetchone()[0]


def apply_migration(conn: sqlite3.Connection, migration: Migration) -> None:
    """Run one migration atomically and bump user_version."""
    script = (
        f"BEGIN IMMEDIATE;\n{migration.sql}\nPRAGMA user_version = {migration.version};\nCOMMIT;"
    )
    try:
        conn.executescript(script)
    except sqlite3.Error:
        if conn.in_transaction:
            conn.execute("ROLLBACK")  # autocommit connections ignore conn.rollback()
        raise


def migrate(
    conn: sqlite3.Connection,
    backup: Callable[[int, int], None] | None = None,
    migrations: list[Migration] | None = None,
) -> int:
    """Upgrade to the latest version. Returns the version now in use.

    `backup(from_version, to_version)` is called once before any change is made
    to a database that already has a schema.
    """
    migrations = migrations if migrations is not None else available_migrations()
    latest = migrations[-1].version if migrations else 0
    version = current_version(conn)
    if version > latest:
        raise DatabaseError(
            "This data was saved by a newer version of Thicket. Please update the app to open it.",
            detail=f"database version {version} > app version {latest}",
        )
    pending = [m for m in migrations if m.version > version]
    if not pending:
        return version
    if version > 0 and backup is not None:
        backup(version, latest)
    for migration in pending:
        log.info("Applying migration %s", migration.name)
        try:
            apply_migration(conn, migration)
        except sqlite3.Error as exc:
            raise DatabaseError(
                "Thicket couldn't upgrade your data. Nothing was changed, and a backup was "
                "made first.",
                detail=f"{migration.name}: {exc}",
            ) from exc
    problems = conn.execute("PRAGMA foreign_key_check").fetchall()
    if problems:
        raise DatabaseError(
            "The upgraded data failed a consistency check.", detail=str(problems[:5])
        )
    return latest
