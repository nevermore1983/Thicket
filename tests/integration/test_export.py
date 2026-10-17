"""Exporting: spreadsheet, Darwin Core, map data, WildLife JSON and the full archive."""

import csv
import hashlib
import io
import json
import zipfile
from datetime import date

import pytest

from helpers import jpeg_with_gps, taxon_id
from wildlife.domain.codes import Identification
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import PlaceDraft, SightingDraft
from wildlife.domain.photo_privacy import has_gps
from wildlife.services.export import CSV_COLUMNS, DWC_COLUMNS, ExportOptions


def seed(ctx, tmp_path):
    ctx.settings.update(recorder_name="Sam Recorder")
    place = ctx.places.save(PlaceDraft("Test Park", 51.5, -0.12, radius_m=150))
    robin = ctx.sightings.save(
        SightingDraft(
            taxon_id=taxon_id(ctx, "Erithacus rubecula"),
            observed_date=date(2026, 5, 3),
            observed_time="07:40",
            place_id=place.id,
            latitude=51.50135,
            longitude=-0.14189,
            uncertainty_m=10,
            location_text="By the gate",
            count=2,
            notes="Singing",
        )
    ).sighting
    fox = ctx.sightings.save(
        SightingDraft(
            taxon_id=taxon_id(ctx, "Vulpes vulpes"),
            observed_date=date(2026, 6, 1),
            identification=Identification.PROBABLE,
            count=None,
        )
    ).sighting
    photo = ctx.photos.import_files([jpeg_with_gps(tmp_path / "robin.jpg")]).imported[0]
    ctx.photos.attach(robin.id, [photo.id])
    return robin, fox, photo


def read_csv(data: bytes) -> list[dict]:
    assert data.startswith(b"\xef\xbb\xbf")  # Excel needs the BOM to read UTF-8
    return list(csv.DictReader(io.StringIO(data.decode("utf-8-sig"))))


def export(ctx, tmp_path, name, **kw):
    summary = ctx.export.export(ExportOptions(**kw), tmp_path / "out" / name)
    return summary, summary.path.read_bytes()


@pytest.fixture
def out(tmp_path):
    (tmp_path / "out").mkdir()
    return tmp_path


def test_spreadsheet(ctx, out):
    robin, _, _ = seed(ctx, out)
    summary, data = export(ctx, out, "sightings", format="csv")
    assert summary.path.name == "sightings.csv" and summary.describe() == "2 sightings"
    rows = read_csv(data)
    assert list(rows[0]) == list(CSV_COLUMNS)
    first = rows[0]
    assert (first["Date"], first["Time"], first["Species"], first["Count"]) == (
        "2026-05-03",
        "07:40",
        "Robin",
        "2",
    )
    assert first["Place"] == "Test Park" and first["Location description"] == "By the gate"
    assert first["Grid reference"] == "TQ 2906 7968" and first["Photos"] == "1"
    assert first["WildLife ID"] == robin.uuid and first["Wild"] == "Yes"
    assert rows[1]["Count"] == "" and rows[1]["Identification"] == "Probable"


def test_blurred_locations_hide_the_spot(ctx, out):
    seed(ctx, out)
    _, data = export(ctx, out, "blurred", format="csv", blur_m=1000)
    first = read_csv(data)[0]
    assert first["Grid reference"] == "TQ 29 79" and first["Location blurred"] == "1 km square"
    assert (first["Latitude"], first["Longitude"]) == ("51.49961", "-0.13574")
    assert int(first["Uncertainty (m)"]) >= 708
    assert first["Place"] == "" and first["Location description"] == ""


def test_darwin_core(ctx, out):
    robin, _, _ = seed(ctx, out)
    _, data = export(ctx, out, "dwc", format="dwc", blur_m=10000)
    rows = read_csv(data)
    assert list(rows[0]) == list(DWC_COLUMNS)
    r, fox = rows
    assert (r["occurrenceID"], r["eventDate"], r["scientificName"]) == (
        robin.uuid,
        "2026-05-03T07:40",
        "Erithacus rubecula",
    )
    assert r["taxonID"] == "R1" and r["nameAccordingTo"] == "UK Species Inventory"
    assert r["recordedBy"] == "Sam Recorder" and r["occurrenceStatus"] == "present"
    assert r["dataGeneralizations"].endswith("10 km square TQ27") and r["locality"] == ""
    assert r["individualCount"] == "2" and r["basisOfRecord"] == "HumanObservation"
    assert fox["identificationQualifier"] == "cf." and fox["decimalLatitude"] == ""


