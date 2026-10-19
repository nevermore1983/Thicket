"""Choose on map: the sighting editor's button and the map window behind it."""

from typing import ClassVar

import pytest
from PySide6.QtWidgets import QDialog, QLabel

from helpers import taxon_id
from wildlife.domain.codes import LocationMethod
from wildlife.domain.models import PlaceDraft
from wildlife.ui import map_picker
from wildlife.ui.map_picker import MapPicker
from wildlife.ui.panels.sighting_editor import SightingEditor

RAINHAM = (51.4955, 0.1975)


def new_editor(window) -> SightingEditor:
    window.add_sighting()
    editor = window.panel.current()
    assert isinstance(editor, SightingEditor)
    return editor


def test_a_position_chosen_on_the_map_is_saved(window):
    editor = new_editor(window)
    editor.use_map_position(*RAINHAM, 10)
    assert editor.location.text().startswith("TQ")
    assert editor.f_location.note.property("role") == "ok"
    editor.picker.set_taxon(window.ctx.catalogue.get(taxon_id(window.ctx, "Erithacus rubecula")))
    saved = editor.save().sighting
    assert (saved.latitude, saved.longitude, saved.uncertainty_m) == (*RAINHAM, 10)
    assert saved.location_method == LocationMethod.MAP


def test_it_finds_the_place_unless_you_chose_one(window):
    rainham = window.ctx.places.save(PlaceDraft("Rainham Marshes", *RAINHAM))
    editor = new_editor(window)
    editor.use_map_position(51.4956, 0.1976, 10)  # inside Rainham Marshes
    assert editor._place_id == rainham.id
    editor._choose_place(None)  # "No place": your choice wins
    editor.use_map_position(51.4956, 0.1976, 10)
    assert editor._place_id is None


class FakePicker:
    """Stands in for the map window: records where it opened and 'clicks' a spot."""

    DialogCode = QDialog.DialogCode
    opened: ClassVar[list] = []

    def __init__(self, ctx, theme, start, zoom, parent=None) -> None:
        FakePicker.opened.append((start, zoom))
        self.position = (52.0, -1.0, 25)

    def exec(self):
        return QDialog.DialogCode.Accepted

    def deleteLater(self) -> None:
        pass


def test_the_button_opens_the_map_where_the_sighting_is(window, monkeypatch):
    monkeypatch.setattr(map_picker, "MapPicker", FakePicker)
    FakePicker.opened = []
    editor = new_editor(window)
    editor._choose_place(None)
    editor.map_btn.click()  # nothing known yet: the map decides
    editor.location.setText("TQ 308 808")
    editor._on_location_edited("TQ 308 808")
    editor.map_btn.click()  # opens on what was typed
    place = window.ctx.places.save(PlaceDraft("Big wood", 51.0, -1.0, radius_m=1_500))
    editor._choose_place(place.id)
    editor.location.clear()
    editor._on_location_edited("")
    editor.map_btn.click()  # opens on the place, zoomed out to fit it
    (first, _), (typed, typed_zoom), (centre, place_zoom) = FakePicker.opened
    assert first is None
    assert typed[0] == pytest.approx(51.511, abs=0.001) and typed_zoom == 15
    assert centre == (51.0, -1.0) and place_zoom == 13
    assert editor._lat == 52.0 and editor._method == LocationMethod.MAP  # the spot was used


# ---- the map window itself -------------------------------------------------------------
@pytest.fixture
def picker(window, qtbot):
    window.ctx.settings.update(allow_online=False)  # tests never use the internet
    dialog = MapPicker(window.ctx, window.theme, RAINHAM, 15, parent=window)
    qtbot.addWidget(dialog)
    dialog.show()
    yield dialog
    dialog.reject()


def test_choosing_a_spot_shows_where_it_is(window, picker):
    window.ctx.places.save(PlaceDraft("Rainham Marshes", *RAINHAM))
    assert not picker.use.isEnabled()
    picker._picked(51.4956, 0.1976, 17)
    lat, lon, unc = picker.position
    assert (lat, lon) == (51.4956, 0.1976) and unc <= 10  # zoomed right in: close
    assert picker.where.text().startswith("TQ") and "inside Rainham Marshes" in picker.where.text()
    assert picker.use.isEnabled()
    picker._picked(51.4956, 0.1976, 8)
    assert picker.position[2] >= 500  # zoomed out: rough


def test_without_webgl_it_says_to_type_the_position(picker):
    picker._page_failed("no_webgl", "WebGL 2 is not available")
    texts = [w.text() for w in picker.findChildren(QLabel)]
    assert "The map can't be shown" in texts
    assert any("Type a grid reference" in t for t in texts)
    assert not picker.use.isEnabled()


def js(picker, qtbot, expression: str):
    result = []
    wrapped = (
        f"(() => {{ try {{ return {expression}; }} catch (e) {{ return 'ERR ' + e.message; }} }})()"
    )
    picker.view.page().runJavaScript(wrapped, 0, result.append)
    qtbot.waitUntil(lambda: bool(result), timeout=5000)
    return result[0]


def test_clicking_the_map_places_the_pin(window, picker, qtbot):
    errors = []
    picker.bridge.failed.connect(lambda code, message: errors.append(code))
    qtbot.waitUntil(lambda: picker.ready or picker.failed, timeout=20_000)
    if picker.failed:
        pytest.skip("No WebGL on this machine: the map can't run here")
    qtbot.waitUntil(
        lambda: js(picker, qtbot, "!!window.__map && window.__map.loaded()"), timeout=10_000
    )
    assert js(picker, qtbot, "document.querySelectorAll('.maplibregl-marker').length") == 1
    assert picker.position is None  # the starting pin isn't a choice yet

    # A click as MapLibre reports one (its own pin code reads the original mouse event)
    clicked = js(
        picker,
        qtbot,
        "(window.__map.fire('click', {lngLat: {lng: 0.2, lat: 51.5}, point: {x: 5, y: 5}, "
        "originalEvent: new MouseEvent('click')}), 'ok')",
    )
    assert clicked == "ok"  # not 'ERR ...': nothing on the page failed
    qtbot.waitUntil(lambda: picker.position is not None, timeout=5000)
    assert picker.position[:2] == (51.5, 0.2)
    assert js(picker, qtbot, "document.querySelectorAll('.maplibregl-marker').length") == 1

    js(picker, qtbot, "window.__map.jumpTo({center: [0.1, 51.4]})")  # Enter: the map's centre
    pressed = js(
        picker,
        qtbot,
        "window.__map.getCanvas().dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter'}))",
    )
    assert pressed is True
    qtbot.waitUntil(lambda: picker.position[:2] == (51.4, 0.1), timeout=5000)

    # Windows going dark while the window is open: the pin follows the theme and stays put
    from wildlife.config.settings import Theme
    from wildlife.ui.theme.tokens import DARK

    def pin_colours() -> list[str]:
        found = js(  # joined into text: a JavaScript list doesn't come back through Qt
            picker,
            qtbot,
            "[...document.querySelectorAll('.maplibregl-marker [fill]')]"
            ".map((e) => e.getAttribute('fill')).join(',')",
        )
        return found.lower().split(",")

    try:
        window.theme.set_theme(Theme.DARK)
        qtbot.waitUntil(lambda: DARK.accent.lower() in pin_colours(), timeout=10_000)
    finally:
        window.theme.set_theme(Theme.SYSTEM)
    assert js(picker, qtbot, "document.querySelectorAll('.maplibregl-marker').length") == 1
    assert picker.position[:2] == (51.4, 0.1)
    assert "script" not in errors
