"""Rules about photo files themselves: which are RAW, which belong together, and
what a file name can tell us when the photo has lost its own date.

Pure functions on names and paths: no image decoding, no database.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

# RAW formats LibRaw (through rawpy) can read. Pixels write DNG; cameras use the others.
RAW_SUFFIXES = (".dng", ".cr2", ".cr3", ".nef", ".arw", ".orf", ".rw2", ".raf", ".pef", ".srw")
PICTURE_SUFFIXES = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".heif", ".tif", ".tiff")
SUPPORTED_SUFFIXES = PICTURE_SUFFIXES + RAW_SUFFIXES

# Pixel since late 2023: PXL_20240407_152207242.RAW-01.COVER.jpg / .RAW-02.ORIGINAL.dng
# (and .RAW-01.MP.COVER.jpg when the cover is a Motion Photo)
_PIXEL_PAIR_PART = re.compile(r"\.raw-\d+(\.[a-z0-9]+)*$", re.IGNORECASE)
_MOTION_PART = re.compile(r"\.mp$", re.IGNORECASE)


def is_raw(path: Path | str) -> bool:
    return str(path).lower().endswith(RAW_SUFFIXES)


def is_supported(path: Path | str) -> bool:
    return str(path).lower().endswith(SUPPORTED_SUFFIXES)


def pair_key(path: Path) -> tuple[str, str]:
    """(folder, base name) shared by a RAW file and its JPEG.

    'PXL_..242.RAW-01.COVER.jpg', 'PXL_..242.RAW-02.ORIGINAL.dng' and the older
    'PXL_..242.jpg' / 'PXL_..242.dng' all give 'pxl_..242'."""
    stem = path.name[: -len(path.suffix)] if path.suffix else path.name
    stem = _PIXEL_PAIR_PART.sub("", stem)
    stem = _MOTION_PART.sub("", stem)
    return str(path.parent).lower(), stem.lower()


@dataclass(frozen=True, slots=True)
class ImportItem:
    """One photo to import: the file to show, and its RAW original if there is one."""

    main: Path
    raw: Path | None = None


def pair_files(paths: list[Path]) -> list[ImportItem]:
    """Group files into photos. A RAW file joins the picture with the same base name in
    the same folder; a RAW with no picture becomes a photo on its own."""
    groups: dict[tuple[str, str], list[Path]] = defaultdict(list)
    order: list[tuple[str, str]] = []
    for path in paths:
        key = pair_key(path)
        if key not in groups:
            order.append(key)
        groups[key].append(path)
    items: list[ImportItem] = []
    for key in order:
        files = groups[key]
        raws = [f for f in files if is_raw(f)]
        pictures = [f for f in files if not is_raw(f)]
        # The Pixel marks its main picture COVER; otherwise keep the order given
        pictures.sort(key=lambda f: ".cover." not in f.name.lower())
        for i, picture in enumerate(pictures):
            items.append(ImportItem(picture, raws.pop(0) if i == 0 and raws else None))
        items.extend(ImportItem(raw) for raw in raws)  # RAWs with no picture of their own
    return items


# ---- dates in file names -----------------------------------------------------------
_PIXEL_NAME = re.compile(r"^PXL_(\d{8})_(\d{6})\d{0,3}", re.IGNORECASE)  # time is UTC
_PHONE_NAME = re.compile(r"(?:IMG|VID|PANO|BURST|MVIMG)[_-]?(\d{8})[_-](\d{6})", re.IGNORECASE)


def date_from_name(name: str) -> str | None:
    """'YYYY-MM-DD HH:MM:SS' local time from a phone-style file name, or None.

    Pixel names (PXL_...) record UTC, so they're converted to this computer's local time
    (an 08:15 PXL name in British summer time is 09:15 on the clock). Other phones'
    IMG_YYYYMMDD_HHMMSS names already use local time."""
    if m := _PIXEL_NAME.match(name):
        moment = _parse(m[1], m[2])
        if moment is None:
            return None
        local = moment.replace(tzinfo=UTC).astimezone().replace(tzinfo=None)
        return local.strftime("%Y-%m-%d %H:%M:%S")
    if m := _PHONE_NAME.search(name):
        moment = _parse(m[1], m[2])
        return moment.strftime("%Y-%m-%d %H:%M:%S") if moment else None
    return None


def _parse(day: str, time: str) -> datetime | None:
    try:
        moment = datetime.strptime(day + time, "%Y%m%d%H%M%S")
    except ValueError:
        return None
    return moment if 1990 <= moment.year <= 2100 else None
