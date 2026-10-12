"""Importing spreadsheets: duplicates, places, and round trips through WildLife's exports."""

from datetime import date

from helpers import taxon_id
from wildlife.domain.codes import CountQualifier, Habitat, Identification
from wildlife.domain.csv_import import guess_mapping
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import PlaceDraft, SightingDraft
from wildlife.services.export import ExportOptions
from wildlife.services.importer import ADD, SAME, SKIP

FIELDS = (
    "taxon_id",
    "observed_date",
    "observed_time",
    "latitude",
    "longitude",
    "uncertainty_m",
    "count",
    "count_qualifier",
    "identification",
    "habitat",
    "is_not_wild",
    "notes",
)


def plan_for(ctx, tmp_path, text, name="records.csv"):
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    table = ctx.spreadsheet.read(path)
    return ctx.spreadsheet.preview(table, guess_mapping(table.header))


def test_import_with_saved_places_and_duplicates(ctx, tmp_path):
    ctx.places.save(PlaceDraft("Garden", 51.4, 0.1))
    ctx.sightings.save(
        SightingDraft(taxon_id(ctx, "Erithacus rubecula"), date(2026, 5, 3), "07:40")
    )
    plan = plan_for(
        ctx,
        tmp_path,
        "Species,Date,Time,Place,Count\n"
        "Robin,03/05/2026,07:40,,1\n"  # already have it
        "Red Fox,04/05/2026,,Garden,2\n"
        "Red Fox,04/05/2026,,Garden,2\n"  # the same row twice
        "Herring Gull,05/05/2026,,Beach car park,\n"
        "Robin,05/05/2030,,,\n",
    )
    assert [r.action for r in plan.rows] == [SAME, ADD, SAME, ADD, SKIP]
    assert plan.rows[4].reason == "The date is in the future"
    result = ctx.spreadsheet.run(plan)
    fox, gull = (ctx.sightings.get(i) for i in result.added)
    assert fox.place_name == "Garden" and fox.count == 2
    assert gull.place_name is None and gull.location_text == "Beach car park"
    assert gull.count is None  # not counted: nothing invented
    assert fox.source == "csv" and fox.source_id is None


def test_round_trip_through_the_spreadsheet_export(ctx, tmp_path):
    """Export → import into an empty library gives the same sightings back."""
    robin = ctx.sightings.save(
        SightingDraft(
            taxon_id(ctx, "Erithacus rubecula"),
            date(2026, 5, 3),
            "07:40",
            latitude=51.50135,
            longitude=-0.14189,
            uncertainty_m=10,
            count=20,
            count_qualifier=CountQualifier.APPROX,
            identification=Identification.PROBABLE,
            habitat=Habitat.WOODLAND,
            is_not_wild=True,
            notes="Line one\nLine two, with “quotes”",
        )
    ).sighting
    for fmt in ("csv", "dwc"):
        out = ctx.export.export(ExportOptions(fmt), tmp_path / f"export-{fmt}")
        ctx.sightings.delete([s.id for s in ctx.sightings.page(SightingFilter())])
        ctx.sightings.purge_recycle_bin(0)
        table = ctx.spreadsheet.read(out.path)
        result = ctx.spreadsheet.run(ctx.spreadsheet.preview(table, guess_mapping(table.header)))
        back = ctx.sightings.get(result.added[0]).to_draft()
        before = robin.to_draft()
        # Darwin Core has no "approximate" count
        same = FIELDS if fmt == "csv" else tuple(f for f in FIELDS if f != "count_qualifier")
        assert {f: getattr(back, f) for f in same} == {f: getattr(before, f) for f in same}, fmt


def test_import_history_shows_and_removes_an_import(ctx, tmp_path):
    result = ctx.spreadsheet.run(
        plan_for(ctx, tmp_path, "Species,Date\nRobin,03/05/2026\nRed Fox,04/05/2026\n")
    )
    (batch,) = ctx.import_history.batches()
    assert (batch.source, batch.file_name, batch.added, batch.live) == ("csv", "records.csv", 2, 2)
    undo = ctx.import_history.remove(batch.id)
    assert ctx.import_history.batches()[0].live == 0
    assert ctx.sightings.totals(SightingFilter())[0] == 0
    undo.run()
    assert ctx.sightings.totals(SightingFilter(import_batch_id=result.batch_id))[0] == 2
