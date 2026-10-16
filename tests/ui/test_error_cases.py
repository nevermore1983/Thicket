"""The spec's error and edge cases (docs/02, section 10) that weren't covered elsewhere.
docs/13-hardening.md lists every row of that table with the test that covers it."""

from datetime import datetime, timedelta
from pathlib import Path

import pytest
from PySide6.QtWidgets import QLabel

from helpers import TODAY, inat_csv, inat_row, taxon_id
from wildlife.config.paths import DataPaths
from wildlife.domain.errors import BackupError
from wildlife.domain.models import SightingDraft
from wildlife.ui.components.thumbnails import ThumbnailLoader
from wildlife.ui.exchange.import_dialog import CHECK

FIXTURES = Path(__file__).parents[1] / "fixtures" / "photos"


def test_a_grid_reference_typo_is_explained(window, qtbot):
    window.add_sighting()
    editor = window.panel.current()
    editor.location.setText("TQ 308 80")  # one figure short
    editor._on_location_edited("")
    editor._update_location_note()
    assert "doesn't look like a grid reference" in editor.f_location.note.text()
    assert "TQ 308 808" in editor.f_location.note.text()  # with an example
    editor._dirty = False
    window.panel.close_panel()


def test_a_time_later_than_now_today_gets_a_gentle_note(window, qtbot, monkeypatch):
    window.add_sighting()
    editor = window.panel.current()
    editor.date.setDate(window.ctx.sightings._today())
    later = (datetime.now() + timedelta(hours=2)).strftime("%H:%M")
    if later > datetime.now().strftime("%H:%M"):  # not when 'later' is tomorrow
        editor.time.setText(later)
        editor._check_time()
        assert editor.f_time.note.text() == "That's later than now. Is the time right?"
        assert editor.f_time.note.property("role") == "help"  # a note, not an error
    editor._dirty = False
    window.panel.close_panel()


def test_an_import_report_can_be_saved(window, qtbot, tmp_path):
    path = tmp_path / "observations.csv"
    rows = [inat_row(1), inat_row(2, observed_on_string="", observed_on="", time_observed_at="")]
    path.write_text(inat_csv(rows), encoding="utf-8")
    window.ctx.settings.update(allow_online=False)
    dialog = window.import_data("inaturalist")
    dialog.open_file(path)
    qtbot.waitUntil(lambda: dialog.pages.currentIndex() == CHECK, timeout=10_000)
    left_out = [r for r in dialog.plan.rows if r.reason]
    report = tmp_path / "left out.txt"
    dialog.write_report(report, left_out)
    assert report.read_text(encoding="utf-8").splitlines() == [
        "Rows left out of observations.csv",
        "",
        "Line 3: Erithacus rubecula: No date",
    ]
    dialog.reject()


def test_a_cloud_synced_data_folder_is_spotted(monkeypatch, tmp_path):
    monkeypatch.setenv("ONEDRIVE", str(tmp_path / "OneDrive"))
    assert DataPaths(tmp_path / "OneDrive" / "WildLife").is_cloud_synced()
    assert DataPaths(Path("C:/Users/x/Dropbox/WildLife")).is_cloud_synced()
    assert not DataPaths(tmp_path / "Local" / "WildLife").is_cloud_synced()


def test_a_damaged_photo_says_cant_display_and_a_gone_one_says_missing(window, qtbot):
    ctx = window.ctx
    damaged, gone = ctx.photos.import_files(
        [FIXTURES / "sample.jpg", FIXTURES / "no_exif.jpg"]
    ).imported
    ctx.photos.path_of(damaged).write_bytes(b"not a picture")
    ctx.photos.path_of(gone).unlink()
    loader = ThumbnailLoader(ctx.photos)
    for photo, text in ((damaged, "Can't display"), (gone, "File missing")):
        loader.get(photo, 300)  # a size not cached by the import
        qtbot.waitUntil(lambda p=photo: isinstance(loader.get(p, 300), str), timeout=5000)
        assert loader.get(photo, 300) == text
        assert ctx.photos.why_no_picture(photo) == text


def test_a_failed_backup_shows_on_the_dashboard(window, qtbot):
    ctx = window.ctx
    taxon = taxon_id(ctx, "Erithacus rubecula")
    ctx.sightings.save(SightingDraft(taxon_id=taxon, observed_date=TODAY))  # not the welcome
    ctx.settings.update(backup_folder="Z:/definitely/not/here")
    with pytest.raises(BackupError):
        ctx.backup.backup_now()
    window.dashboard.refresh()
    texts = [label.text() for label in window.dashboard.findChildren(QLabel)]
    assert "Last backup failed" in texts
    assert any("drive connected" in t for t in texts)  # says why, so it can be fixed
    assert ctx.backup.is_due()  # and it tries again next time


def test_settings_warns_about_a_cloud_synced_data_folder(window, monkeypatch):
    monkeypatch.setattr(DataPaths, "is_cloud_synced", lambda _self: True)
    window.settings_page.refresh()
    texts = [label.text() for label in window.settings_page.findChildren(QLabel)]
    assert any("cloud-synced folder" in t for t in texts)
