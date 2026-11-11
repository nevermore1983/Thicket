"""Importing eBird exports end to end, from invented rows (helpers.ebird_full_row, ebird_life_row)."""

from dataclasses import replace

import pytest

from helpers import EBIRD_FULL as FULL
from helpers import EBIRD_LIFE as LIFE
from helpers import ebird_full_row as full_row
from helpers import ebird_life_row as life_row
from helpers import ebird_table as table
from helpers import taxon_id
from wildlife.domain.errors import NotFoundError
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


def checklist_rows():
    """Two species on one invented checklist, and one on another."""
    walk = {
        "Duration (Min)": "95",
        "All Obs Reported": "1",
        "Distance Traveled (km)": "2.5",
        "Number of Observers": "2",
        "Protocol": "eBird - Traveling Count",
        "Checklist Comments": "Calm and bright",
    }
    return [
        full_row(**walk),
        full_row(**walk, **{"Scientific Name": "Alcedo atthis", "Common Name": "Kingfisher"}),
        full_row(**{"Submission ID": "S101", "Date": "2026-05-04"}),
    ]


def test_each_checklist_becomes_one_outing(ctx, tmp_path):
    park = ctx.places.save(PlaceDraft("Invented Park", 52.12, -1.76))
    path = write(tmp_path, "MyEBirdData.csv", table(FULL, checklist_rows()))
    result = ctx.ebird.run(ctx.ebird.preview(path))
    assert len(result.outings) == 2 and "2 outings" in result.describe()
    robin, kingfisher, other = (ctx.sightings.get(i) for i in result.added)
    assert robin.outing_id == kingfisher.outing_id != other.outing_id
    walk = ctx.outings.get(robin.outing_id)
    assert (walk.outing_date.isoformat(), walk.start_time, walk.end_time) == (
        "2026-05-03",
        "07:45",
        "09:20",
    )
    assert walk.place_id == park.id and walk.is_complete_list
    assert walk.notes.startswith("Calm and bright")
    assert "S100: eBird - Traveling Count, 2.5 km, 2 observers" in walk.notes
    again = ctx.ebird.run(
        ctx.ebird.preview(write(tmp_path, "newer.csv", table(FULL, checklist_rows())))
    )
    assert again.outings == []  # the same checklists: no second outings


def test_undo_removes_the_outings_too(ctx, tmp_path):
    result = ctx.ebird.run(
        ctx.ebird.preview(write(tmp_path, "d.csv", table(FULL, checklist_rows())))
    )
    result.undo.run()
    for outing_id in result.outings:
        with pytest.raises(NotFoundError):
            ctx.outings.get(outing_id)


def test_a_life_list_makes_no_outings(ctx, tmp_path):
    result = ctx.ebird.run(ctx.ebird.preview(write(tmp_path, "l.csv", table(LIFE, [life_row()]))))
    assert result.outings == [] and ctx.sightings.get(result.added[0]).outing_id is None


def test_an_outing_you_deleted_isnt_made_again(ctx, tmp_path):
    path = write(tmp_path, "d.csv", table(FULL, checklist_rows()[:1]))
    first = ctx.ebird.run(ctx.ebird.preview(path))
    ctx.outings.delete(first.outings[0])
    rows = [full_row(**{"Scientific Name": "Alcedo atthis", "Common Name": "Kingfisher"})]
    later = ctx.ebird.run(ctx.ebird.preview(write(tmp_path, "e.csv", table(FULL, rows))))
    assert later.outings == [] and ctx.sightings.get(later.added[0]).outing_id is None


