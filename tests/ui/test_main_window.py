"""UI tests: pytest-qt drives a real window, with the mini species list and a temp data folder."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMessageBox, QPushButton

from helpers import TODAY, taxon_id
from wildlife.config.settings import Theme
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import PlaceDraft, SightingDraft
from wildlife.ui.main_window import NAV
from wildlife.ui.panels.place_editor import PlaceEditor
from wildlife.ui.panels.sighting_detail import SightingDetail
from wildlife.ui.panels.sighting_editor import SightingEditor, normalise_time
from wildlife.ui.theme.tokens import DARK, LIGHT


def editor(win) -> SightingEditor:
    view = win.panel.current()
    assert isinstance(view, SightingEditor)
    return view


def type_species(qtbot, ed: SightingEditor, text: str) -> None:
    qtbot.keyClicks(ed.picker.edit, text)
    qtbot.waitUntil(lambda: ed.picker.list.isVisible() and ed.picker.list.count() > 0, timeout=2000)


# ---- shell -------------------------------------------------------------------
def test_new_library_shows_welcome(window):
    assert window.current_page() == "dashboard"
    titles = [w.text() for w in window.dashboard.findChildren(QLabel, "EmptyStateTitle")]
    assert titles == ["Start your wildlife journal"]


def test_every_page_opens(window, qtbot):
    for entry in (*NAV,):
        qtbot.mouseClick(window._nav_buttons[entry.key], Qt.MouseButton.LeftButton)
        assert window.current_page() == entry.key


def test_theme_switch_from_settings_is_saved(window, qtbot):
    window.go("settings")
    choice = window.settings_page.theme_choice
    qtbot.mouseClick(choice.button_for(Theme.DARK), Qt.MouseButton.LeftButton)
    assert window.theme.tokens is DARK and window.ctx.settings.current.theme is Theme.DARK
    window.settings_page.theme_choice.button_for(Theme.LIGHT).click()
    assert window.theme.tokens is LIGHT


def test_pages_are_narrow_enough_for_the_sidebar_to_collapse(window):
    """The sidebar shrinks below 900 px, so at full width (228 px) no page may need over 671."""
    for i in range(window.pages.count()):
        page = window.pages.widget(i)
        assert page.minimumSizeHint().width() <= 671, type(page).__name__


def test_sidebar_collapses_when_narrow(window):
    window.setMinimumSize(0, 0)
    window.resize(820, 700)
    assert window._nav_buttons["map"].text() == ""
    window.resize(1280, 800)
    assert window._nav_buttons["map"].text() == "Map"


# ---- adding ------------------------------------------------------------------------
def test_keyboard_only_add(window, qtbot):
    qtbot.keyClick(window, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)
    ed = editor(window)
    type_species(qtbot, ed, "robin")
    qtbot.keyClick(ed.picker.edit, Qt.Key.Key_Return)  # pick the first suggestion
    assert ed.picker.taxon.display_name == "Robin"
    if window.isActiveWindow():  # Windows won't focus a test window while you use another app
        qtbot.waitUntil(lambda: ed.count.hasFocus(), timeout=1000)
    else:
        ed.count.selectAll()
    qtbot.keyClicks(ed.count, "c. 12")  # replaces the selected default "1"
    qtbot.keyClick(ed.count, Qt.Key.Key_Return)  # save
    assert not window.panel.isVisible()
    (saved,) = window.ctx.sightings.page(SightingFilter())  # one Enter, one sighting
    assert (saved.display_name, saved.count, saved.count_qualifier.value) == ("Robin", 12, "approx")
    assert saved.observed_date == TODAY
    assert any("Robin saved" in m and "new species" in m for m in window.toasts.messages())


def test_save_without_species_shows_message(window, qtbot):
    window.add_sighting()
    ed = editor(window)
    ed.save()
    assert "Choose a species" in ed.f_species.note.text()
    assert window.panel.isVisible() and window.ctx.sightings.totals(SightingFilter())[0] == 0


def test_save_and_add_another_keeps_date_and_place(window, qtbot):
    garden = window.ctx.places.save(PlaceDraft("Garden", 51.75, -0.34, radius_m=50))
    window.add_sighting(SightingDraft(taxon_id=None, observed_date=TODAY, place_id=garden.id))
    ed = editor(window)
    type_species(qtbot, ed, "fox")
    qtbot.keyClick(ed.picker.edit, Qt.Key.Key_Return)
    qtbot.keyClick(ed, Qt.Key.Key_Return, Qt.KeyboardModifier.ControlModifier)
    fresh = editor(window)
    assert fresh is not ed and fresh.picker.taxon is None and fresh._place_id == garden.id
    assert window.ctx.sightings.totals(SightingFilter())[0] == 1


def test_grid_reference_is_parsed(window, qtbot):
    window.add_sighting()
    ed = editor(window)
    qtbot.keyClicks(ed.location, "TQ 308 808")
    qtbot.waitUntil(lambda: "±100 m" in ed.f_location.note.text(), timeout=1000)
    ed.location.setText("")
    qtbot.keyClicks(ed.location, "-0.12, 51.5")
    qtbot.waitUntil(lambda: "swapped" in ed.f_location.note.text(), timeout=1000)


def test_escape_with_changes_asks_first(window, qtbot, monkeypatch):
    window.add_sighting()
    ed = editor(window)
    qtbot.keyClicks(ed.notes, "a note")
    asked = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **k: asked.append(True) or QMessageBox.StandardButton.Cancel,
    )
    window.panel.close_panel()
    assert asked and window.panel.isVisible()  # chose to keep editing


@pytest.mark.parametrize(
    ("typed", "stored"), [("930", "09:30"), ("9:30", "09:30"), ("09.30", "09:30"), ("", None)]
)
def test_time_normalising(typed, stored):
    assert normalise_time(typed) == stored


# ---- viewing, editing, deleting ------------------------------------------------------
def _add(window, sci="Erithacus rubecula", **kw):
    return window.ctx.sightings.save(
        SightingDraft(taxon_id=taxon_id(window.ctx, sci), observed_date=TODAY, **kw)
    ).sighting


def test_open_edit_and_undo(window, qtbot):
    s = _add(window, count=2)
    window.go("sightings")
    window.open_sighting(s.id)
    assert isinstance(window.panel.current(), SightingDetail)
    window.edit_sighting(s.id)
    ed = editor(window)
    ed.count.setText("5")
    ed.save()
    assert isinstance(window.panel.current(), SightingDetail)  # back to the detail view
    assert window.ctx.sightings.get(s.id).count == 5
    qtbot.keyClick(window, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert window.ctx.sightings.get(s.id).count == 2


def test_delete_from_detail_and_undo(window, qtbot):
    s = _add(window)
    window.open_sighting(s.id)
    window.panel.current().delete_requested.emit(s.id)
    assert window.ctx.sightings.totals(SightingFilter())[0] == 0 and not window.panel.isVisible()
    qtbot.keyClick(window, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert window.ctx.sightings.totals(SightingFilter())[0] == 1


def test_sightings_table_lists_and_filters(window, qtbot):
    _add(window)
    _add(window, "Vulpes vulpes", notes="Crossing the lane")
    window.go("sightings")
    assert window.sightings_page.model.rowCount() == 2
    window.show_sightings(SightingFilter(text="lane"))
    assert window.sightings_page.model.rowCount() == 1
    assert "match these filters" in window.sightings_page.footer.text()
    window.sightings_page.filter_bar.set_filter(SightingFilter())
    assert window.sightings_page.model.rowCount() == 2


def test_bulk_delete_from_table(window, qtbot):
    for _ in range(3):
        _add(window)
    window.go("sightings")
    window.sightings_page.table.selectAll()
    assert window.sightings_page.bulk.isVisible()
    window.sightings_page.delete_selected()
    assert window.ctx.sightings.totals(SightingFilter())[0] == 0


def test_dashboard_updates_after_saving(window):
    _add(window)
    window.go("dashboard")
    window.dashboard.refresh()
    tiles = [w.text() for w in window.dashboard.findChildren(QLabel, "TileValue")]
    assert tiles[:2] == ["1", "1"]


def test_global_search_goes_to_filtered_sightings(window, qtbot):
    _add(window, notes="On the feeder")
    qtbot.keyClicks(window.search, "feeder")
    qtbot.keyClick(window.search, Qt.Key.Key_Return)
    assert window.current_page() == "sightings"
    assert window.sightings_page.model.filter.text == "feeder"
    assert window.sightings_page.model.rowCount() == 1


# ---- places and backups --------------------------------------------------------------
def test_create_place(window, qtbot):
    window.go("places")
    window.edit_place(None)
    ed = window.panel.current()
    assert isinstance(ed, PlaceEditor)
    qtbot.keyClicks(ed.name, "Garden")
    qtbot.keyClicks(ed.position, "TL 155 076")
    ed.save()
    assert [p.name for p in window.ctx.places.all()] == ["Garden"]
    qtbot.waitUntil(lambda: window.places_page.table.rowCount() == 1, timeout=2000)


def test_backup_now_from_settings(window, qtbot):
    window.go("settings")
    window.settings_page.backup_requested.emit()
    qtbot.waitUntil(lambda: window.ctx.backup.last_result() is not None, timeout=10_000)
    assert window.ctx.backup.last_result().ok


def test_empty_now_empties_photos_too(window, monkeypatch):
    """It used to remove only sightings: their photos, and photos deleted on their own,
    stayed in the bin for another 30 days."""
    from pathlib import Path

    ctx = window.ctx
    fixtures = Path(__file__).parents[1] / "fixtures" / "photos"
    on_sighting, loose = ctx.photos.import_files(
        [fixtures / "sample.jpg", fixtures / "sample.heic"]
    ).imported
    s = _add(window)
    ctx.photos.attach(s.id, [on_sighting.id])
    ctx.sightings.delete([s.id])
    ctx.photos.delete([loose.id])
    window.go("settings")
    page = window.settings_page
    page.refresh()
    assert "1 sighting · 1 photo" in " ".join(lbl.text() for lbl in page.findChildren(QLabel))
    monkeypatch.setattr(QMessageBox, "question", lambda *a, **k: QMessageBox.StandardButton.Yes)
    page._empty_bin()
    assert ctx.sightings.recycle_bin() == [] and ctx.photos.recycle_bin() == []
    assert not ctx.photos.path_of(on_sighting).exists()
    assert not ctx.photos.path_of(loose).exists()


def test_empty_now_works_when_only_photos_are_in_the_bin(window):
    from pathlib import Path

    photo = window.ctx.photos.import_files(
        [Path(__file__).parents[1] / "fixtures" / "photos" / "sample.jpg"]
    ).imported[0]
    window.ctx.photos.delete([photo.id])
    window.settings_page.refresh()
    buttons = {b.text(): b for b in window.settings_page.findChildren(QPushButton)}
    assert buttons["Empty now"].isEnabled()


def test_recycle_bin_restore(window):
    from wildlife.ui.pages.settings_page import RecycleBinDialog

    s = _add(window)
    window.ctx.sightings.delete([s.id])
    dialog = RecycleBinDialog(window.ctx, window)
    assert dialog.list.count() == 1
    dialog.list.selectAll()
    dialog._restore()
    assert dialog.restored == 1 and window.ctx.sightings.totals(SightingFilter())[0] == 1
