"""Photos: reading their details, copying them into the library, thumbnails, and looking after them.

Originals are copied into the library (photos/YYYY/MM/<sha256>.<ext>) and never
changed. The file name is the photo's content hash, so the same image imported
twice is stored once, and a backup only ever needs to copy new files.

RAW files (e.g. a Pixel's .dng) are kept too. Next to its JPEG, a RAW file is that
photo's "RAW original"; on its own, it's shown by rendering it with LibRaw (rawpy).
"""

from __future__ import annotations

import hashlib
import io
import logging
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pi_heif
import rawpy
from PIL import Image, ImageOps, UnidentifiedImageError

from wildlife.config.paths import DataPaths
from wildlife.data.db import Database
from wildlife.data.repositories import photos as repo
from wildlife.domain.errors import NotFoundError, PhotoError
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import Photo
from wildlife.domain.photo_files import (
    SUPPORTED_SUFFIXES,
    ImportItem,
    date_from_name,
    is_raw,
    is_supported,
    pair_files,
)
from wildlife.services.events import EventHub
from wildlife.services.settings import SettingsService
from wildlife.services.sightings import Undo

log = logging.getLogger(__name__)
pi_heif.register_heif_opener()  # lets Pillow open HEIC/HEIF files

SUPPORTED = set(SUPPORTED_SUFFIXES)  # kept for older callers (the add-photos file dialog)
THUMB_SIZES = (256, 1024)
SCREEN = 2048  # the viewer's picture size: sharp on a 4K screen, quick to load
TOPIC = "photos"


@dataclass(frozen=True, slots=True)
class PhotoInfo:
    """What a photo file tells us about itself."""

    width: int
    height: int
    taken_at: str | None  # 'YYYY-MM-DD HH:MM:SS' (camera's local time)
    latitude: float | None
    longitude: float | None
    gps_accuracy_m: float | None
    camera: str | None
    taken_source: str | None = None  # 'exif' or 'file_name'


@dataclass
class ImportSummary:
    imported: list[Photo] = field(default_factory=list)
    duplicates: list[Photo] = field(default_factory=list)  # already in the library
    failed: list[tuple[str, str]] = field(default_factory=list)  # (file name, reason)
    raw_paired: int = 0  # RAW originals kept with their photo
    skipped: int = 0  # files in a folder that aren't photos (videos, documents...)

    @property
    def photos(self) -> list[Photo]:
        """Everything usable: new imports plus duplicates already in the library."""
        return self.imported + self.duplicates

    def describe(self) -> str:
        """'38 imported · 12 RAW originals kept · 2 already in your library · 1 couldn't be read'."""
        parts = [f"{len(self.imported):,} imported"]
        if self.raw_paired:
            parts.append(
                f"{self.raw_paired:,} RAW original{'s' if self.raw_paired != 1 else ''} kept"
            )
        if self.duplicates:
            parts.append(f"{len(self.duplicates):,} already in your library")
        if self.failed:
            parts.append(f"{len(self.failed):,} couldn't be read")
        return " · ".join(parts)


# ---- reading files ---------------------------------------------------------------------
def _gps_decimal(dms, ref: str | None) -> float:
    d, m, s = (float(x) for x in dms)
    value = d + m / 60 + s / 3600
    return -value if ref in ("S", "W") else value


