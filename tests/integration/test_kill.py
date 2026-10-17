"""Killing WildLife outright (the nearest a test gets to a power cut).

A separate process saves sightings (or makes backups) as fast as it can and reports
each one that finished. The test kills it at an arbitrary moment, then checks that the
data file is sound and everything reported as saved is there. Only the save in progress
may be lost.
"""

import random
import sqlite3
import subprocess
import sys
import textwrap
import time

import pytest

from helpers import MINI_CATALOGUE
from wildlife.context import AppContext
from wildlife.data.db import Database
from wildlife.data.repositories import taxa as taxa_repo
from wildlife.data.restore import check

WORKER = textwrap.dedent(
    """
    import sys
    from datetime import date
    from pathlib import Path
    from wildlife.config.paths import DataPaths
    from wildlife.context import AppContext
    from wildlife.domain.models import SightingDraft

    folder, job = Path(sys.argv[1]), sys.argv[2]
    ctx = AppContext.open(DataPaths(folder).ensure())
    with ctx.db.connection() as conn:
        robin = conn.execute(
            "SELECT id FROM taxon WHERE scientific_name = 'Erithacus rubecula'"
        ).fetchone()[0]
    n = 0
    while True:
        if job == "save":
            ctx.sightings.save(SightingDraft(robin, date(2026, 5, 3), notes="x" * 3000))
        else:
            ctx.backup.backup_now("manual")
        n += 1
        print(n, flush=True)
    """
)


@pytest.fixture
def library(paths):
    ctx = AppContext.open(paths)
    with ctx.db.transaction() as conn:
        taxa_repo.install_catalogue(conn, MINI_CATALOGUE)
    ctx.close()
    return paths


def run_and_kill(tmp_path, paths, job: str, after: int) -> int:
    """Start the worker, kill it once it has reported `after` (+ a random moment more),
    and return the last count it reported."""
    script = tmp_path / "worker.py"
    script.write_text(WORKER, encoding="utf-8")
    proc = subprocess.Popen(
        [sys.executable, str(script), str(paths.root), job],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
    )
    last = 0
    try:
        for line in proc.stdout:
            last = int(line)
            if last >= after:
                break
        time.sleep(random.uniform(0, 0.02))  # somewhere inside the next save or backup
    finally:
        proc.kill()  # TerminateProcess: no clean-up runs, like pulling the plug
        proc.wait(10)
        # it kept going until the kill: count what it reported in the meantime too
        last = max([last, *(int(x) for x in proc.stdout.read().split())])
        proc.stdout.close()
    return last


def opened_like_wildlife(path) -> Database:
    """Open the data as WildLife does: waiting a moment if the killed process (or a virus
    scanner looking at what it wrote) is still letting go of the file. If it never can,
    say exactly what SQLite reported."""
    try:
        return Database(path)
    except sqlite3.OperationalError as exc:
        pytest.fail(f"{exc} ({getattr(exc, 'sqlite_errorname', '?')}) after waiting")


@pytest.mark.parametrize("after", [5, 37, 120])
def test_killed_while_saving_loses_nothing_that_was_saved(library, tmp_path, after):
    reported = run_and_kill(tmp_path, library, "save", after)
    database = opened_like_wildlife(library.database)
    try:
        with database.connection() as conn:
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
            saved = conn.execute("SELECT COUNT(*) FROM sighting").fetchone()[0]
    finally:
        database.close()
    assert reported <= saved <= reported + 1  # at most the save in progress is missing
    AppContext.open(library).close()  # and WildLife opens it normally


@pytest.mark.parametrize("after", [1, 3])
def test_killed_while_backing_up_leaves_only_sound_backups(library, tmp_path, after):
    ctx = AppContext.open(library)
    ctx.close()
    run_and_kill(tmp_path, library, "backup", after)
    again = AppContext.open(library)
    try:
        for info in again.backup.backups():  # every backup offered is complete and sound
            check(info.path)
        again.backup.backup_now("manual")  # and backing up still works
        assert again.backup.last_result().ok
    finally:
        again.close()
