"""The safety nets themselves: failing backups, the internet guard, error reporting,
the single-window rule and the log file."""

import logging
import sqlite3
import threading
import time
import urllib.error
from datetime import date

import pytest

from helpers import taxon_id
from wildlife.data import snapshot
from wildlife.domain.errors import BackupError, OnlineServiceError, ValidationError
from wildlife.domain.models import SightingDraft
from wildlife.services import online


def add(ctx):
    ctx.sightings.save(SightingDraft(taxon_id(ctx, "Erithacus rubecula"), date(2026, 5, 3)))


# ---- backups that go wrong ---------------------------------------------------------------
def test_a_backup_that_fails_its_check_is_discarded(ctx, monkeypatch):
    add(ctx)
    bad = snapshot.Verification(False, "page 3 is never used", 0, {})
    monkeypatch.setattr(snapshot, "verify", lambda path: bad)
    with pytest.raises(BackupError) as failed:
        ctx.backup.backup_now("manual")
    assert "discarded" in failed.value.user_message
    assert list((ctx.backup.folder() / "snapshots").glob("*.db")) == []
    assert ctx.backup.last_result().ok is False and ctx.backup.is_due()  # tried again later


def test_backups_run_one_at_a_time(ctx, monkeypatch):
    """The start-up backup, "Back up now" and the backup on exit can all be asked for at
    once. They used to run side by side and could spoil each other's files."""
    add(ctx)
    real, running, most = snapshot.take_snapshot, [0], [0]

    def slow(conn, target):
        running[0] += 1
        most[0] = max(most[0], running[0])
        time.sleep(0.2)  # long enough for the other requests to arrive meanwhile
        try:
            real(conn, target)
        finally:
            running[0] -= 1

    monkeypatch.setattr(snapshot, "take_snapshot", slow)
    results = []
    threads = [
        threading.Thread(target=lambda k=kind: results.append(ctx.backup.backup_now(k)))
        for kind in ("auto", "manual", "exit")
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert most[0] == 1
    assert len(results) == 3 and all(r.ok for r in results)
    assert len({r.snapshot for r in results}) == 3  # three separate, complete backups
    # The keep-rules then keep the manual one and the newest automatic one of the day
    kinds = sorted(b.kind for b in ctx.backup.backups())
    assert len(kinds) == 2 and "manual" in kinds  # (which automatic one is newest varies)


def test_other_files_in_the_backup_folder_are_left_alone(ctx):
    add(ctx)
    ctx.backup.backup_now("manual")
    mine = ctx.backup.folder() / "snapshots" / "my own copy.db"
    mine.write_bytes(b"something you saved here yourself")
    assert ctx.backup.backup_now("auto").ok  # it used to stop every backup
    assert mine.exists()
    assert all(b.path != mine for b in ctx.backup.backups())  # and isn't offered to restore


def test_a_change_made_while_a_backup_runs_is_backed_up_on_exit(ctx, monkeypatch):
    add(ctx)
    real = snapshot.take_snapshot

    def change_meanwhile(conn, target):
        real(conn, target)
        add(ctx)  # saved after the snapshot was taken, before the backup finished

    monkeypatch.setattr(snapshot, "take_snapshot", change_meanwhile)
    ctx.backup.backup_now("auto")
    assert ctx.backup.needed_on_exit()  # that sighting isn't in the backup yet


def test_a_full_backup_drive_is_explained(ctx, monkeypatch):
    add(ctx)
    from wildlife.services import backup as module

    def full(*args, **kwargs):
        raise OSError(28, "No space left on device")

    monkeypatch.setattr(module.BackupService, "_mirror_photos", full)
    with pytest.raises(BackupError) as failed:
        ctx.backup.backup_now("manual")
    assert "free space" in failed.value.user_message
    assert ctx.backup.last_result().ok is False


# ---- the internet guard ------------------------------------------------------------------
class FakeResponse:
    def __init__(self, data: bytes):
        self.data = data

    def read(self, n):
        return self.data[:n]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def test_fetch_refuses_hosts_not_on_the_list(monkeypatch):
    monkeypatch.setattr(online._opener, "open", lambda *a, **k: pytest.fail("no request"))
    with pytest.raises(OnlineServiceError) as err:
        online.fetch("https://example.com/x.jpg")
    assert "only connects" in err.value.user_message


def test_fetch_errors_are_explained(monkeypatch):
    url = "https://static.inaturalist.org/photos/1/original.jpg"

    def refused(*a, **k):
        raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)

    monkeypatch.setattr(online._opener, "open", refused)
    with pytest.raises(OnlineServiceError) as err:
        online.fetch(url)
    assert "403" in err.value.user_message

    def offline(*a, **k):
        raise urllib.error.URLError("getaddrinfo failed")

    monkeypatch.setattr(online._opener, "open", offline)
    with pytest.raises(OnlineServiceError) as err:
        online.fetch(url)
    assert "internet connection" in err.value.user_message

    monkeypatch.setattr(online._opener, "open", lambda *a, **k: FakeResponse(b"x" * 101))
    with pytest.raises(OnlineServiceError) as err:
        online.fetch(url, max_bytes=100)
    assert "larger than expected" in err.value.user_message
    monkeypatch.setattr(online._opener, "open", lambda *a, **k: FakeResponse(b"photo"))
    assert online.fetch(url) == b"photo"


