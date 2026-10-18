"""Starting Thicket when its data can't be opened (app.open_data and its dialog).

The real dialog is built; only the click is pretended (QMessageBox.exec is replaced by
picking one of its buttons), so the text, the buttons and what they do are all tested."""

from datetime import date

import pytest
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QMessageBox

from helpers import taxon_id
from wildlife import app
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import SightingDraft


def damage(paths) -> None:
    paths.database.write_bytes(b"not a database" * 600)
    for side in ("-wal", "-shm"):
        paths.database.with_name(paths.database.name + side).unlink(missing_ok=True)


@pytest.fixture
def answer(monkeypatch, qtbot):  # qtbot: the dialog needs a running Qt application
    """Pretend you click the button with this text; records what the dialog said."""
    seen: dict = {}

    def use(button_text: str):
        def fake_exec(box: QMessageBox) -> int:
            seen["text"], seen["info"] = box.text(), box.informativeText()
            seen["buttons"] = [b.text() for b in box.buttons()]
            seen["clicked"] = next(b for b in box.buttons() if b.text() == button_text)
            return 0

        monkeypatch.setattr(QMessageBox, "exec", fake_exec)
        monkeypatch.setattr(QMessageBox, "clickedButton", lambda box: seen["clicked"])
        return seen

    opened: list = []
    monkeypatch.setattr(QDesktopServices, "openUrl", lambda url: opened.append(url))
    use.opened_folder = opened
    return use


def test_healthy_data_just_opens(ctx, paths, answer):
    ctx.close()
    seen = answer("Close")
    opened = app.open_data(paths)
    assert opened is not None and opened[1] is None  # no restore was due
    opened[0].close()
    assert seen == {}  # no dialog


def test_damaged_data_offers_the_latest_backup_and_opens_it(ctx, paths, answer):
    ctx.sightings.save(SightingDraft(taxon_id(ctx, "Erithacus rubecula"), date(2026, 5, 3)))
    ctx.backup.backup_now("manual")
    ctx.close()
    damage(paths)
    seen = answer("Restore latest backup")
    opened = app.open_data(paths)
    assert "Restore latest backup" in seen["buttons"]
    assert "1 sightings" in seen["info"] and "safety copy" in seen["info"]
    assert opened is not None
    restored_ctx, outcome = opened
    try:
        assert outcome.ok
        assert restored_ctx.sightings.totals(SightingFilter())[0] == 1
    finally:
        restored_ctx.close()


def test_damaged_data_is_not_opened_if_you_close_the_message(ctx, paths, answer):
    ctx.backup.backup_now("manual")
    ctx.close()
    damage(paths)
    answer("Close")
    assert app.open_data(paths) is None


def test_with_no_backup_it_offers_the_data_folder(ctx, paths, answer):
    ctx.close()
    damage(paths)
    seen = answer("Open data folder")
    assert app.open_data(paths) is None
    assert "Restore latest backup" not in seen["buttons"]
    assert str(paths.root) in seen["info"]
    assert len(answer.opened_folder) == 1  # opened in Explorer
