"""UI tests for the map page. The real web page loads (offline: tests never use the internet)."""

import pytest
import shiboken6
from PySide6.QtWidgets import QLabel

from helpers import TODAY, taxon_id
from wildlife.domain.codes import LocationMethod
from wildlife.domain.models import PlaceDraft, SightingDraft
from wildlife.ui.panels.place_editor import PlaceEditor
from wildlife.ui.panels.sighting_detail import SightingDetail
from wildlife.ui.panels.sighting_editor import SightingEditor
from wildlife.ui.panels.sighting_list import SightingListPanel

RAINHAM = (51.4955, 0.1975)


def add(ctx, sci="Erithacus rubecula", lat=None, lon=None, **kw):
    return ctx.sightings.save(
        SightingDraft(
            taxon_id=taxon_id(ctx, sci),
            observed_date=TODAY,
            latitude=lat,
            longitude=lon,
            uncertainty_m=10 if lat is not None else None,
            **kw,
        )
    ).sighting


@pytest.fixture
def map_page(window, qtbot):
    """The map page, loaded, with online maps off. Fails if the page reports a script error."""
    window.ctx.settings.update(allow_online=False)
    errors = []
    window.go("map")
    page = window.map_page
    qtbot.waitUntil(lambda: page.bridge is not None, timeout=5000)
    page.bridge.failed.connect(lambda code, message: errors.append((code, message)))
    qtbot.waitUntil(lambda: page.ready or page.failed, timeout=20_000)
    if page.failed:
        pytest.skip("No WebGL on this machine: the map can't run here")
    yield page
    assert [e for e in errors if e[0] == "script"] == []


def test_map_shows_located_sightings(window, map_page, qtbot):
    add(window.ctx, lat=RAINHAM[0], lon=RAINHAM[1])
    add(window.ctx, "Vulpes vulpes", 52.0, -1.0)
    add(window.ctx, "Vulpes vulpes")  # no location
    map_page.refresh()
    qtbot.waitUntil(lambda: map_page.status.text() == "2 sightings on the map", timeout=5000)
    assert (
        map_page.missing.isVisibleTo(map_page) and map_page.missing.text() == "1 without a location"
    )
    assert map_page._bounds.north == 52.0


def test_plain_background_and_banner_when_online_is_off(window, map_page):
    assert map_page._resolved_basemap() == "plain"
    assert map_page.banner.isVisibleTo(map_page)
    assert not map_page.gate.online_allowed
    window.ctx.settings.update(allow_online=True)
    assert map_page.gate.online_allowed and not map_page.banner.isVisibleTo(map_page)
    window.ctx.settings.update(allow_online=False)


def test_clicking_a_pin_opens_the_sighting(window, map_page):
    s = add(window.ctx, lat=RAINHAM[0], lon=RAINHAM[1])
    map_page.bridge.sightingClicked(s.id)
    detail = window.panel.current()
    assert isinstance(detail, SightingDetail) and detail.sighting_id == s.id


def test_several_in_one_spot_are_listed(window, map_page):
    a = add(window.ctx, lat=RAINHAM[0], lon=RAINHAM[1])
    b = add(window.ctx, "Vulpes vulpes", RAINHAM[0], RAINHAM[1])
    map_page.bridge.clusterPicked(f"[{a.id}, {b.id}]")
    panel = window.panel.current()
    assert isinstance(panel, SightingListPanel)
    assert panel.findChildren(QLabel)[0].text() == "2 sightings"


def test_add_sighting_here_fills_the_position(window, map_page):
    map_page.add_at.emit(51.5, -0.12, 25)
    editor = window.panel.current()
    assert isinstance(editor, SightingEditor)
    editor.picker.set_taxon(window.ctx.catalogue.get(taxon_id(window.ctx, "Erithacus rubecula")))
    saved = editor.save().sighting
    assert (saved.latitude, saved.longitude, saved.uncertainty_m) == (51.5, -0.12, 25)
    assert saved.location_method == LocationMethod.MAP


def test_create_place_here(window, map_page):
    map_page.new_place_at.emit(*RAINHAM)
    editor = window.panel.current()
    assert isinstance(editor, PlaceEditor)
    assert editor.position.text().startswith("TQ")


def test_show_on_map_from_a_sighting(window, map_page):
    s = add(window.ctx, lat=RAINHAM[0], lon=RAINHAM[1])
    window.go("sightings")
    window.open_sighting(s.id)
    window.panel.current().show_on_map.emit(window.ctx.sightings.get(s.id))
    assert window.current_page() == "map" and not window.panel.isVisible()