def test_redirects_only_to_allowed_hosts():
    handler = online._AllowListRedirects()
    with pytest.raises(urllib.error.HTTPError):
        handler.redirect_request(None, None, 302, "Found", {}, "https://evil.example/x")


# ---- reporting errors ----------------------------------------------------------------------
def test_unexpected_errors_are_logged_and_shown_gently(qapp, caplog):
    from wildlife.ui.error_handler import ErrorReporter

    reporter = ErrorReporter()
    shown = []
    reporter.report.disconnect()
    reporter.report.connect(lambda message, details, expected: shown.append((message, expected)))
    try:
        raise KeyError("boom")
    except KeyError as exc:
        with caplog.at_level(logging.CRITICAL):
            reporter.handle(type(exc), exc, exc.__traceback__)
    assert shown == [
        ("Something went wrong. Your data is safe: any change in progress was undone.", False)
    ]
    assert "KeyError" in caplog.text  # the details are in the log
    error = ValidationError({"date": "The date can't be in the future."})
    reporter.handle(type(error), error, None)
    assert shown[-1] == ("Please check the highlighted fields.", True)


def test_a_second_launch_finds_the_first(qapp):
    from wildlife.ui import single_instance

    shown = []
    server = single_instance.InstanceServer(lambda: shown.append(True))
    try:
        assert single_instance.another_instance_is_running(ask_to_show=False)
        assert single_instance.another_instance_is_running()
        qapp.processEvents()
    finally:
        server.deleteLater()
        server._server.close()
    assert not single_instance.another_instance_is_running(ask_to_show=False)


def test_the_log_file_is_utf8_and_rotates(tmp_path):
    from wildlife.logging_setup import setup_logging

    root = logging.getLogger()
    saved = list(root.handlers)
    try:
        setup_logging(tmp_path / "logs")
        logging.getLogger("wildlife.test").info("Grey Heron · café · 🦉")
        for h in root.handlers:
            h.flush()
        text = (tmp_path / "logs" / "wildlife.log").read_text(encoding="utf-8")
        assert "Grey Heron · café · 🦉" in text
        rotating = [h for h in root.handlers if hasattr(h, "maxBytes")]
        assert rotating and rotating[0].maxBytes == 1_000_000 and rotating[0].backupCount == 5
    finally:
        for h in list(root.handlers):
            root.removeHandler(h)
            h.close()
        for h in saved:
            root.addHandler(h)


def test_snapshot_side_files_are_removed_with_it(tmp_path):
    db = tmp_path / "x.db"
    sqlite3.connect(db).close()
    for extra in ("-wal", "-shm"):
        (tmp_path / f"x.db{extra}").write_bytes(b"")
    (tmp_path / "x.json").write_text("{}")
    snapshot.remove(db)
    assert list(tmp_path.iterdir()) == []
