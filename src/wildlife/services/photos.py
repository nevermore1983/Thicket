"""Photos: reading their details, copying them into the library, thumbnails.

Originals are copied into the library (photos/YYYY/MM/<sha256>.<ext>) and never
changed. The file name is the photo's content hash, so the same image imported
twice is stored once, and a backup only ever needs to copy new files.
"""

from __future__ import annotations

import hashlib
import logging
import shutil
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

import pi_heif
from PIL import Image, ImageOps, UnidentifiedImageError

from wildlife.config.paths import DataPaths
from wildlife.data.db import Database
from wildlife.data.repositories import photos as repo
from wildlife.domain.errors import PhotoError
from wildlife.domain.models import Photo
from wildlife.services.events import EventHub

log = logging.getLogger(__name__)
pi_heif.register_heif_opener()  # lets Pillow open iPhone HEIC/HEIF files

SUPPORTED = {".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff"}
THUMB_SIZES = (256, 1024)
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


@dataclass
class ImportSummary:
    imported: list[Photo] = field(default_factory=list)
    duplicates: list[Photo] = field(default_factory=list)  # already in the library
    failed: list[tuple[str, str]] = field(default_factory=list)  # (file name, reason)

    @property
    def photos(self) -> list[Photo]:
        """Everything usable: new imports plus duplicates already in the library."""
        return self.imported + self.duplicates


def _gps_decimal(dms, ref: str | None) -> float:
    d, m, s = (float(x) for x in dms)
    value = d + m / 60 + s / 3600
    return -value if ref in ("S", "W") else value


def read_info(path: Path) -> PhotoInfo:
    """Read size, date taken, GPS and camera. Raises PhotoError if it isn't a readable image."""
    try:
        with Image.open(path) as im:
            exif = im.getexif()
            upright = ImageOps.exif_transpose(im)  # HEIC arrives upright already; JPEG may not
            width, height = upright.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise PhotoError(
            f"“{path.name}” isn't a photo WildLife can read.", detail=str(exc)
        ) from exc
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
    camera = " ".join(str(exif.get(t, "")).strip() for t in (0x010F, 0x0110)).strip() or None
    return PhotoInfo(width, height, taken, lat, lon, accuracy, camera)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


class PhotoService:
    def __init__(self, paths: DataPaths, db: Database, events: EventHub) -> None:
        self._paths, self._db, self._events = paths, db, events

    # ---- importing --------------------------------------------------------
    def import_files(
        self, files: Iterable[Path], progress: Callable[[int, int], None] = lambda d, t: None
    ) -> ImportSummary:
        files = [Path(f) for f in files]
        summary = ImportSummary()
        for i, path in enumerate(files):
            progress(i, len(files))
            if path.suffix.lower() not in SUPPORTED:
                summary.failed.append((path.name, "Not a supported photo type"))
                continue
            try:
                photo, is_new = self._import_one(path)
            except PhotoError as exc:
                summary.failed.append((path.name, exc.user_message))
                continue
            except OSError as exc:
                log.warning("Couldn't import %s: %s", path, exc)
                summary.failed.append((path.name, "The file couldn't be read or copied"))
                continue
            (summary.imported if is_new else summary.duplicates).append(photo)
        progress(len(files), len(files))
        if summary.imported:
            self._events.publish(TOPIC, tuple(p.id for p in summary.imported))
        return summary

    def _import_one(self, path: Path) -> tuple[Photo, bool]:
        sha = file_sha256(path)
        with self._db.connection() as conn:
            existing = repo.by_sha(conn, sha)
        if existing:
            return existing, False
        info = read_info(path)
        when = info.taken_at or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        rel = f"photos/{when[:4]}/{when[5:7]}/{sha}{path.suffix.lower()}"
        dest = self._paths.root / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        shutil.copy2(path, tmp)
        tmp.replace(dest)  # appears in the library only once fully copied
        try:
            with self._db.transaction() as conn:
                photo_id = repo.insert(
                    conn,
                    repo.NewPhoto(
                        sha,
                        rel,
                        path.name,
                        dest.stat().st_size,
                        info.width,
                        info.height,
                        info.taken_at,
                        info.latitude,
                        info.longitude,
                    ),
                )
                photo = repo.get(conn, photo_id)
        except Exception:
            dest.unlink(missing_ok=True)  # don't leave an unrecorded file behind
            raise
        return photo, True

    # ---- linking to sightings ----------------------------------------------
    def attach(self, sighting_id: int, photo_ids: list[int]) -> None:
        if not photo_ids:
            return
        with self._db.transaction() as conn:
            repo.attach(conn, sighting_id, photo_ids)
        self._events.publish("sightings", (sighting_id,))

    def detach(self, sighting_id: int, photo_ids: list[int]) -> None:
        """Take photos off a sighting; they return to the Photo Inbox."""
        with self._db.transaction() as conn:
            repo.detach(conn, sighting_id, photo_ids)
        self._events.publish("sightings", (sighting_id,))

    def for_sighting(self, sighting_id: int) -> list[Photo]:
        with self._db.connection() as conn:
            return repo.for_sighting(conn, sighting_id)

    def inbox_count(self) -> int:
        with self._db.connection() as conn:
            return repo.inbox_count(conn)

    # ---- files ---------------------------------------------------------------
    def path_of(self, photo: Photo) -> Path:
        return self._paths.root / photo.rel_path

    def thumbnail(self, photo: Photo, size: int = 256) -> Path | None:
        """Path to a cached thumbnail, made on first use. None if the original is missing."""
        target = (
            self._paths.thumbnails
            / str(size)
            / photo.sha256[:2]
            / f"{photo.sha256}_{photo.rotation}.webp"
        )
        if target.exists():
            return target
        original = self.path_of(photo)
        if not original.exists():
            return None
        try:
            with Image.open(original) as im:
                img = ImageOps.exif_transpose(im)
                if photo.rotation:
                    img = img.rotate(-photo.rotation, expand=True)
                img.thumbnail((size, size))
                target.parent.mkdir(parents=True, exist_ok=True)
                img.convert("RGB").save(target, "WEBP", quality=82)
        except (OSError, ValueError) as exc:
            log.warning("Thumbnail failed for %s: %s", original, exc)
            return None
        return target
