"""Phase 9: RAW + JPEG, folders, the Inbox, the Library, the recycle bin and missing files."""

import shutil
from datetime import UTC, datetime
from pathlib import Path

import pytest
from PIL import Image

from helpers import TODAY, taxon_id
from wildlife.domain.errors import PhotoError
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import SightingDraft
from wildlife.services.photos import open_image, read_info

FIXTURES = Path(__file__).parents[1] / "fixtures" / "photos"
STEM = "PXL_20261011_071530123"


def pixel_pair(
    folder: Path, stem: str = STEM, jpeg_source: str = "sample.jpg"
) -> tuple[Path, Path]:
    """A Pixel-style RAW + JPEG pair made from the fixtures."""
    folder.mkdir(parents=True, exist_ok=True)
    jpg = folder / f"{stem}.RAW-01.COVER.jpg"
    dng = folder / f"{stem}.RAW-02.ORIGINAL.dng"
    shutil.copy(FIXTURES / jpeg_source, jpg)
    shutil.copy(FIXTURES / "sample.dng", dng)
    return jpg, dng


def add_sighting(ctx, **kw):
    return ctx.sightings.save(
        SightingDraft(taxon_id=taxon_id(ctx, "Erithacus rubecula"), observed_date=TODAY, **kw)
    ).sighting


# ---- RAW files --------------------------------------------------------------------
def test_raw_file_details_are_read():
    info = read_info(FIXTURES / "sample.dng")
    assert (info.width, info.height) == (64, 48)
    assert info.taken_at == "2026-10-11 08:15:30" and info.taken_source == "exif"
    assert info.camera == "Google Pixel 10 Pro"
    assert info.latitude == pytest.approx(51.4955, abs=1e-4)
    assert info.longitude == pytest.approx(0.1975, abs=1e-4)


def test_raw_file_can_be_shown():
    image = open_image(FIXTURES / "sample.dng", rotation=90, max_size=256)
    assert image.mode == "RGB" and image.size == (48, 64)  # rendered, then turned


def test_raw_and_jpeg_pair_become_one_photo(ctx, tmp_path):
    jpg, dng = pixel_pair(tmp_path / "DCIM")
    summary = ctx.photos.import_files([dng, jpg])
    assert len(summary.imported) == 1 and summary.raw_paired == 1
    photo = summary.imported[0]
    assert photo.original_name == jpg.name and photo.raw_name == dng.name
    assert photo.has_raw and not photo.is_raw and photo.raw_size == dng.stat().st_size
    assert ctx.photos.raw_path_of(photo).read_bytes() == dng.read_bytes()
    assert summary.describe() == "1 imported · 1 RAW original kept"


def test_folder_import_finds_photos_in_sub_folders(ctx, tmp_path):
    pixel_pair(tmp_path / "DCIM" / "Camera")
    shutil.copy(FIXTURES / "sample.heic", tmp_path / "DCIM" / "IMG_0002.HEIC")
    (tmp_path / "DCIM" / "notes.txt").write_text("not a photo")
    (tmp_path / "DCIM" / "clip.mp4").write_bytes(b"video")
    summary = ctx.photos.import_files([tmp_path / "DCIM"])
    assert len(summary.imported) == 2 and summary.raw_paired == 1 and summary.skipped == 2


def test_raw_on_its_own_is_a_photo(ctx):
    summary = ctx.photos.import_files([FIXTURES / "sample.dng"])
    photo = summary.imported[0]
    assert photo.is_raw and photo.has_raw and photo.camera == "Google Pixel 10 Pro"
    thumb = ctx.photos.thumbnail(photo)
    assert thumb is not None
    with Image.open(thumb) as im:
        assert im.size == (64, 48)


def test_raw_arriving_later_joins_its_photo(ctx, tmp_path):
    jpg, dng = pixel_pair(tmp_path)
    first = ctx.photos.import_files([jpg])
    later = ctx.photos.import_files([jpg, dng])  # the whole pair copied over again
    assert later.raw_paired == 1 and len(later.duplicates) == 1
    assert ctx.photos.get(first.imported[0].id).has_raw
    again = ctx.photos.import_files([jpg, dng])
    assert again.raw_paired == 0 and len(again.duplicates) == 1


