"""The spec's key scenarios, S1-S7 (docs/02-product-specification.md, section 4), each
followed step by step through the real window."""

import time
from datetime import date

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel

from helpers import TODAY, jpeg_with_gps, taxon_id
from wildlife.config.paths import DataPaths
from wildlife.context import AppContext
from wildlife.data.restore import apply_pending_restore
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import PlaceDraft, SightingDraft
from wildlife.services.statistics import Period
from wildlife.ui.components.rows import StatTile
from wildlife.ui.panels.sighting_editor import SightingEditor


def add(ctx, sci, day=TODAY, **kw):
    return ctx.sightings.save(SightingDraft(taxon_id(ctx, sci), day, **kw)).sighting


def test_s1_quick_add_with_the_keyboard(window, qtbot):
    """Ctrl+N, "goldf", Enter, count 3, Enter: today, now, at the Garden used earlier."""
    ctx = window.ctx
    garden = ctx.places.save(PlaceDraft("Garden", 51.75, -0.34, radius_m=50))
    add(ctx, "Erithacus rubecula", place_id=garden.id)  # earlier today, in the garden
    started = time.perf_counter()
    qtbot.keyClick(window, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)
    editor = window.panel.current()
    assert isinstance(editor, SightingEditor)
    qtbot.keyClicks(editor.picker.edit, "goldf")
    qtbot.waitUntil(lambda: editor.picker.list.count() > 0, timeout=2000)
    qtbot.keyClick(editor.picker.edit, Qt.Key.Key_Return)
    if not window.isActiveWindow():  # Windows won't focus a test window behind another app
        editor.count.setFocus()
    editor.count.selectAll()
    qtbot.keyClicks(editor.count, "3")
    qtbot.keyClick(editor.count, Qt.Key.Key_Return)
    assert time.perf_counter() - started < 10  # the app's share of the 10 seconds
    saved = ctx.sightings.page(
        SightingFilter(taxon_ids=frozenset({taxon_id(ctx, "Carduelis carduelis")}))
    )
    assert len(saved) == 1
    s = saved[0]
    assert (s.display_name, s.count, s.observed_date, s.place_name) == (
        "Goldfinch",
        3,
        TODAY,
        "Garden",
    )
    assert s.observed_time is not None


def test_s2_photos_from_a_walk(window, qtbot, tmp_path):
    """A folder of photos lands in the Inbox grouped by time and place; 3 heron photos
    become one sighting with the photos' date, time and position."""
    walk = tmp_path / "Sunday walk"
    walk.mkdir()
    for minute in (0, 1, 2):  # a heron by the lake
        jpeg_with_gps(
            walk / f"heron{minute}.jpg",
            (90, 90, 120),
            (51, 29, 44),
            (0, 11, 51),
            taken=f"2026:10:10 09:0{minute}:00",
        )
    for minute in (0, 5, 9):  # later, 4 km away
        jpeg_with_gps(
            walk / f"wood{minute}.jpg",
            (40, 110, 40),
            (51, 31, 50),
            (0, 14, 30),
            taken=f"2026:10:10 14:0{minute}:00",
        )
    window.go("photos")
    page = window.photos_page
    page.import_paths([walk])
    qtbot.waitUntil(lambda: not page._importing, timeout=15_000)
    qtbot.waitUntil(lambda: len(page._inbox_grids) == 2, timeout=5000)
    heron_grid = page._inbox_grids[0]
    heron_grid.select_all()
    page._create_sighting()
    editor = window.panel.current()
    assert isinstance(editor, SightingEditor)
    editor.picker.set_taxon(window.ctx.catalogue.get(taxon_id(window.ctx, "Ardea cinerea")))
    editor.save()
    (heron,) = window.ctx.sightings.page(SightingFilter())
    assert (heron.display_name, heron.observed_date, heron.observed_time) == (
        "Grey Heron",
        date(2026, 10, 10),
        "09:00",
    )
    assert heron.latitude is not None and heron.photo_count == 3
    assert len(window.ctx.photos.inbox()) == 3  # the rest wait for later


def test_s3_a_planned_day_trip(window, qtbot):
    """Start an outing; sightings added today join it; its summary counts species and
    those new this year."""
    ctx = window.ctx
    titchwell = ctx.places.save(PlaceDraft("Titchwell Marsh", 52.96, 0.61, radius_m=800))
    add(ctx, "Erithacus rubecula", date(2026, 1, 5))  # already seen this year
    window.new_outing(TODAY)
    editor = window.panel.current()
    editor.title_edit.setText("Titchwell Marsh")
    editor.place.setCurrentIndex(editor.place.findData(titchwell.id))
    editor.start.setText("08:00")
    editor.weather.setCurrentIndex(editor.weather.findText("Sunny"))
    editor.temperature.setText("14")
    editor.save()
    outing = ctx.outings.in_progress()
    assert outing is not None and outing.temperature_c == 14
    window.add_sighting()
    adding = window.panel.current()
    assert adding.outing.currentData() == outing.id  # today's sightings default to the outing
    adding._dirty = False
    window.panel.close_panel()
    for sci in ("Erithacus rubecula", "Ardea cinerea", "Alcedo atthis"):
        add(ctx, sci, observed_time="10:00", outing_id=outing.id)
    window.open_outing(outing.id)
    tiles = {}
    for tile in window.panel.current().findChildren(StatTile):
        label, value = (w.text() for w in tile.findChildren(QLabel)[:2])
        tiles[label] = value
    assert tiles["Species"] == "3" and tiles["New this year"] == "2"  # heron and kingfisher


