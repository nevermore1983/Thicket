"""Reading eBird's CSV exports. Two kinds are recognised from their columns:

* **Download My Data** (ebird.org › My eBird › Download My Data): every species on every
  checklist, with its position, date and time, count and notes. The .zip it comes in
  holds MyEBirdData.csv.
* **A life or year list** (My eBird › a list › Download): one row per species, the first
  time you recorded it, so only those sightings come in.

Each row becomes an `ImportRecord` for the shared import pipeline, which matches the
names to the species list. eBird's names follow its own (Clements) taxonomy; most of
the scientific names are the same as the UK list's, and the rest are offered for you to
match. A record is tracked by its checklist and species, so importing a newer export,
or the full data after a life list, adds only what's new.
"""

from __future__ import annotations

import csv
import io
import math
import re
from datetime import date, datetime
from pathlib import Path

from wildlife.domain.codes import CountQualifier
from wildlife.domain.errors import ImportFileError
from wildlife.domain.import_records import ImportRecord, export_text

SOURCE = "ebird"
CHECKLIST_URL = "https://ebird.org/checklist/{}"
MAX_NOTES, MAX_LOCATION_TEXT, MAX_UNCERTAINTY = 10_000, 200, 100_000
FULL = ("Submission ID", "Scientific Name", "Date")  # Download My Data
LIST = ("SubID", "Scientific Name", "Date")  # a life or year list
# Marks a record from Download My Data. A life list's record of the same sighting has
# less (no time, and a hotspot has no position), so the full data replaces it: the
# importer updates a record whose mark differs, unless you've edited it in Thicket.
FULL_DATA = "download-my-data"
NOT_WILD_CATEGORIES = {"domestic"}  # eBird's own word for farmyard and pet birds
ESCAPEE = "X"  # the Exotic column: N naturalised, P provisional, X escapee

# "Somewhere, England, GB (52.123, -1.765)": a personal location's position, written into its name
_POSITION_IN_NAME = re.compile(r"\s*\((-?\d{1,2}\.\d+),\s*(-?\d{1,3}\.\d+)\)\s*$")
# "Branta canadensis [canadensis Group]", "Anas platyrhynchos (Domestic type)"
_GROUP = re.compile(r"\s*[\[(][^\])]*[\])]")
_TIME = re.compile(r"^\s*(\d{1,2}):(\d{2})\s*([AaPp][Mm])?\s*$")


def is_ebird(header: list[str]) -> bool:
    """Does this CSV header look like one of eBird's exports?"""
    return all(c in header for c in FULL) or all(c in header for c in LIST)


def read_file(path: Path) -> list[ImportRecord]:
    """Read an eBird export: the .csv, or the .zip it downloads in."""
    return read_text(export_text(path))


def read_text(text: str) -> list[ImportRecord]:
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = [h.strip() for h in reader.fieldnames or []]
    if not is_ebird(header):
        raise ImportFileError(
            "This doesn't look like an eBird export. On ebird.org, choose My eBird › "
            "Download My Data, then pick the .zip (or the MyEBirdData.csv inside it)."
        )
    reader.fieldnames = header
    full = all(c in header for c in FULL)
    return [parse_row(i + 2, row, full) for i, row in enumerate(reader)]


def _text(row: dict, key: str) -> str | None:
    value = (row.get(key) or "").strip()
    return value or None


def _float(row: dict, key: str) -> float | None:
    try:
        return float(row[key]) if _text(row, key) else None
    except ValueError:
        return None


def _date(text: str | None) -> date | None:
    """'2026-05-17' (Download My Data) or '17 May 2026' (a list)."""
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%d %B %Y", "%m-%d-%Y"):
        try:
            return datetime.strptime(text or "", fmt).date()
        except ValueError:
            continue
    return None


def _time(text: str | None) -> str | None:
    """'07:45 AM' -> '07:45'; '1:05 PM' -> '13:05'."""
    m = _TIME.match(text or "")
    if not m:
        return None
    hour, minute, ampm = int(m[1]), int(m[2]), m[3]
    if ampm:
        hour = hour % 12 + (12 if ampm.lower() == "pm" else 0)
    return f"{hour:02d}:{minute:02d}" if hour < 24 and minute < 60 else None


def _count(text: str | None) -> int | None:
    """A number, or None for 'X' (present, not counted) and blanks."""
    try:
        return int(text) if text else None
    except ValueError:
        return None


def clean_name(name: str | None) -> str | None:
    """eBird's scientific name as the species list would write it: groups and types
    dropped ('[canadensis Group]', '(Domestic type)'), and 'Larus sp.' as the genus.
    Slashes ('Corvus corone/cornix') and hybrids stay, for you to match yourself."""
    if not name:
        return None
    name = " ".join(_GROUP.sub("", name).split())
    if name.endswith(" sp."):
        name = name.removesuffix(" sp.")
    return name or None


def _uncertainty(row: dict) -> int:
    """How far from the given point the bird may have been. A checklist has one point
    (where it started, or the location's position), so at least ~100 m; a walk or a
    survey area spreads further: half the distance walked, or half the area's width."""
    distance_km = _float(row, "Distance Traveled (km)") or 0
    area_ha = _float(row, "Area Covered (ha)") or 0
    spread = max(distance_km * 500, 50 * math.sqrt(area_ha))
    return min(max(100, round(spread)), MAX_UNCERTAINTY)


def parse_row(line: int, row: dict, full: bool = True) -> ImportRecord:
    checklist = _text(row, "Submission ID" if full else "SubID")
    scientific = _text(row, "Scientific Name")
    common = _text(row, "Common Name")
    day = _date(_text(row, "Date"))
    location = _text(row, "Location")
    lat, lon = _float(row, "Latitude"), _float(row, "Longitude")
    if location and (m := _POSITION_IN_NAME.search(location)):
        location = location[: m.start()].strip() or None
        if lat is None:
            lat, lon = float(m[1]), float(m[2])
    if lat is not None and not (-90 <= lat <= 90 and -180 <= lon <= 180):
        lat = lon = None
    notes = [_text(row, "Observation Details")]
    if code := _text(row, "Breeding Code"):
        notes.append(f"Breeding code: {code}")
    category = (_text(row, "Category") or "").lower()
    raw_count = _text(row, "Count")
    count = _count(raw_count)
    problem = None
    if not checklist:
        problem = "No eBird checklist id"
    elif day is None:
        problem = "No date"
    elif not scientific and not common:
        problem = "No species name"
    return ImportRecord(
        line=line,
        source_id=f"{checklist}/{scientific or common}" if checklist else None,
        url=CHECKLIST_URL.format(checklist) if checklist else None,
        observed_date=day,
        observed_time=_time(_text(row, "Time")),
        latitude=round(lat, 6) if lat is not None else None,
        longitude=round(lon, 6) if lon is not None else None,
        uncertainty_m=_uncertainty(row) if lat is not None else None,
        location_text=location[:MAX_LOCATION_TEXT] if location else None,
        place_name=location,  # a saved place with the same name (a hotspot, say) is used
        count=count,
        count_qualifier=CountQualifier.EXACT,
        notes="\n".join(n for n in notes if n)[:MAX_NOTES] or None,
        is_not_wild=category in NOT_WILD_CATEGORIES or _text(row, "Exotic") == ESCAPEE,
        scientific_name=clean_name(scientific),
        common_name=common,
        kingdom="Animalia",  # birds: tells apart names shared with plants (Prunella)
        updated_at=FULL_DATA if full else None,  # a life list's None never replaces anything
        problem=problem,
    )