def _from_exif(
    exif: Image.Exif,
) -> tuple[str | None, float | None, float | None, float | None, str | None]:
    """(taken_at, lat, lon, accuracy, camera) from EXIF tags."""
    sub = exif.get_ifd(0x8769)
    raw_date = sub.get(0x9003) or exif.get(0x0132)
    taken = None
    if isinstance(raw_date, str):
        try:
            taken = datetime.strptime(raw_date.strip()[:19], "%Y:%m:%d %H:%M:%S").strftime(
                "%Y-%m-%d %H:%M:%S"
            )
        except ValueError:
            taken = None
    lat = lon = accuracy = None
    gps = exif.get_ifd(0x8825)
    try:
        if gps.get(2) and gps.get(4):
            lat, lon = _gps_decimal(gps[2], gps.get(1)), _gps_decimal(gps[4], gps.get(3))
            if not (-90 <= lat <= 90 and -180 <= lon <= 180) or (lat == 0 and lon == 0):
                lat = lon = None
            accuracy = float(gps[0x1F]) if 0x1F in gps else None
    except (TypeError, ValueError, ZeroDivisionError):
        lat = lon = accuracy = None
    make, model = (str(exif.get(t, "")).strip() for t in (0x010F, 0x0110))
    # 'Google' + 'Pixel 10 Pro' -> 'Google Pixel 10 Pro'; avoid 'Canon Canon EOS R7'
    camera = (
        model if model.lower().startswith(make.lower()) else f"{make} {model}"
    ).strip() or None
    return taken, lat, lon, accuracy, camera


def read_info(path: Path) -> PhotoInfo:
    """Read size, date taken, GPS and camera. Raises PhotoError if it isn't a readable image.

    A RAW file is read with LibRaw for its size and as a TIFF for its EXIF. (Google Photos'
    'storage saver' can hand back a JPEG still named .dng, so Pillow always gets the first try.)"""
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            width, height = ImageOps.exif_transpose(im).size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        if not is_raw(path):
            raise PhotoError(
                f"“{path.name}” isn't a photo WildLife can read.", detail=str(exc)
            ) from exc
        width, height, exif = _raw_size_and_exif(path)
    taken, lat, lon, accuracy, camera = _from_exif(exif)
    source = "exif" if taken else None
    if taken is None and (taken := date_from_name(path.name)):
        source = "file_name"
    return PhotoInfo(width, height, taken, lat, lon, accuracy, camera, source)


def _raw_size_and_exif(path: Path) -> tuple[int, int, Image.Exif]:
    try:
        with rawpy.imread(str(path)) as raw:
            sizes = raw.sizes
            width, height = sizes.width, sizes.height
            if sizes.flip in (5, 6):  # LibRaw's codes for a quarter turn
                width, height = height, width
    except (rawpy.LibRawError, OSError) as exc:
        raise PhotoError(
            f"“{path.name}” isn't a RAW file WildLife can read.", detail=str(exc)
        ) from exc
    exif = Image.Exif()
    try:
        exif.load(path.read_bytes())  # DNG and most RAW formats are TIFF inside
    except (OSError, ValueError, SyntaxError) as exc:  # pragma: no cover - unusual RAW layouts
        log.info("No EXIF in %s: %s", path.name, exc)
    return width, height, exif


def open_image(path: Path, rotation: int = 0, max_size: int | None = None) -> Image.Image:
    """The picture upright and turned by `rotation`, as a Pillow image (RGB).

    For RAW files: the camera's embedded JPEG if it's big enough, else a LibRaw rendering."""
    if is_raw(path):
        image = _open_raw(path, max_size)
    else:
        with Image.open(path) as im:
            if max_size:
                # JPEG: decode at 1/2, 1/4 or 1/8 size, much faster. Pillow only shrinks while
                # *both* sides stay at least the size asked for, so ask in the photo's own
                # shape; the 10% margin lets a Pixel's 4080 px photo decode at half size
                # (2040 px) for the 2048 px viewer picture.
                fit = max_size * 0.9 / max(im.size)
                im.draft("RGB", (round(im.width * fit), round(im.height * fit)))
            image = ImageOps.exif_transpose(im)
            image.load()
    if max_size:
        image.thumbnail((max_size, max_size))
    if rotation:
        image = image.rotate(-rotation, expand=True)
    return image.convert("RGB")