def test_s4_when_did_i_last_see_a_kingfisher(window, qtbot):
    ctx = window.ctx
    add(ctx, "Alcedo atthis", date(2023, 5, 14))
    add(ctx, "Alcedo atthis", date(2026, 9, 2))
    qtbot.keyClick(window, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier)
    qtbot.keyClicks(window.search, "kingfisher")
    popup = window.search_popup
    qtbot.waitUntil(lambda: popup.list.count() > 1, timeout=2000)
    first = popup.list.item(0).text()
    assert first == "Kingfisher   2 sightings · first 14 May 2023 · last 2 Sep 2026"
    popup.list.setCurrentRow(0)
    popup._choose()
    assert window.current_page() == "sightings" and window.sightings_page.model.total == 2


def test_s5_year_in_review(window, qtbot):
    ctx = window.ctx
    rainham = ctx.places.save(PlaceDraft("Rainham", 51.49, 0.19))
    add(ctx, "Erithacus rubecula", date(2025, 4, 1), place_id=rainham.id)
    add(ctx, "Erithacus rubecula", date(2026, 5, 3), place_id=rainham.id)
    add(ctx, "Alcedo atthis", date(2026, 5, 9), place_id=rainham.id)
    window.go("statistics")
    page = window.statistics_page
    page.data = None
    page.set_period(Period.this_year(TODAY))
    qtbot.waitUntil(lambda: page.data is not None, timeout=10_000)
    data = page.data
    assert [line.label for line in page.growth.lines] == ["2026", "2025"]  # against last year
    assert data.places[0].name == "Rainham"  # top places by species
    assert max(range(12), key=lambda m: page.months.series[0].values[m]) == 4  # best month: May
    assert [f.name for f in data.firsts if f.kind == "lifer"] == ["Kingfisher"]  # the lifers list


def test_s6_new_pc_restore_from_the_backup_drive(window, qtbot, tmp_path):
    """Everything (sightings, photos, settings) comes back on a new PC, verified."""
    ctx = window.ctx
    ctx.settings.update(recorder_name="Sam Recorder", backup_folder=str(tmp_path / "USB drive"))
    heron = add(ctx, "Ardea cinerea")
    photo = ctx.photos.import_files([jpeg_with_gps(tmp_path / "heron.jpg")]).imported[0]
    ctx.photos.attach(heron.id, [photo.id])
    ctx.backup.backup_now("manual")
    backup = ctx.backup.backups()[0].path

    new_pc = DataPaths(tmp_path / "New PC" / "WildLife").ensure()  # a fresh install
    fresh = AppContext.open(new_pc)
    try:
        fresh.backup.request_restore(backup)  # Settings > Backup > Restore > Choose a file
    finally:
        fresh.close()
    assert apply_pending_restore(new_pc).ok  # done as WildLife restarts
    restored = AppContext.open(new_pc)
    try:
        (back,) = restored.sightings.page(SightingFilter())
        assert (back.uuid, back.photo_count) == (heron.uuid, 1)
        (p,) = restored.photos.for_sighting(back.id)
        assert (new_pc.root / p.rel_path).read_bytes() == (
            ctx.paths.root / photo.rel_path
        ).read_bytes()
        assert restored.settings.current.recorder_name == "Sam Recorder"
    finally:
        restored.close()


def test_s7_fixing_a_mistake_in_bulk(window, qtbot, monkeypatch):
    ctx = window.ctx
    for day in range(1, 9):
        add(ctx, "Sympetrum sanguineum", date(2026, 8, day))
    add(ctx, "Erithacus rubecula", date(2026, 8, 1))
    ruddy = taxon_id(ctx, "Sympetrum sanguineum")
    window.show_sightings(SightingFilter(taxon_ids=frozenset({ruddy})))
    page = window.sightings_page
    assert page.model.total == 8
    page.table.selectAll()
    monkeypatch.setattr("wildlife.ui.pages.sightings_page.QDialog.exec", lambda self: True)
    common = ctx.catalogue.get(taxon_id(ctx, "Sympetrum striolatum"))
    monkeypatch.setattr(
        "wildlife.ui.components.species_picker.SpeciesPicker.taxon", property(lambda self: common)
    )
    page._change_species()
    assert ctx.sightings.totals(SightingFilter(taxon_ids=frozenset({common.id})))[0] == 8
    assert ctx.sightings.totals(SightingFilter(taxon_ids=frozenset({ruddy})))[0] == 0
    window._undo()  # Ctrl+Z
    assert ctx.sightings.totals(SightingFilter(taxon_ids=frozenset({ruddy})))[0] == 8