# ---- audit 3 (docs/22-code-audit-3.md) -----------------------------------------------
def test_sightings_imported_before_outings_are_grouped_on_the_next_import(ctx, tmp_path):
    """A1: Download My Data imported with 1.4 (no outings), imported again with 1.5+."""
    rows = checklist_rows()
    first = ctx.ebird.run(ctx.ebird.preview(write(tmp_path, "d.csv", table(FULL, rows))))
    with ctx.db.transaction() as conn:  # as 1.4 left it: no outings
        conn.execute("UPDATE sighting SET outing_id = NULL")
        conn.execute("UPDATE sighting SET source_edited = 0")
        conn.execute("DELETE FROM outing")
    plan = ctx.ebird.preview(write(tmp_path, "d2.csv", table(FULL, rows)))
    assert [r.action for r in plan.rows] == [SAME, SAME, SAME] and plan.new_outings == 2
    again = ctx.ebird.run(plan)
    assert len(again.outings) == 2 and sorted(again.grouped) == sorted(first.added)
    robin, kingfisher, other = (ctx.sightings.get(i) for i in first.added)
    assert robin.outing_id == kingfisher.outing_id != other.outing_id
    # Grouping isn't your edit: a later download may still update them
    assert ctx.ebird.preview(write(tmp_path, "d3.csv", table(FULL, rows))).new_outings == 0
    with ctx.db.connection() as conn:
        assert conn.execute("SELECT MAX(source_edited) FROM sighting").fetchone()[0] == 0
    again.undo.run()
    assert ctx.sightings.get(first.added[0]).outing_id is None


def test_a_species_ebird_renamed_is_recognised_by_its_checklist(ctx, tmp_path):
    """A3: eBird's names change every year; the sighting must not come in twice."""
    path = write(tmp_path, "d.csv", table(FULL, [full_row()]))
    first = ctx.ebird.run(ctx.ebird.preview(path))
    with ctx.db.transaction() as conn:  # as if eBird used another name then
        conn.execute("UPDATE sighting SET source_id = 'S100/Erithacus rubeculus'")
    plan = ctx.ebird.preview(write(tmp_path, "d2.csv", table(FULL, [full_row()])))
    assert [r.action for r in plan.rows] == [SAME]
    assert plan.rows[0].existing_id == first.added[0]
    assert ctx.sightings.totals(SightingFilter())[0] == 1


def test_removing_an_import_later_puts_its_outings_away_too(ctx, tmp_path):
    """A4: Settings › Import & export › remove, days later."""
    result = ctx.ebird.run(
        ctx.ebird.preview(write(tmp_path, "d.csv", table(FULL, checklist_rows())))
    )
    batch = ctx.import_history.batches()[0]
    undo = ctx.import_history.remove(batch.id)
    for outing_id in result.outings:
        with pytest.raises(NotFoundError):
            ctx.outings.get(outing_id)
    undo.run()
    assert [ctx.outings.get(i).sightings for i in result.outings] == [2, 1]


def test_a_checklist_without_a_duration_isnt_an_outing_in_progress(ctx, tmp_path):
    """A5: an incidental sighting today would otherwise look like the outing you're on."""
    row = full_row(Date=ctx.sightings._today().isoformat(), Time="06:00 AM")
    result = ctx.ebird.run(ctx.ebird.preview(write(tmp_path, "d.csv", table(FULL, [row]))))
    outing = ctx.outings.get(result.outings[0])
    assert (outing.start_time, outing.end_time) == ("06:00", "06:00")
    assert not outing.in_progress


def test_checklist_outings_are_named_by_place_and_date_and_link_to_ebird(ctx, tmp_path):
    """B3: twenty visits to one reserve shouldn't all read 'Invented Park'."""
    ctx.places.save(PlaceDraft("Invented Park", 52.12, -1.76))
    rows = [
        full_row(Location="Invented Park"),
        full_row(
            **{"Submission ID": "S9", "Location": "Elsewhere Moor", "Latitude": "", "Longitude": ""}
        ),
    ]
    result = ctx.ebird.run(ctx.ebird.preview(write(tmp_path, "d.csv", table(FULL, rows))))
    at_park, elsewhere = (ctx.outings.get(i) for i in result.outings)
    assert at_park.title is None and at_park.display_title.startswith("Invented Park · ")
    assert elsewhere.display_title == "Elsewhere Moor"
    assert (at_park.source, at_park.source_id) == ("ebird", "S100")