def _open_raw(path: Path, max_size: int | None) -> Image.Image:
    try:
        with Image.open(path) as im:  # a JPEG wearing a .dng name (storage saver)
            image = ImageOps.exif_transpose(im)
            image.load()
            return image
    except (UnidentifiedImageError, OSError):
        pass
    with rawpy.imread(str(path)) as raw:
        try:
            thumb = raw.extract_thumb()
            if thumb.format == rawpy.ThumbFormat.JPEG:
                preview = Image.open(io.BytesIO(thumb.data))
                if max_size and max(preview.size) >= max_size * 0.9:
                    return ImageOps.exif_transpose(preview)
        except (rawpy.LibRawNoThumbnailError, rawpy.LibRawUnsupportedThumbnailError):
            pass
        half = bool(max_size and max(raw.sizes.width, raw.sizes.height) / 2 >= max_size)
        rgb = raw.postprocess(use_camera_wb=True, half_size=half, output_bps=8)
    return Image.fromarray(rgb)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def expand(paths: Iterable[Path]) -> tuple[list[Path], int]:
    """Files to import: files as given, folders searched (sub-folders too) for photos.
    Returns (photo files, number of other files skipped in folders)."""
    out: list[Path] = []
    skipped = 0
    for path in paths:
        path = Path(path)
        if path.is_dir():
            for f in sorted(p for p in path.rglob("*") if p.is_file()):
                if is_supported(f):
                    out.append(f)
                else:
                    skipped += 1
        else:
            out.append(path)
    return out, skipped


