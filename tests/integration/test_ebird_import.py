"""Importing eBird exports end to end, from invented rows (helpers.ebird_full_row, ebird_life_row)."""

from dataclasses import replace

from helpers import EBIRD_FULL as FULL
from helpers import EBIRD_LIFE as LIFE
from helpers import ebird_full_row as full_row
from helpers import ebird_life_row as life_row
from helpers import ebird_table as table
from helpers import taxon_id
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import PlaceDraft
from wildlife.services.importer import ADD, SAME, SKIP, UPDATE


def write(tmp_path, name: str, text: str):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def test_download_my_data_imports_every_checklist_row(ctx, tmp_path):
    rows = [
        full_row(),
        full_row(**{"Scientific Name": "Alcedo atthis", "Common Name": "Common Kingfisher"}),
        full_row(**{"Submission ID": "S101", "Date": "2026-05-04"}),  # another day's Robin
    ]
    plan = ctx.ebird.preview(write(tmp_path, "MyEBirdData.csv", table(FULL, rows)))
    assert [r.action for r in plan.rows] == [ADD, ADD, ADD] and not plan.unmatched
    result = ctx.ebird.run(plan)
    assert len(result.added) == 3
    robin = ctx.sightings.get(result.added[0])
    assert robin.taxon_id == taxon_id(ctx, "Erithacus rubecula")
    assert (robin.observed_time, robin.count, robin.uncertainty_m) == ("07:45", 2, 100)
    assert robin.source == "ebird" and robin.source_id == "S100/Erithacus rubecula"


def test_a_life_list_then_the_full_data_adds_only_whats_new(ctx, tmp_path):
    life = table(LIFE, [life_row()])
    ctx.ebird.run(ctx.ebird.preview(write(tmp_path, "ebird_GB_life_list.csv", life)))
    full = table(FULL, [full_row(), full_row(**{"Submission ID": "S101"})])
    plan = ctx.ebird.preview(write(tmp_path, "MyEBirdData.csv", full))
    # The life list's Robin is upgraded with the full data's time and exact position
    assert [r.action for r in plan.rows] == [UPDATE, ADD]
    result = ctx.ebird.run(plan)
    robin = ctx.sightings.get(result.updated[0])
    assert robin.observed_time == "07:45" and robin.latitude == 52.123457
    assert ctx.sightings.totals(SightingFilter())[0] == 2  # nothing doubled
    again = ctx.ebird.preview(write(tmp_path, "MyEBirdData2.csv", full))
    assert [r.action for r in again.rows] == [SAME, SAME]
    life_again = ctx.ebird.preview(write(tmp_path, "life2.csv", life))
    assert [r.action for r in life_again.rows] == [SAME]  # a list never replaces full data


def test_the_full_data_keeps_a_life_list_sighting_you_edited(ctx, tmp_path):
    life = table(LIFE, [life_row()])
    result = ctx.ebird.run(ctx.ebird.preview(write(tmp_path, "list.csv", life)))
    mine = ctx.sightings.get(result.added[0])
    ctx.sightings.save(replace(mine.to_draft(), notes="My own note"))
    plan = ctx.ebird.preview(write(tmp_path, "MyEBirdData.csv", table(FULL, [full_row()])))
    assert plan.rows[0].action == SKIP and "your Thicket version is kept" in plan.rows[0].reason


def test_a_hotspot_without_a_position_uses_your_place_of_that_name(ctx, tmp_path):
    reserve = ctx.places.save(PlaceDraft("Invented Reserve", 52.5, -1.5))
    row = life_row(Location="Invented Reserve")
    result = ctx.ebird.run(ctx.ebird.preview(write(tmp_path, "list.csv", table(LIFE, [row]))))
    sighting = ctx.sightings.get(result.added[0])
    assert sighting.place_id == reserve.id and sighting.latitude is None


def test_location_names_show_where_there_is_no_saved_place(ctx, tmp_path):
    """A hotspot with no position, and a personal location with one: both are named."""
    rows = [life_row(Location="Invented Reserve"), life_row(SubID="S200")]
    result = ctx.ebird.run(ctx.ebird.preview(write(tmp_path, "list.csv", table(LIFE, rows))))
    hotspot, personal = (ctx.sightings.get(i) for i in result.added)
    assert hotspot.where == "Invented Reserve" and not hotspot.has_location
    assert personal.where == "Somewhere, England, GB" and personal.has_location


def test_the_sighting_links_back_to_its_checklist(ctx, tmp_path):
    from wildlife.ui.panels.sighting_detail import _origin

    path = write(tmp_path, "MyEBirdData.csv", table(FULL, [full_row()]))
    result = ctx.ebird.run(ctx.ebird.preview(path))
    app, link, words = _origin(ctx.sightings.get(result.added[0]))
    assert (app, link) == ("eBird", "https://ebird.org/checklist/S100")
    assert "checklist" in words


def test_the_import_can_be_undone(ctx, tmp_path):
    path = write(tmp_path, "MyEBirdData.csv", table(FULL, [full_row()]))
    result = ctx.ebird.run(ctx.ebird.preview(path))
    result.undo.run()
    assert [r.action for r in ctx.ebird.preview(path).rows] == [ADD]


def test_sorting_by_place_uses_the_location_name_shown(ctx, tmp_path):
    ctx.places.save(PlaceDraft("Middle Wood", 52.5, -1.5))
    rows = [
        life_row(Location="Zebra Marsh", SubID="S1"),
        life_row(Location="Middle Wood", SubID="S2"),  # your saved place
        life_row(Location="Alder Carr", SubID="S3"),
    ]
    ctx.ebird.run(ctx.ebird.preview(write(tmp_path, "list.csv", table(LIFE, rows))))
    shown = [s.where for s in ctx.sightings.page(SightingFilter(), "place", descending=False)]
    assert shown == ["Alder Carr", "Middle Wood", "Zebra Marsh"]
