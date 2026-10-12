"""Restoring a backup: requested while running, applied at the next start."""

from datetime import date

import pytest

from helpers import TODAY, jpeg_with_gps, taxon_id
from wildlife.context import AppContext
from wildlife.data.restore import apply_pending_restore, pending
from wildlife.domain.errors import BackupError
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import SightingDraft


def add(ctx, name="Erithacus rubecula", day=date(2026, 5, 3)):
    return ctx.sightings.save(SightingDraft(taxon_id(ctx, name), day)).sighting


def test_restore_brings_back_the_backup_and_its_photos(ctx, paths, tmp_path):
    robin = add(ctx)
    photo = ctx.photos.import_files([jpeg_with_gps(tmp_path / "robin.jpg")]).imported[0]
    ctx.photos.attach(robin.id, [photo.id])
    ctx.backup.backup_now("manual")
    backup = ctx.backup.backups()[0]
    assert (backup.sightings, backup.photos, backup.kind) == (1, 1, "manual")

    add(ctx, "Vulpes vulpes")  # made after the backup: goes away
    (paths.root / photo.rel_path).unlink()  # a lost photo file: comes back from the mirror
    ctx.backup.request_restore(backup.path)
    assert pending(paths) == backup.path
    ctx.close()

    outcome = apply_pending_restore(paths)
    assert outcome.ok and outcome.photos_copied == 1 and outcome.safety_copy.exists()
    assert pending(paths) is None and (paths.root / photo.rel_path).exists()
    again = AppContext.open(paths)
    try:
        again.set_today(TODAY)
        names = [s.display_name for s in again.sightings.page(SightingFilter())]
        assert names == ["Robin"]
    finally:
        again.close()
    assert apply_pending_restore(paths) is None  # done once only


def test_damaged_or_foreign_files_are_refused(ctx, tmp_path):
    junk = tmp_path / "not-a-backup.db"
    junk.write_bytes(b"this is not a database at all" * 100)
    with pytest.raises(BackupError) as refused:
        ctx.backup.request_restore(junk)
    assert refused.value.user_message == "That file isn't a WildLife backup."
    with pytest.raises(BackupError, match="isn't there"):
        ctx.backup.request_restore(tmp_path / "missing.db")


def test_a_failed_restore_leaves_the_data_alone(ctx, paths, tmp_path):
    add(ctx)
    ctx.backup.backup_now("manual")
    backup = ctx.backup.backups()[0].path
    ctx.backup.request_restore(backup)
    ctx.close()
    backup.unlink()  # the backup drive was unplugged before restarting
    outcome = apply_pending_restore(paths)
    assert not outcome.ok and "isn't there" in outcome.message
    again = AppContext.open(paths)
    try:
        assert again.sightings.totals(SightingFilter())[0] == 1
    finally:
        again.close()


def test_backups_are_single_files(ctx):
    """A snapshot must not leave -wal/-shm side files behind once it's been verified."""
    add(ctx)
    ctx.backup.backup_now("manual")
    folder = ctx.backup.folder() / "snapshots"
    assert sorted(p.suffix for p in folder.iterdir()) == [".db", ".json"]


def test_latest_backup_is_found_even_if_the_data_file_is_damaged(ctx, paths, tmp_path):
    from wildlife.data.restore import latest_backup

    elsewhere = tmp_path / "Backup drive"
    ctx.settings.update(backup_folder=str(elsewhere))
    add(ctx)
    ctx.backup.backup_now("manual")
    ctx.close()
    paths.database.write_bytes(b"damaged" * 1000)  # the setting inside can't be read now
    found = latest_backup(paths)
    assert found is not None and found.path.is_relative_to(elsewhere) and found.sightings == 1
