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
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from wildlife.domain.errors import DatabaseError

log = logging.getLogger(__name__)

PRAGMAS = (
    "PRAGMA foreign_keys = ON",  # off by default in SQLite, per connection
    "PRAGMA synchronous = FULL",  # survive power cuts, not just crashes
    "PRAGMA busy_timeout = 5000",  # wait up to 5 s for another writer
    "PRAGMA temp_store = MEMORY",
)


# Errors that can pass in a moment: another program (antivirus, a sync app, or a Thicket
# that has just crashed and is still letting go) holding the file. Opening tries again
# for a few seconds before giving up. Real damage ("not a database") is never retried.
TEMPORARY = {
    sqlite3.SQLITE_IOERR,
    sqlite3.SQLITE_BUSY,
    sqlite3.SQLITE_LOCKED,
    sqlite3.SQLITE_CANTOPEN,
}
OPEN_RETRY_S = 5.0


def is_temporary(exc: sqlite3.Error) -> bool:
    code = getattr(exc, "sqlite_errorcode", None)
    return code is not None and (code & 0xFF) in TEMPORARY  # low byte: the main error code


def connect(path: Path | str) -> sqlite3.Connection:
    """Open a configured connection. Creates the file if it doesn't exist."""
    # Each connection is only ever used by the thread that opened it (Database hands out
    # one per thread). check_same_thread=False only lets close() at shutdown, on the main
    # thread, close the background threads' connections too; otherwise they'd stay open.
    conn = sqlite3.connect(path, autocommit=True, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        for pragma in PRAGMAS:
            conn.execute(pragma)
    except BaseException:
        conn.close()  # a damaged file fails here: don't leave it open (and locked)
        raise
    return conn


class Database:
    """Hands out one connection per thread for a single database file."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self._local = threading.local()
        self._all: list[sqlite3.Connection] = []
        self._busy: dict[int, int] = {}  # id(connection) -> how many blocks are using it now
        self._lock = threading.Lock()
        give_up = time.monotonic() + OPEN_RETRY_S
        while True:
            try:
                with self.connection() as conn:
                    # WAL is stored in the file itself, so setting it once is enough.
                    mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()[0]
                    if mode.lower() != "wal":
                        log.warning("Could not enable WAL mode (got %s)", mode)
                return
            except sqlite3.OperationalError as exc:
                self.close()  # an open connection would keep the file locked
                if not is_temporary(exc) or time.monotonic() > give_up:
                    raise
                log.info("Data file not readable yet (%s): trying again", exc)
                time.sleep(0.25)
            except BaseException:
                self.close()  # an open connection would keep the file locked (e.g. for a restore)
                raise

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        """This thread's connection (opened on first use)."""
        conn = getattr(self._local, "conn", None)
        if conn is None:
            conn = connect(self.path)
            self._local.conn = conn
            with self._lock:
                self._all.append(conn)
        with self._lock:
            self._busy[id(conn)] = self._busy.get(id(conn), 0) + 1
        try:
            yield conn
        finally:
            with self._lock:
                self._busy[id(conn)] -= 1

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        """All-or-nothing: commits if the block succeeds, rolls back on any error."""
        with self.connection() as conn:
            if conn.in_transaction:
                raise RuntimeError("transaction() is not re-entrant; pass the connection down")
            conn.execute("BEGIN IMMEDIATE")  # take the write lock now, not halfway through
            try:
                yield conn
                conn.execute("COMMIT")
            except BaseException as exc:
                # With autocommit=True, conn.rollback() does nothing, so be explicit. A
                # failed COMMIT (e.g. the disk filled up) also leaves the transaction open.
                if conn.in_transaction:
                    conn.execute("ROLLBACK")
                if isinstance(exc, sqlite3.OperationalError) and "full" in str(exc).lower():
                    raise DatabaseError(
                        "Not enough disk space, so nothing was changed. Free some space on "
                        "the drive and try again.",
                        detail=str(exc),
                    ) from exc
                raise

    def close(self) -> None:
        """Close every thread's connection. One that another thread is using at this very
        moment is left alone: closing it under that thread would crash the program. (The
        app waits for background work before closing, so this is a last safeguard.)"""
        own = getattr(self._local, "conn", None)
        with self._lock:
            still_in_use = []
            for conn in self._all:
                if conn is not own and self._busy.get(id(conn), 0):
                    still_in_use.append(conn)
                    continue
                with contextlib.suppress(sqlite3.ProgrammingError):  # already closed
                    conn.close()
            if still_in_use:
                log.warning("%d connection(s) still in use at close; left open", len(still_in_use))
            self._all = still_in_use
        self._local = threading.local()