# ---- the service ----------------------------------------------------------------------
class PhotoService:
    def __init__(
        self,
        paths: DataPaths,
        db: Database,
        events: EventHub,
        settings: SettingsService | None = None,
    ) -> None:
        self._paths, self._db, self._events, self._settings = paths, db, events, settings

    # ---- importing ---------------------------------------------------------------
    def import_files(
        self, files: Iterable[Path], progress: Callable[[int, int], None] = lambda d, t: None
    ) -> ImportSummary:
        """Import photo files and/or folders. RAW files are paired with their JPEGs."""
        found, skipped = expand(files)
        summary = ImportSummary(skipped=skipped)
        items = pair_files(found)
        for i, item in enumerate(items):
            progress(i, len(items))
            if not is_supported(item.main):
                summary.failed.append((item.main.name, "Not a supported photo type"))
                continue
            try:
                photo, is_new, raw_kept = self._import_one(item)
            except PhotoError as exc:
                summary.failed.append((item.main.name, exc.user_message))
                continue
            except OSError as exc:
                log.warning("Couldn't import %s: %s", item.main, exc)
                summary.failed.append((item.main.name, "The file couldn't be read or copied"))
                continue
            (summary.imported if is_new else summary.duplicates).append(photo)
            summary.raw_paired += raw_kept
        progress(len(items), len(items))
        if summary.imported or summary.raw_paired:
            self._events.publish(TOPIC, tuple(p.id for p in summary.photos))
        return summary

    def _copy_in(self, source: Path, sha: str, when: str | None) -> tuple[str, Path]:
        """Copy a file into the library; returns (relative path, full path)."""
        when = when or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rel = f"photos/{when[:4]}/{when[5:7]}/{sha}{source.suffix.lower()}"
        dest = self._paths.root / rel
        if not dest.exists():
            dest.parent.mkdir(parents=True, exist_ok=True)
            tmp = dest.with_suffix(dest.suffix + ".part")
            shutil.copy2(source, tmp)
            tmp.replace(dest)  # appears in the library only once fully copied
        return rel, dest

    def _import_one(self, item: ImportItem) -> tuple[Photo, bool, int]:
        """(photo, newly imported?, RAW original kept: 0 or 1)."""
        sha = file_sha256(item.main)
        raw_sha = file_sha256(item.raw) if item.raw else None
        with self._db.connection() as conn:
            existing = repo.by_sha(conn, sha) or repo.by_raw_sha(conn, sha)
            raw_known = raw_sha is not None and (
                repo.by_raw_sha(conn, raw_sha) or repo.by_sha(conn, raw_sha)
            )
        if existing:
            if item.raw and not raw_known and not existing.has_raw:
                existing = self._add_raw(existing, item.raw, raw_sha)  # the RAW arrived later
                return existing, False, 1
            return existing, False, 0
        info = read_info(item.main)
        rel, dest = self._copy_in(item.main, sha, info.taken_at)
        raw_rel = raw_dest = None
        if item.raw and not raw_known:
            raw_rel, raw_dest = self._copy_in(item.raw, raw_sha, info.taken_at)
        try:
            with self._db.transaction() as conn:
                photo_id = repo.insert(
                    conn,
                    repo.NewPhoto(
                        sha,
                        rel,
                        item.main.name,
                        dest.stat().st_size,
                        info.width,
                        info.height,
                        info.taken_at,
                        info.latitude,
                        info.longitude,
                        camera=info.camera,
                        taken_source=info.taken_source,
                        raw_sha256=raw_sha if raw_rel else None,
                        raw_rel_path=raw_rel,
                        raw_name=item.raw.name if raw_rel else None,
                        raw_size=raw_dest.stat().st_size if raw_dest else None,
                    ),
                )
                photo = repo.get(conn, photo_id)
        except Exception:
            dest.unlink(missing_ok=True)  # don't leave unrecorded files behind
            if raw_dest:
                raw_dest.unlink(missing_ok=True)
            raise
        return photo, True, 1 if raw_rel else 0

    def add_raw(self, photo_id: int, raw: Path) -> Photo:
        """Keep a RAW original with a photo that has none yet (e.g. from an export)."""
        photo = self.get(photo_id)
        if photo.has_raw:
            return photo
        return self._add_raw(photo, raw, file_sha256(raw))

    def _add_raw(self, photo: Photo, raw: Path, raw_sha: str) -> Photo:
        rel, dest = self._copy_in(raw, raw_sha, photo.taken_at)
        with self._db.transaction() as conn:
            repo.set_raw(conn, photo.id, raw_sha, rel, raw.name, dest.stat().st_size)
            return repo.get(conn, photo.id)

    # ---- reading -------------------------------------------------------------------
    def get(self, photo_id: int) -> Photo:
        with self._db.connection() as conn:
            photo = repo.get(conn, photo_id)
        if photo is None:
            raise NotFoundError("That photo no longer exists.")
        return photo

    def for_sighting(self, sighting_id: int) -> list[Photo]:
        with self._db.connection() as conn:
            return repo.for_sighting(conn, sighting_id)

    def inbox(self) -> list[Photo]:
        with self._db.connection() as conn:
            return repo.inbox(conn)

    def inbox_count(self) -> int:
        with self._db.connection() as conn:
            return repo.inbox_count(conn)

    def library(self, flt: SightingFilter) -> list[repo.LibraryItem]:
        with self._db.connection() as conn:
            return repo.library(conn, flt)

    # ---- linking to sightings ------------------------------------------------------
    def attach(self, sighting_id: int, photo_ids: list[int]) -> None:
        if not photo_ids:
            return
        with self._db.transaction() as conn:
            repo.attach(conn, sighting_id, photo_ids)
        self._events.publish("sightings", (sighting_id,))
        self._events.publish(TOPIC, tuple(photo_ids))

    def detach(self, sighting_id: int, photo_ids: list[int]) -> None:
        """Take photos off a sighting; they return to the Photo Inbox."""
        with self._db.transaction() as conn:
            repo.detach(conn, sighting_id, photo_ids)
        self._events.publish("sightings", (sighting_id,))
        self._events.publish(TOPIC, tuple(photo_ids))

    def make_cover(self, sighting_id: int, photo_id: int) -> None:
        with self._db.transaction() as conn:
            repo.make_cover(conn, sighting_id, photo_id)
        self._events.publish("sightings", (sighting_id,))
        self._events.publish(TOPIC, (photo_id,))

    def reorder(self, sighting_id: int, photo_ids: list[int]) -> None:
        """Set the order of a sighting's photos (the first is the cover)."""
        with self._db.transaction() as conn:
            repo.reorder(conn, sighting_id, photo_ids)
        self._events.publish("sightings", (sighting_id,))

    # ---- changing ------------------------------------------------------------------
    def rotate(self, photo_id: int, degrees: int = 90) -> Photo:
        """Turn the photo clockwise for display. The original file is never changed."""
        photo = self.get(photo_id)
        with self._db.transaction() as conn:
            repo.set_rotation(conn, photo_id, photo.rotation + degrees)
        self._events.publish(TOPIC, (photo_id,))
        return self.get(photo_id)

    def shift_times(self, ids: list[int], minutes: int) -> Undo:
        """Move the time the photos were taken by `minutes` (a camera clock that was set
        wrong, or not changed for summer time). Photos with no time are left alone."""
        with self._db.transaction() as conn:
            found = [p for i in ids if (p := repo.get(conn, i)) is not None and p.taken_at]
            before = {p.id: (p.taken_at, p.taken_source or "exif") for p in found}
            for p in found:
                moved = datetime.fromisoformat(p.taken_at) + timedelta(minutes=minutes)
                repo.set_taken(conn, p.id, moved.strftime("%Y-%m-%d %H:%M:%S"), "manual")
        self._events.publish(TOPIC, tuple(before))

        def undo() -> None:
            with self._db.transaction() as c:
                for pid, (taken, source) in before.items():
                    repo.set_taken(c, pid, taken, source)
            self._events.publish(TOPIC, tuple(before))

        noun = "photo" if len(before) == 1 else f"{len(before)} photos"
        return Undo(f"Change the time of {noun}", undo)

    def set_caption(self, photo_id: int, caption: str | None) -> None:
        with self._db.transaction() as conn:
            repo.set_caption(conn, photo_id, (caption or "").strip() or None)
        self._events.publish(TOPIC, (photo_id,))

    def delete(self, ids: list[int]) -> Undo:
        """Move photos to the recycle bin (they leave any sighting they were on)."""
        with self._db.transaction() as conn:
            found = [p for i in ids if (p := repo.get(conn, i)) is not None]
            links = {p.id: p.sighting_ids for p in found}
            for pid, sightings in links.items():
                for sid in sightings:
                    repo.detach(conn, sid, [pid])
            repo.soft_delete(conn, ids)
        self._events.publish(TOPIC, tuple(ids))
        if any(links.values()):
            self._events.publish("sightings", tuple({s for v in links.values() for s in v}))

        def undo() -> None:
            with self._db.transaction() as c:
                repo.restore(c, ids)
                for pid, sightings in links.items():
                    for sid in sightings:
                        repo.attach(c, sid, [pid])
            self._events.publish(TOPIC, tuple(ids))
            self._events.publish("sightings", tuple({s for v in links.values() for s in v}))

        noun = "photo" if len(ids) == 1 else f"{len(ids)} photos"
        return Undo(f"Delete {noun}", undo)

    def restore(self, ids: list[int]) -> None:
        with self._db.transaction() as conn:
            repo.restore(conn, ids)
        self._events.publish(TOPIC, tuple(ids))

    def recycle_bin(self) -> list[Photo]:
        with self._db.connection() as conn:
            return repo.recycle_bin(conn)

    def purge_recycle_bin(self, older_than_days: int | None = None) -> int:
        """Permanently remove photos deleted more than N days ago, files and all.
        The only time WildLife ever deletes a photo file."""
        days = older_than_days
        if days is None:
            days = self._settings.current.recycle_bin_days if self._settings else 30
        cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._db.transaction() as conn:
            doomed = repo.deleted_before(conn, cutoff)
            repo.hard_delete(conn, [p.id for p in doomed])
        for photo in doomed:
            self._remove_files(photo)
        if doomed:
            log.info("Recycle bin: removed %d photos", len(doomed))
            self._events.publish(TOPIC, tuple(p.id for p in doomed))
        return len(doomed)

    def _remove_files(self, photo: Photo) -> None:
        for rel in (photo.rel_path, photo.raw_rel_path):
            if rel:
                (self._paths.root / rel).unlink(missing_ok=True)
        for size in (*THUMB_SIZES, SCREEN):
            for cached in (self._paths.thumbnails / str(size) / photo.sha256[:2]).glob(
                f"{photo.sha256}_*.*"
            ):
                cached.unlink(missing_ok=True)

    # ---- missing files -------------------------------------------------------------
    def missing(self) -> list[Photo]:
        """Photos whose library file has gone (e.g. deleted outside WildLife)."""
        with self._db.connection() as conn:
            photos = repo.live(conn)
        return [p for p in photos if not self.path_of(p).exists()]

    def locate(self, photo_id: int, candidate: Path) -> Photo:
        """Put a missing photo's file back from `candidate`, if it is the very same photo."""
        photo = self.get(photo_id)
        if file_sha256(candidate) != photo.sha256:
            raise PhotoError(
                f"“{candidate.name}” isn't the same photo (its contents are different). "
                "Choose the original file."
            )
        dest = self.path_of(photo)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        shutil.copy2(candidate, tmp)
        tmp.replace(dest)
        self._events.publish(TOPIC, (photo_id,))
        return photo

    def find_in_folder(
        self, folder: Path, progress: Callable[[int, int], None] = lambda d, t: None
    ) -> int:
        """Look through `folder` (and its sub-folders) for missing photo files, and put
        back every one whose contents match. Returns how many came back. Only files of
        exactly the right size are read, so a big folder is still quick."""
        with self._db.connection() as conn:
            files = repo.library_files(conn)
        wanted: dict[str, tuple[Path, int]] = {  # sha256 -> (where it belongs, size)
            sha: (self._paths.root / rel, size)
            for sha, rel, size in files
            if not (self._paths.root / rel).exists()
        }
        sizes = {size for _, size in wanted.values()}
        candidates = [f for f in folder.rglob("*") if f.is_file() and f.stat().st_size in sizes]
        found = 0
        for i, candidate in enumerate(candidates):
            progress(i, len(candidates))
            target = wanted.get(file_sha256(candidate))
            if target is None or target[0].exists():
                continue
            target[0].parent.mkdir(parents=True, exist_ok=True)
            tmp = target[0].with_suffix(target[0].suffix + ".part")
            shutil.copy2(candidate, tmp)
            tmp.replace(target[0])
            found += 1
        progress(len(candidates), len(candidates))
        if found:
            log.info("Found %d missing photo files in %s", found, folder)
            self._events.publish(TOPIC, ())
        return found

    # ---- files ---------------------------------------------------------------------
    def path_of(self, photo: Photo) -> Path:
        return self._paths.root / photo.rel_path

    def raw_path_of(self, photo: Photo) -> Path | None:
        if photo.raw_rel_path:
            return self._paths.root / photo.raw_rel_path
        return self.path_of(photo) if photo.is_raw else None

    def thumbnail(self, photo: Photo, size: int = 256) -> Path | None:
        """Path to a cached picture of at most `size` pixels, made on first use.
        None if the original is missing or can't be decoded."""
        # Small thumbnails as WebP (compact); the big viewer copy as JPEG (WebP takes ~0.6 s
        # to save at 2048 px, JPEG 7 ms, for the same file size)
        suffix = "webp" if size <= 1024 else "jpg"
        target = (
            self._paths.thumbnails
            / str(size)
            / photo.sha256[:2]
            / f"{photo.sha256}_{photo.rotation}.{suffix}"
        )
        if target.exists():
            return target
        original = self.path_of(photo)
        if not original.exists():
            return None
        try:
            img = open_image(original, photo.rotation, size)
            target.parent.mkdir(parents=True, exist_ok=True)
            tmp = target.with_suffix(".part")
            if suffix == "webp":
                img.save(tmp, "WEBP", quality=82)
            else:
                img.save(tmp, "JPEG", quality=90)
            tmp.replace(target)
        except (OSError, ValueError, rawpy.LibRawError) as exc:
            log.warning("Thumbnail failed for %s: %s", original, exc)
            return None
        return target

    def screen_image(self, photo: Photo) -> Path | None:
        """The viewer's picture (up to 2048 px), cached like a thumbnail."""
        return self.thumbnail(photo, SCREEN)
