"""Importing eBird exports end to end, from invented rows (helpers.ebird_full_row, ebird_life_row)."""

from helpers import EBIRD_FULL as FULL
from helpers import EBIRD_LIFE as LIFE
from helpers import ebird_full_row as full_row
from helpers import ebird_life_row as life_row
from helpers import ebird_table as table
from helpers import taxon_id
from wildlife.domain.models import PlaceDraft
from wildlife.services.importer import ADD, SAME


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
    assert [r.action for r in plan.rows] == [SAME, ADD]  # the life list's Robin is already in
    again = ctx.ebird.preview(write(tmp_path, "life2.csv", life))
    assert [r.action for r in again.rows] == [SAME]


def test_a_hotspot_without_a_position_uses_your_place_of_that_name(ctx, tmp_path):
    reserve = ctx.places.save(PlaceDraft("Invented Reserve", 52.5, -1.5))
    row = life_row(Location="Invented Reserve")
    result = ctx.ebird.run(ctx.ebird.preview(write(tmp_path, "list.csv", table(LIFE, [row]))))
    sighting = ctx.sightings.get(result.added[0])
    assert sighting.place_id == reserve.id and sighting.latitude is None


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
