"""The health check: findings in plain words, and the fixes it offers."""

from datetime import date

from helpers import jpeg_with_gps, taxon_id
from wildlife.domain.models import SightingDraft
from wildlife.services.health import OK, PROBLEM, WARNING


def titles(report):
    return {f.title: f for f in report.findings}


def library_with_a_photo(ctx, tmp_path):
    robin = ctx.sightings.save(
        SightingDraft(taxon_id(ctx, "Erithacus rubecula"), date(2026, 5, 3))
    ).sighting
    photo = ctx.photos.import_files([jpeg_with_gps(tmp_path / "robin.jpg")]).imported[0]
    ctx.photos.attach(robin.id, [photo.id])
    return photo


def test_a_healthy_library(ctx, tmp_path):
    library_with_a_photo(ctx, tmp_path)
    ctx.backup.backup_now("manual")
    found = titles(ctx.health.check())
    assert found["Your data file is sound"].level == OK
    assert found["Every photo file is in place (1)"].level == OK
    assert found["Backups are up to date"].level == OK
    # the default backup folder is on the same drive: worth a warning, not a problem
    assert found["Backups are on the same drive as your data"].level == WARNING


def test_missing_photos_come_back_from_the_backup(ctx, tmp_path):
    photo = library_with_a_photo(ctx, tmp_path)
    ctx.backup.backup_now("manual")
    (ctx.paths.root / photo.rel_path).unlink()
    report = ctx.health.check()
    missing = titles(report)["1 photo file is missing"]
    assert report.worst == PROBLEM and missing.action == "restore_photos"
    assert missing.items == (photo.rel_path,)
    assert ctx.health.bring_back_photos() == 1
    assert "Every photo file is in place (1)" in titles(ctx.health.check())


def test_strange_files_are_reported_never_deleted(ctx, tmp_path):
    library_with_a_photo(ctx, tmp_path)
    stray = ctx.paths.photos / "2026" / "stray.jpg"
    stray.parent.mkdir(parents=True, exist_ok=True)
    stray.write_bytes(b"x")
    partial = ctx.paths.photos / "2026" / "abc.jpg.part"
    partial.write_bytes(b"x")
    found = titles(ctx.health.check())
    assert found["1 file in the photo folder isn't in your library"].items == (
        "photos/2026/stray.jpg",
    )
    assert found["1 unfinished copy in the photo folder"].action == "remove_partial"
    assert ctx.health.remove_partial() == 1
    assert stray.exists() and not partial.exists()


def test_no_backup_yet_is_a_problem(ctx):
    found = titles(ctx.health.check())
    assert found["No working backup"].level == PROBLEM
    assert found["No working backup"].action == "backup_now"


def test_thumbnails_can_be_cleared(ctx, tmp_path):
    photo = library_with_a_photo(ctx, tmp_path)
    ctx.photos.thumbnail(photo)
    assert ctx.health.clear_thumbnails() >= 1
    assert titles(ctx.health.check())  # still runs with an empty cache