def test_map_data_leaves_out_sightings_without_a_location(ctx, out):
    seed(ctx, out)
    summary, data = export(ctx, out, "map", format="geojson")
    features = json.loads(data)["features"]
    assert len(features) == 1 and summary.without_location == 1
    assert features[0]["geometry"]["coordinates"] == [-0.14189, 51.50135]  # longitude first
    assert features[0]["properties"]["species"] == "Robin"


def test_only_the_filtered_sightings(ctx, out):
    seed(ctx, out)
    fox_only = SightingFilter(taxon_ids=frozenset({taxon_id(ctx, "Vulpes vulpes")}))
    summary, data = export(ctx, out, "fox", format="csv", flt=fox_only)
    assert summary.sightings == 1 and read_csv(data)[0]["Species"] == "Red Fox"


def test_shared_photos_have_their_location_removed(ctx, out):
    _, _, photo = seed(ctx, out)
    assert has_gps((ctx.paths.root / photo.rel_path).read_bytes())
    summary, _ = export(ctx, out, "share", format="dwc", with_photos=True)
    assert summary.path.suffix == ".zip" and summary.photos == 1
    with zipfile.ZipFile(summary.path) as z:
        names = z.namelist()
        shared = [n for n in names if n.startswith("photos/")]
        assert shared == ["photos/2026-05-03 Robin 1-1.jpg"]
        assert not has_gps(z.read(shared[0]))
        rows = read_csv(z.read("darwin-core.csv"))
    assert rows[0]["associatedMedia"] == shared[0]
    assert has_gps((ctx.paths.root / photo.rel_path).read_bytes())  # the original is untouched


def test_photos_can_keep_their_location_if_asked(ctx, out):
    seed(ctx, out)
    summary, _ = export(ctx, out, "share", format="csv", with_photos=True, strip_gps=False)
    with zipfile.ZipFile(summary.path) as z:
        assert has_gps(z.read(next(n for n in z.namelist() if n.startswith("photos/"))))


def test_full_archive(ctx, out):
    robin, _, photo = seed(ctx, out)
    summary, _ = export(ctx, out, "everything", format="archive")
    with zipfile.ZipFile(summary.path) as z:
        names = set(z.namelist())
        assert {"wildlife-export.json", "sightings.csv", "darwin-core.csv", "README.txt"} <= names
        assert photo.rel_path in names
        library = (ctx.paths.root / photo.rel_path).read_bytes()
        assert z.read(photo.rel_path) == library  # exact, location and all
        data = json.loads(z.read("wildlife-export.json"))
    assert data["format"] == "wildlife-export" and data["complete"] is True
    assert hashlib.sha256(library).hexdigest() == data["photos"][0]["sha256"]
    assert data["photos"][0]["file"] == photo.rel_path
    sighting = next(s for s in data["sightings"] if s["uuid"] == robin.uuid)
    assert sighting["photos"] == [photo.uuid] and sighting["taxon"]["uksi_key"] == "R1"
    assert sighting["place"] == data["places"][0]["uuid"]


def test_nothing_half_written_is_left_behind(ctx, out, monkeypatch):
    seed(ctx, out)
    from wildlife.services import export as module

    def broken(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(module, "_write_csv", broken)
    with pytest.raises(OSError):
        export(ctx, out, "fails", format="csv")
    assert list((out / "out").iterdir()) == []


def test_text_that_looks_like_a_formula_stays_text(ctx, out):
    """Excel runs a cell starting with = + - or @ as a formula. A leading ' keeps it text;
    numbers (a negative longitude) are left as numbers."""
    for notes in ('=HYPERLINK("http://example.com","Click")', "+44 seen", "-ish", "@home"):
        ctx.sightings.save(
            SightingDraft(
                taxon_id(ctx, "Erithacus rubecula"),
                date(2026, 5, 3),
                notes=notes,
                latitude=51.5,
                longitude=-0.12,
                uncertainty_m=10,
            )
        )
    for fmt in ("csv", "dwc"):
        _, data = export(ctx, out, f"formulas-{fmt}", format=fmt)
        rows = read_csv(data)
        notes = {r["Notes" if fmt == "csv" else "occurrenceRemarks"] for r in rows}
        assert notes == {
            '\'=HYPERLINK("http://example.com","Click")',
            "'+44 seen",
            "'-ish",
            "'@home",
        }
        longitude = rows[0]["Longitude" if fmt == "csv" else "decimalLongitude"]
        assert longitude.startswith("-0.12")  # a number, not made into text
