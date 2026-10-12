"""Every control on every screen can be named by a screen reader and reached with Tab.

This is the Phase 12 audit kept as a test: a new icon-only button without a name, a
form field whose label isn't linked to it, or a control Tab can't reach fails here.
"""

from datetime import date

import pytest

from helpers import jpeg_with_gps, taxon_id
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import PlaceDraft, SightingDraft
from wildlife.ui.accessibility import check

PAGES = (
    "dashboard",
    "sightings",
    "calendar",
    "map",
    "photos",
    "statistics",
    "species",
    "places",
    "settings",
)


@pytest.fixture
def seeded(window, tmp_path):
    ctx = window.ctx
    place = ctx.places.save(PlaceDraft("Test Park", 51.5, -0.12))
    robin = ctx.sightings.save(
        SightingDraft(
            taxon_id(ctx, "Erithacus rubecula"), date(2026, 5, 3), "07:40", place_id=place.id
        )
    ).sighting
    photo = ctx.photos.import_files([jpeg_with_gps(tmp_path / "robin.jpg")]).imported[0]
    ctx.photos.attach(robin.id, [photo.id])
    return window, robin


def problems(root) -> list[str]:
    return [f"{f.severity}: {f.message}" for f in check(root)]


@pytest.mark.parametrize("page", PAGES)
def test_pages(seeded, qtbot, page):
    window, _ = seeded
    window.go(page)
    qtbot.wait(50)
    assert problems(window.pages.currentWidget()) == []


def test_sidebar_and_top_bar(seeded):
    from PySide6.QtWidgets import QWidget

    window, _ = seeded
    assert problems(window.findChild(QWidget, "Sidebar")) == []
    assert problems(window.findChild(QWidget, "TopBar")) == []


def test_side_panels(seeded, qtbot):
    window, robin = seeded
    openers = {
        "add": lambda: window.add_sighting(),
        "details": lambda: window.open_sighting(robin.id),
        "edit": lambda: window.edit_sighting(robin.id),
        "species profile": lambda: window.open_species(robin.taxon_id),
        "day": lambda: window.open_day(robin.observed_date, SightingFilter()),
        "new place": lambda: window.edit_place(None),
        "new outing": lambda: window.new_outing(robin.observed_date),
    }
    found = {}
    for name, opener in openers.items():
        opener()
        qtbot.wait(20)
        found[name] = problems(window.panel)
        window.panel.current()._dirty = False
        window.panel.close_panel()
    assert {k: v for k, v in found.items() if v} == {}


def test_windows(seeded, qtbot):
    window, _ = seeded
    openers = {
        "import": lambda: window.import_data("csv"),
        "export": lambda: window.export_data(None),
        "health check": lambda: window.health_check(),
        "restore": lambda: window.restore_backup(),
    }
    found = {}
    for name, opener in openers.items():
        dialog = opener()
        qtbot.wait(20)
        found[name] = problems(dialog)
        dialog.reject()
    assert {k: v for k, v in found.items() if v} == {}


def test_mistakes_show_when_you_leave_a_field(seeded):
    window, _ = seeded
    window.add_sighting()
    editor = window.panel.current()
    editor.time.setText("930")
    editor.time.editingFinished.emit()
    assert editor.time.text() == "09:30"  # tidied
    assert editor.f_time.note.property("role") != "error"
    editor.time.setText("25:70")
    editor.time.editingFinished.emit()
    assert editor.f_time.note.property("role") == "error"
    editor._dirty = False
    window.panel.close_panel()
    window.new_outing(window.ctx.sightings._today())
    outing = window.panel.current()
    outing.temperature.setText("warm")
    outing.temperature.editingFinished.emit()
    assert outing.f_temperature.note.property("role") == "error"
    outing.temperature.setText("80")
    outing.temperature.editingFinished.emit()
    assert "looks wrong" in outing.f_temperature.note.text()
    outing._dirty = False
    window.panel.close_panel()


def test_shortcuts_sheet(seeded, qtbot):
    from PySide6.QtWidgets import QLabel

    from wildlife.ui.shortcuts import SHEET, ShortcutsDialog

    window, _ = seeded
    window.go("dashboard")
    qtbot.keyClicks(window, "?")
    sheet = window.findChildren(ShortcutsDialog)[-1]
    assert sheet.isVisible()
    shown = {label.text() for label in sheet.findChildren(QLabel)}
    assert all(keys in shown for _, rows in SHEET for keys, _ in rows)
    assert problems(sheet) == []
    sheet.reject()


def test_typing_a_question_mark_in_a_box_still_types_it(seeded, qtbot):

    from wildlife.ui.shortcuts import ShortcutsDialog

    window, _ = seeded
    window.search.setFocus()
    qtbot.keyClicks(window.search, "?")
    assert window.search.text() == "?" and not window.findChildren(ShortcutsDialog)
