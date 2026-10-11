"""Opening the SQLite database safely, and running transactions.

Rules (see docs/03-architecture.md, section 4.5):
  * one connection per thread (SQLite connections must not be shared);
  * `autocommit=True` so Python never opens transactions behind our back;
    we open them explicitly with `with db.transaction() as conn:`;
  * every connection gets foreign keys ON, full disk sync and a busy timeout.
"""

from __future__ import annotations

import contextlib
import logging
import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

log = logging.getLogger(__name__)

PRAGMAS = (
    "PRAGMA foreign_keys = ON",  # off by default in SQLite, per connection
    "PRAGMA synchronous = FULL",  # survive power cuts, not just crashes
    "PRAGMA busy_timeout = 5000",  # wait up to 5 s for another writer
    "PRAGMA temp_store = MEMORY",
)


def connect(path: Path | str) -> sqlite3.Connection:
    """Open a configured connection. Creates the file if it doesn't exist."""
    conn = sqlite3.connect(path, autocommit=True, check_same_thread=True)
    conn.row_factory = sqlite3.Row
    for pragma in PRAGMAS:
        conn.execute(pragma)
    return conn


class Database:
    """Hands out one connection per thread for a single database file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._local = threading.local()
        self._all: list[sqlite3.Connection] = []
        self._lock = threading.Lock()
        with self.connection() as conn:
            # WAL is stored in the file itself, so setting it once is enough.
            mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
            if mode.lower() != "wal":
                log.warning("Could not enable WAL mode (got %s)", mode)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """This thread's connection (opened on first use)."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = connect(self.path)
            self._local.conn = conn
            with self._lock:
                self._all.append(conn)
        yield conn

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """All-or-nothing: commits if the block succeeds, rolls back on any error."""
        with self.connection() as conn:
            if conn.in_transaction:
                raise RuntimeError("transaction() is not re-entrant; pass the connection down")
            conn.execute("BEGIN IMMEDIATE")  # take the write lock now, not halfway through
            try:
                yield conn
            except BaseException:
                # With autocommit=True, conn.rollback() does nothing, so be explicit.
                conn.execute("ROLLBACK")
                raise
            else:
                conn.execute("COMMIT")

    def close(self) -> None:
        with self._lock:
            for conn in self._all:
                with contextlib.suppress(sqlite3.ProgrammingError):  # already closed
                    conn.close()
            self._all.clear()
        self._local = threading.local()