def test_storage_saver_jpeg_named_dng_still_imports(ctx, tmp_path):
    """Google Photos' storage saver can return a JPEG still named .dng."""
    fake = tmp_path / "PXL_20261011_071530123.RAW-02.ORIGINAL.dng"
    shutil.copy(FIXTURES / "sample.jpg", fake)
    photo = ctx.photos.import_files([fake]).imported[0]
    assert photo.taken_at == "2026-10-10 10:42:07"  # EXIF read from the JPEG inside
    assert ctx.photos.thumbnail(photo) is not None


def test_date_from_pixel_file_name_when_exif_is_missing(ctx, tmp_path):
    shared = tmp_path / "PXL_20260711_081530123.jpg"
    shutil.copy(FIXTURES / "no_exif.jpg", shared)  # e.g. sent through a messaging app
    photo = ctx.photos.import_files([shared]).imported[0]
    local = datetime(2026, 7, 11, 8, 15, 30, tzinfo=UTC).astimezone()
    assert photo.taken_at == local.strftime("%Y-%m-%d %H:%M:%S")
    assert photo.taken_source == "file_name"
    assert photo.rel_path.startswith("photos/2026/07/")


def test_backups_include_raw_originals(ctx, tmp_path):
    jpg, dng = pixel_pair(tmp_path)
    ctx.photos.import_files([jpg, dng])
    ctx.settings.update(backup_folder=str(tmp_path / "backups"))
    result = ctx.backup.backup_now("manual")
    copies = [p.name for p in (tmp_path / "backups").rglob("*.dng")]
    assert result.photos_copied == 2 and len(copies) == 1


# ---- Inbox and Library ---------------------------------------------------------------
def test_inbox_and_library(ctx, tmp_path):
    jpg, dng = pixel_pair(tmp_path)
    a, b = ctx.photos.import_files([jpg, dng, FIXTURES / "sample.heic"]).imported
    assert {p.id for p in ctx.photos.inbox()} == {a.id, b.id}
    robin = add_sighting(ctx)
    fox = ctx.sightings.save(
        SightingDraft(taxon_id=taxon_id(ctx, "Vulpes vulpes"), observed_date=TODAY)
    ).sighting
    ctx.photos.attach(robin.id, [a.id])
    ctx.photos.attach(fox.id, [b.id])
    assert ctx.photos.inbox_count() == 0
    everything = ctx.photos.library(SightingFilter())
    assert {i.photo.id for i in everything} == {a.id, b.id}
    birds = ctx.photos.library(SightingFilter(category_ids=frozenset({1})))
    assert [(i.photo.id, i.name) for i in birds] == [(a.id, "Robin")]


def test_photos_of_a_deleted_sighting_stay_out_of_the_inbox(ctx):
    photo = ctx.photos.import_files([FIXTURES / "sample.jpg"]).imported[0]
    s = add_sighting(ctx)
    ctx.photos.attach(s.id, [photo.id])
    ctx.sightings.delete([s.id])
    assert ctx.photos.inbox_count() == 0  # in the recycle bin with its sighting
    assert ctx.photos.library(SightingFilter()) == []


def test_cover_rotation_and_caption(ctx):
    a, b = ctx.photos.import_files([FIXTURES / "sample.jpg", FIXTURES / "sample.heic"]).imported
    s = add_sighting(ctx)
    ctx.photos.attach(s.id, [a.id, b.id])
    ctx.photos.make_cover(s.id, b.id)
    assert [p.id for p in ctx.photos.for_sighting(s.id)] == [b.id, a.id]
    assert ctx.sightings.get(s.id).cover_photo == b.rel_path
    turned = ctx.photos.rotate(a.id)
    assert turned.rotation == 90 and ctx.photos.rotate(a.id, 270).rotation == 0
    ctx.photos.set_caption(a.id, "  Singing from the hawthorn ")
    assert ctx.photos.get(a.id).caption == "Singing from the hawthorn"
    ctx.photos.set_caption(a.id, "")
    assert ctx.photos.get(a.id).caption is None


def test_rotated_thumbnails_are_cached_separately(ctx):
    photo = ctx.photos.import_files([FIXTURES / "sample.jpg"]).imported[0]
    upright = ctx.photos.thumbnail(photo)
    turned = ctx.photos.thumbnail(ctx.photos.rotate(photo.id))
    assert upright != turned
    with Image.open(upright) as up, Image.open(turned) as down:
        assert up.size[::-1] == down.size
    assert ctx.photos.screen_image(photo) is not None