def test_modes_and_places_are_remembered(window, map_page, qtbot):
    window.ctx.places.save(PlaceDraft("Rainham", *RAINHAM))
    add(window.ctx, lat=RAINHAM[0], lon=RAINHAM[1])
    map_page.set_mode("squares")
    qtbot.waitUntil(lambda: "Colour shows" in map_page.squares_note.text(), timeout=5000)
    map_page.set_mode("heat")
    assert map_page.weight_box.isVisibleTo(map_page)
    map_page.places_box.setChecked(True)
    from PySide6.QtCore import QSettings

    assert QSettings().value("map/mode") == "heat"
    assert QSettings().value("map/places", type=bool) is True


def test_no_webgl_shows_an_explanation(window):
    page = window.map_page
    page.failed = True  # pretend, without loading the page
    page._page_failed("no_webgl", "WebGL 2 is not available")
    titles = [w.text() for w in page.findChildren(QLabel, "EmptyStateTitle")]
    assert "The map can't be shown" in titles


def js(page, qtbot, expression: str):
    """Evaluate a JavaScript expression in the map page (errors come back as 'ERR ...')."""
    result = []
    wrapped = (
        f"(() => {{ try {{ return {expression}; }} catch (e) {{ return 'ERR ' + e.message; }} }})()"
    )
    page.view.page().runJavaScript(wrapped, 0, result.append)
    qtbot.waitUntil(lambda: bool(result), timeout=5000)
    return result[0]


def drawn(page, qtbot, layers: list[str]) -> int:
    """How many features MapLibre has drawn in these layers (-1 while a layer doesn't exist yet)."""
    names = ", ".join(f"'{name}'" for name in layers)
    found = js(
        page,
        qtbot,
        f"((ls) => ls.length ? window.__map.queryRenderedFeatures({{layers: ls}}).length : -1)"
        f"([{names}].filter((l) => window.__map.getLayer(l)))",
    )
    return -1 if isinstance(found, str) else int(found)


def test_maplibre_draws_the_pins_and_squares(window, map_page, qtbot):
    add(window.ctx, lat=RAINHAM[0], lon=RAINHAM[1])
    add(window.ctx, "Vulpes vulpes", 52.0, -1.0)
    map_page.refresh()
    qtbot.waitUntil(lambda: map_page._bounds is not None, timeout=5000)
    map_page.bridge.command("fit", bounds={"west": -1.5, "south": 51.3, "east": 0.5, "north": 52.2})
    qtbot.waitUntil(lambda: drawn(map_page, qtbot, ["pins", "clusters"]) >= 2, timeout=10_000)
    map_page.set_mode("squares")
    squares = ["sq-10000-fill", "sq-2000-fill", "sq-1000-fill"]  # which one shows depends on zoom
    qtbot.waitUntil(lambda: drawn(map_page, qtbot, squares) == 2, timeout=10_000)
    # In this mode the pins aren't loaded at all (-1: no such layer), saving memory
    assert drawn(map_page, qtbot, ["pins", "clusters"]) == -1
    map_page.set_mode("pins")
    qtbot.waitUntil(lambda: drawn(map_page, qtbot, ["pins", "clusters"]) >= 2, timeout=10_000)


def test_switching_theme_recolours_the_map(window, map_page, qtbot):
    """Changing theme while the map is open (Settings, or Windows going dark) must recolour it."""
    from wildlife.config.settings import Theme
    from wildlife.ui.theme.tokens import DARK, LIGHT

    def accent() -> str:
        return js(map_page, qtbot, "window.__map.getPaintProperty('highlight', 'circle-stroke-color')")

    qtbot.waitUntil(lambda: accent() == window.theme.tokens.accent, timeout=10_000)
    try:
        window.theme.set_theme(Theme.DARK)
        qtbot.waitUntil(lambda: accent() == DARK.accent, timeout=10_000)
        window.theme.set_theme(Theme.LIGHT)
        qtbot.waitUntil(lambda: accent() == LIGHT.accent, timeout=10_000)
    finally:
        window.theme.set_theme(Theme.SYSTEM)


def test_late_results_after_the_map_closed_are_ignored(window, map_page, qtbot):
    """Background work can finish after the window closed; that must not raise."""
    layer = window.ctx.map.sightings(map_page.filter)
    map_page.view.deleteLater()  # takes the bridge with it
    qtbot.waitUntil(lambda: not shiboken6.isValid(map_page.bridge), timeout=2000)
    map_page._sightings_loaded(map_page._generation, layer)  # must simply do nothing
    map_page._send("fit", bounds={})
