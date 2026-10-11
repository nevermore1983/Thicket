import json
import shutil
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from helpers import TODAY, taxon_id
from wildlife.domain.errors import BackupError
from wildlife.domain.models import SightingDraft
from wildlife.services.photos import read_info

FIXTURES = Path(__file__).parents[1] / "fixtures" / "photos"


def test_read_info_from_heic_and_jpeg():
    for name in ("sample.heic", "sample.jpg"):
        info = read_info(FIXTURES / name)
        assert (info.width, info.height) == (300, 400)  # upright after rotation
        assert info.taken_at == "2026-10-10 10:42:07"
        assert info.latitude == pytest.approx(51.4955, abs=1e-4)
        assert info.longitude == pytest.approx(0.1975, abs=1e-4)
        assert info.gps_accuracy_m == pytest.approx(4.7)
        assert info.camera == "Apple iPhone 16"


def test_photo_without_exif_still_imports(ctx):
    summary = ctx.photos.import_files([FIXTURES / "no_exif.jpg"])
    assert len(summary.imported) == 1 and summary.imported[0].taken_at is None


def test_import_copies_into_library_and_skips_duplicates(ctx, tmp_path):
    copy = tmp_path / "IMG_0001.HEIC"
    shutil.copy(FIXTURES / "sample.heic", copy)
    first = ctx.photos.import_files([FIXTURES / "sample.heic", FIXTURES / "sample.jpg"])
    again = ctx.photos.import_files([copy])
    assert len(first.imported) == 2 and not first.failed
    assert len(again.imported) == 0 and len(again.duplicates) == 1  # same image, different name
    photo = first.imported[0]
    assert photo.rel_path.startswith("photos/2026/10/") and ctx.photos.path_of(photo).exists()
    assert ctx.photos.inbox_count() == 2  # not attached to a sighting yet


def test_bad_files_are_reported_not_fatal(ctx, tmp_path):
    notes = tmp_path / "notes.txt"
    notes.write_text("hello")
    summary = ctx.photos.import_files([FIXTURES / "corrupt.jpg", notes, FIXTURES / "sample.jpg"])
    assert len(summary.imported) == 1
    assert {name for name, _ in summary.failed} == {"corrupt.jpg", "notes.txt"}


def test_attach_and_detach(ctx):
    photo = ctx.photos.import_files([FIXTURES / "sample.jpg"]).imported[0]
    s = ctx.sightings.save(
        SightingDraft(taxon_id=taxon_id(ctx, "Erithacus rubecula"), observed_date=TODAY)
    )
    ctx.photos.attach(s.sighting.id, [photo.id])
    assert [p.id for p in ctx.photos.for_sighting(s.sighting.id)] == [photo.id]
    assert ctx.sightings.get(s.sighting.id).photo_count == 1
    assert ctx.photos.inbox_count() == 0
    ctx.photos.detach(s.sighting.id, [photo.id])
    assert ctx.photos.inbox_count() == 1


def test_thumbnail_is_made_once_and_upright(ctx):
    photo = ctx.photos.import_files([FIXTURES / "sample.jpg"]).imported[0]
    thumb = ctx.photos.thumbnail(photo, 256)
    assert thumb is not None and thumb.suffix == ".webp"
    from PIL import Image

    with Image.open(thumb) as im:
        assert im.height > im.width  # portrait, i.e. the EXIF rotation was applied
    assert ctx.photos.thumbnail(photo, 256) == thumb


def test_missing_original_gives_no_thumbnail(ctx):
    photo = ctx.photos.import_files([FIXTURES / "sample.jpg"]).imported[0]
    ctx.photos.path_of(photo).unlink()
    assert ctx.photos.thumbnail(photo, 1024) is None


# ---- backups ----------------------------------------------------------------
def test_backup_snapshot_manifest_and_photo_mirror(ctx):
    ctx.photos.import_files([FIXTURES / "sample.jpg"])
    ctx.sightings.save(
        SightingDraft(taxon_id=taxon_id(ctx, "Erithacus rubecula"), observed_date=TODAY)
    )
    result = ctx.backup.backup_now("manual")
    assert result.ok and result.sightings == 1 and result.photos_copied == 1
    snap = Path(result.snapshot)
    manifest = json.loads(snap.with_suffix(".json").read_text())
    assert manifest["integrity"] == "ok" and manifest["counts"]["sighting"] == 1
    assert ctx.backup.last_result().ok
    assert ctx.backup.backup_now("manual").photos_copied == 0  # photos only copied once


def test_backup_to_missing_drive_fails_clearly(ctx):
    ctx.settings.update(backup_folder="Z:\\definitely\\not\\here")
    with pytest.raises(BackupError) as err:
        ctx.backup.backup_now()
    assert "drive connected" in err.value.user_message
    assert ctx.backup.last_result().ok is False


def test_backup_is_due_daily_and_after_failures(ctx):
    assert ctx.backup.is_due()
    ctx.backup.backup_now("auto")
    assert not ctx.backup.is_due()
    assert ctx.backup.is_due(now=datetime.now(UTC) + timedelta(hours=25))
    ctx.settings.update(auto_backup=False)
    assert not ctx.backup.is_due()


def test_backup_needed_on_exit_only_after_changes(ctx):
    ctx.backup.backup_now("auto")
    assert not ctx.backup.needed_on_exit()
    ctx.sightings.save(
        SightingDraft(taxon_id=taxon_id(ctx, "Erithacus rubecula"), observed_date=TODAY)
    )
    assert ctx.backup.needed_on_exit()


def test_rotation_keeps_daily_weekly_monthly_and_manual(ctx):
    folder = ctx.backup.folder() / "snapshots"
    folder.mkdir(parents=True)
    start = datetime(2026, 10, 11)
    for d in range(400):  # a year+ of daily automatic snapshots
        day = start - timedelta(days=d)
        (folder / f"{day:%Y-%m-%d}_090000_auto.db").write_bytes(b"x")
    (folder / "2025-01-01_120000_manual.db").write_bytes(b"x")
    ctx.backup._rotate(folder)
    kept = sorted(p.stem for p in folder.glob("*.db"))
    assert "2025-01-01_120000_manual" in kept
    assert all(f"2026-10-{d:02d}_090000_auto" in kept for d in range(5, 12))  # last 7 days
    assert len(kept) <= 1 + 7 + 4 + 12