# ---- recycle bin --------------------------------------------------------------------
def test_delete_undo_and_purge_removes_files(ctx, tmp_path):
    jpg, dng = pixel_pair(tmp_path)
    photo = ctx.photos.import_files([jpg, dng]).imported[0]
    s = add_sighting(ctx)
    ctx.photos.attach(s.id, [photo.id])
    ctx.photos.thumbnail(photo)
    undo = ctx.photos.delete([photo.id])
    assert ctx.photos.for_sighting(s.id) == [] and ctx.photos.inbox_count() == 0
    undo.run()
    assert [p.id for p in ctx.photos.for_sighting(s.id)] == [photo.id]
    ctx.photos.delete([photo.id])
    files = [ctx.photos.path_of(photo), ctx.photos.raw_path_of(photo)]
    assert ctx.photos.purge_recycle_bin(older_than_days=1) == 0  # not old enough
    assert ctx.photos.purge_recycle_bin(older_than_days=0) == 1
    assert not any(f.exists() for f in files)
    assert not list(ctx.paths.thumbnails.rglob(f"{photo.sha256}_*"))


def test_purging_a_sighting_removes_photos_no_one_else_uses(ctx):
    only_robin, shared = ctx.photos.import_files(
        [FIXTURES / "sample.jpg", FIXTURES / "sample.heic"]
    ).imported
    robin, other = add_sighting(ctx), add_sighting(ctx)
    ctx.photos.attach(robin.id, [only_robin.id, shared.id])
    ctx.photos.attach(other.id, [shared.id])
    ctx.sightings.delete([robin.id])
    ctx.sightings.purge_recycle_bin(older_than_days=0)
    ctx.photos.purge_recycle_bin(older_than_days=0)
    assert not ctx.photos.path_of(only_robin).exists()
    assert ctx.photos.path_of(shared).exists()  # still on the other sighting
    assert ctx.photos.inbox_count() == 0


def test_importing_a_photo_from_the_recycle_bin_brings_it_back(ctx):
    """It used to say "already in your library" and stay hidden in the bin, so attaching
    it to a sighting showed nothing, and it was deleted for good 30 days later."""
    photo = ctx.photos.import_files([FIXTURES / "sample.jpg"]).imported[0]
    ctx.photos.delete([photo.id])
    again = ctx.photos.import_files([FIXTURES / "sample.jpg"])
    assert [p.id for p in again.imported] == [photo.id] and again.duplicates == []
    assert [p.id for p in ctx.photos.inbox()] == [photo.id]
    assert ctx.photos.recycle_bin() == []
    s = add_sighting(ctx)
    ctx.photos.attach(s.id, [photo.id])
    assert [p.id for p in ctx.photos.for_sighting(s.id)] == [photo.id]


# ---- missing files -----------------------------------------------------------------
def test_importing_a_photo_again_puts_back_its_missing_file(ctx):
    photo = ctx.photos.import_files([FIXTURES / "sample.jpg"]).imported[0]
    ctx.photos.path_of(photo).unlink()  # deleted outside WildLife
    again = ctx.photos.import_files([FIXTURES / "sample.jpg"])
    assert [p.id for p in again.duplicates] == [photo.id]  # the same photo, not a new one
    assert ctx.photos.missing() == []


def test_missing_file_is_found_and_can_be_located(ctx, tmp_path):
    photo = ctx.photos.import_files([FIXTURES / "sample.jpg"]).imported[0]
    ctx.photos.path_of(photo).unlink()
    assert [p.id for p in ctx.photos.missing()] == [photo.id]
    with pytest.raises(PhotoError):
        ctx.photos.locate(photo.id, FIXTURES / "sample.heic")  # a different photo
    ctx.photos.locate(photo.id, FIXTURES / "sample.jpg")
    assert ctx.photos.missing() == [] and ctx.photos.thumbnail(photo) is not None


def test_camera_clock_correction_with_undo(ctx, tmp_path):
    from helpers import jpeg_with_gps

    photo = ctx.photos.import_files([jpeg_with_gps(tmp_path / "a.jpg")]).imported[0]
    with ctx.db.transaction() as conn:
        conn.execute("UPDATE photo SET taken_at = '2026-03-29 00:30:00' WHERE id = ?", (photo.id,))
    undo = ctx.photos.shift_times([photo.id], 90)
    moved = ctx.photos.get(photo.id)
    assert (moved.taken_at, moved.taken_source) == ("2026-03-29 02:00:00", "manual")
    undo.run()
    assert ctx.photos.get(photo.id).taken_at == "2026-03-29 00:30:00"
