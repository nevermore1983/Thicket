"""Failure injection: things going wrong at the worst moment must never lose data.

Each test breaks something on purpose (a full disk, a damaged file, an interrupted
backup or import) and checks that what was saved before is still there and sound.
Killing WildLife outright is in test_kill.py.
"""

import sqlite3
from datetime import date

import pytest

from helpers import TODAY, taxon_id
from wildlife.context import AppContext
from wildlife.data import snapshot
from wildlife.data.repositories import imports as imports_repo
from wildlife.domain.errors import DatabaseError
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import SightingDraft


def add(ctx, day=TODAY):
    return ctx.sightings.save(SightingDraft(taxon_id(ctx, "Erithacus rubecula"), day)).sighting


def total(ctx) -> int:
    return ctx.sightings.totals(SightingFilter())[0]


def test_a_full_disk_changes_nothing_and_says_so(ctx):
    add(ctx)
    with ctx.db.connection() as conn:
        pages = conn.execute("PRAGMA page_count").fetchone()[0]
        conn.execute(f"PRAGMA max_page_count = {pages}")  # the 'disk' is now full
    with pytest.raises(DatabaseError) as full:
        for _ in range(500):  # sooner or later a save needs a new page
            add(ctx)
    assert "Not enough disk space" in full.value.user_message
    with ctx.db.connection() as conn:
        assert not conn.in_transaction  # the failed save was rolled back
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        conn.execute("PRAGMA max_page_count = 1073741823")  # space freed
    before = total(ctx)
    add(ctx)
    assert total(ctx) == before + 1  # works again


def test_an_import_that_fails_part_way_adds_nothing(ctx, tmp_path, monkeypatch):
    from wildlife.domain.csv_import import guess_mapping

    sheet = tmp_path / "list.csv"
    sheet.write_text("Species,Date\n" + "Robin,03/05/2026\n" * 1 + "Red Fox,04/05/2026\n" * 5)
    table = ctx.spreadsheet.read(sheet)
    plan = ctx.spreadsheet.preview(table, guess_mapping(table.header))
    real_insert, calls = imports_repo.insert, []

    def failing_insert(*args, **kwargs):
        calls.append(1)
        if len(calls) == 2:
            raise OSError("the drive went away")
        return real_insert(*args, **kwargs)

    monkeypatch.setattr(imports_repo, "insert", failing_insert)
    with pytest.raises(OSError):
        ctx.spreadsheet.run(plan)
    assert total(ctx) == 0 and ctx.import_history.batches() == []  # all or nothing


def test_an_interrupted_backup_never_looks_like_a_backup(ctx):
    add(ctx)
    ctx.backup.backup_now("manual")
    folder = ctx.backup.folder() / "snapshots"

    class PulledOut:  # a connection whose drive disappears during the copy
        def backup(self, target, *args, **kwargs):
            raise sqlite3.OperationalError("disk I/O error")

    with pytest.raises(sqlite3.OperationalError):
        snapshot.take_snapshot(PulledOut(), folder / "2026-10-11_120000_manual.db")
    assert len(ctx.backup.backups()) == 1  # only the complete one is offered
    assert list(folder.glob("*.part"))  # the half-copy is still on the drive...
    ctx.backup.backup_now("manual")
    assert not list(folder.glob("*.part"))  # ...until the next backup tidies it away


def test_a_damaged_data_file_is_never_opened_quietly(paths):
    ctx = AppContext.open(paths)
    ctx.close()
    data = paths.database.read_bytes()
    for damage in (data[: len(data) // 3], b"\0" * 4096 + data[4096:], b"not a database" * 50):
        paths.database.write_bytes(damage)
        for side in ("-wal", "-shm"):
            paths.database.with_name(paths.database.name + side).unlink(missing_ok=True)
        with pytest.raises(DatabaseError) as refused:
            AppContext.open(paths).close()
        assert refused.value.user_message.endswith("You can restore it from a backup.")


def test_restore_keeps_changes_that_were_still_in_the_side_file(ctx, paths):
    """The newest changes live in the -wal file until SQLite folds them in. Restoring
    must save them in the safety copy before that file is removed."""
    from wildlife.data.restore import apply_pending_restore

    add(ctx, date(2026, 5, 1))
    ctx.backup.backup_now("manual")
    newest = add(ctx, date(2026, 6, 1))  # after the backup: only in the live data
    ctx.backup.request_restore(ctx.backup.backups()[0].path)
    ctx.close()
    outcome = apply_pending_restore(paths)
    safety = sqlite3.connect(outcome.safety_copy)
    try:
        uuids = {r[0] for r in safety.execute("SELECT uuid FROM sighting")}
    finally:
        safety.close()
    assert newest.uuid in uuids


def test_a_damaged_data_file_can_be_replaced_by_the_latest_backup(ctx, paths):
    """What 'Restore latest backup' does at start-up. A failed open once left the file
    locked, so the backup couldn't be put in its place."""
    from wildlife.data.restore import apply_pending_restore, latest_backup, request_restore

    add(ctx)
    ctx.backup.backup_now("manual")
    ctx.close()
    paths.database.write_bytes(b"\0" * 8192)  # damaged beyond opening
    with pytest.raises(DatabaseError):
        AppContext.open(paths)
    request_restore(paths, latest_backup(paths).path)
    assert apply_pending_restore(paths).ok
    again = AppContext.open(paths)
    try:
        assert total(again) == 1
    finally:
        again.close()
