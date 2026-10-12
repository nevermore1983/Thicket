"""WildLife's own export, imported again: into an empty library, twice, with Undo."""

import json
import shutil
import zipfile
from datetime import date
from pathlib import Path

import pytest

from helpers import MINI_CATALOGUE, TODAY, jpeg_with_gps, taxon_id
from wildlife.config.paths import DataPaths
from wildlife.context import AppContext
from wildlife.data.repositories import taxa as taxa_repo
from wildlife.domain.codes import Evidence, Weather
from wildlife.domain.errors import ImportFileError
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import OutingDraft, PlaceDraft, SightingDraft
from wildlife.services.export import ExportOptions

SAMPLE_DNG = Path(__file__).parents[1] / "fixtures" / "photos" / "sample.dng"


@pytest.fixture
def other(tmp_path):
    """A second, empty library (like a new PC)."""
    ctx = AppContext.open(DataPaths(tmp_path / "Other").ensure())
    with ctx.db.transaction() as conn:
        taxa_repo.install_catalogue(conn, MINI_CATALOGUE)
    ctx.set_today(TODAY)
    yield ctx
    ctx.close()


def seed(ctx, tmp_path):
    place = ctx.places.save(PlaceDraft("Test Park", 51.5, -0.12, radius_m=150))
    outing, _ = ctx.outings.save(
        OutingDraft(date(2026, 5, 3), "07:00", "09:00", place.id, "Dawn walk", Weather.SUNNY)
    )
    robin = ctx.sightings.save(
        SightingDraft(
            taxon_id(ctx, "Erithacus rubecula"),
            date(2026, 5, 3),
            "07:40",
            place_id=place.id,
            outing_id=outing.id,
            count=3,
            evidence=Evidence.HEARD,
            notes="Singing",
        )
    ).sighting
    with ctx.db.transaction() as conn:  # a species that only exists in this library
        conn.execute(
            "INSERT INTO taxon (scientific_name, common_name, rank, category_id, is_custom) "
            "VALUES ('Mysteria nova', 'Garden mystery', 'species', 7, 1)"
        )
        mystery = conn.execute("SELECT id FROM taxon WHERE is_custom = 1").fetchone()[0]
    ctx.sightings.save(SightingDraft(mystery, date(2026, 6, 1)))
    jpeg = jpeg_with_gps(tmp_path / "robin.jpg")
    photo = ctx.photos.import_files([jpeg]).imported[0]
    ctx.photos.add_raw(photo.id, shutil.copy(SAMPLE_DNG, tmp_path / "robin.dng"))
    ctx.photos.rotate(photo.id, 90)
    ctx.photos.set_caption(photo.id, "Front garden")
    ctx.photos.attach(robin.id, [photo.id])
    return robin, photo


def snapshot(ctx):
    """Everything that should survive the trip, without the library's own row ids."""
    with ctx.db.connection() as conn:
        sightings = conn.execute(
            """SELECT s.uuid, t.scientific_name, s.observed_date, s.observed_time, s.count,
                      s.evidence, s.notes, s.created_at, p.uuid, o.uuid
               FROM sighting s JOIN taxon t ON t.id = s.taxon_id
               LEFT JOIN place p ON p.id = s.place_id LEFT JOIN outing o ON o.id = s.outing_id
               ORDER BY s.uuid"""
        ).fetchall()
        places = conn.execute("SELECT uuid, name, latitude, radius_m FROM place").fetchall()
        outings = conn.execute(
            "SELECT uuid, outing_date, start_time, end_time, title, weather FROM outing"
        ).fetchall()
        photos = conn.execute(
            """SELECT p.uuid, p.sha256, p.raw_sha256, p.rotation, p.caption, s.uuid
               FROM photo p JOIN sighting_photo sp ON sp.photo_id = p.id
               JOIN sighting s ON s.id = sp.sighting_id"""
        ).fetchall()
    return [list(map(tuple, x)) for x in (sightings, places, outings, photos)]


def test_round_trip_into_an_empty_library(ctx, other, tmp_path):
    seed(ctx, tmp_path)
    archive = ctx.export.export(ExportOptions("archive"), tmp_path / "everything").path
    plan = other.wildlife_import.preview(archive)
    assert (plan.new_sightings, plan.new_places, plan.new_outings, plan.photos_to_add) == (
        2,
        1,
        1,
        1,
    )
    assert plan.new_species == ["Garden mystery"]
    result = other.wildlife_import.run(plan)
    assert result.describe() == "2 added · 1 photos"
    assert snapshot(other) == snapshot(ctx)
    photo = other.photos.for_sighting(result.added[0])[0]
    assert photo.has_raw and (other.paths.root / photo.raw_rel_path).exists()
    again = other.wildlife_import.preview(archive)
    assert again.new_sightings == 0 and again.already == 2


def test_json_only_brings_the_records(ctx, other, tmp_path):
    seed(ctx, tmp_path)
    path = ctx.export.export(ExportOptions("json"), tmp_path / "records").path
    plan = other.wildlife_import.preview(path)
    assert plan.photos_to_add == 0 and plan.photos_missing == 1
    other.wildlife_import.run(plan)
    assert other.sightings.totals(SightingFilter())[0] == 2


def test_undo_removes_everything_the_import_added(ctx, other, tmp_path):
    seed(ctx, tmp_path)
    archive = ctx.export.export(ExportOptions("archive"), tmp_path / "everything").path
    result = other.wildlife_import.run(other.wildlife_import.preview(archive))
    result.undo.run()
    with other.db.connection() as conn:
        counts = [
            conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("sighting", "place", "outing", "import_batch")
        ]
        custom = conn.execute("SELECT COUNT(*) FROM taxon WHERE is_custom = 1").fetchone()[0]
    assert counts == [0, 0, 0, 0] and custom == 0
    assert len(other.photos.recycle_bin()) == 1


def test_other_files_are_refused(other, tmp_path):
    wrong = tmp_path / "x.json"
    wrong.write_text(json.dumps({"hello": 1}), encoding="utf-8")
    with pytest.raises(ImportFileError, match="isn't a WildLife export"):
        other.wildlife_import.preview(wrong)
    newer = tmp_path / "newer.json"
    newer.write_text(json.dumps({"format": "wildlife-export", "format_version": 99}))
    with pytest.raises(ImportFileError, match="newer version"):
        other.wildlife_import.preview(newer)
    zipped = tmp_path / "x.zip"
    with zipfile.ZipFile(zipped, "w") as z:
        z.writestr("notes.txt", "hi")
    with pytest.raises(ImportFileError, match=r"no wildlife-export\.json"):
        other.wildlife_import.preview(zipped)


def test_archive_paths_cant_escape_the_library(ctx, other, tmp_path):
    """A doctored archive naming '../..' files must not write outside WildLife's folders."""
    seed(ctx, tmp_path)
    archive = ctx.export.export(ExportOptions("archive"), tmp_path / "everything").path
    with zipfile.ZipFile(archive) as z:
        data = json.loads(z.read("wildlife-export.json"))
        files = {n: z.read(n) for n in z.namelist() if n.startswith("photos/")}
    data["photos"][0]["original_name"] = "../../../evil.jpg"
    doctored = tmp_path / "doctored.zip"
    with zipfile.ZipFile(doctored, "w") as z:
        z.writestr("wildlife-export.json", json.dumps(data))
        for name, blob in files.items():
            z.writestr(name, blob)
    other.wildlife_import.run(other.wildlife_import.preview(doctored))
    assert (
        not (tmp_path / "evil.jpg").exists() and not (other.paths.root.parent / "evil.jpg").exists()
    )
