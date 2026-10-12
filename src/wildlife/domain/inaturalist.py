"""Reading iNaturalist's CSV export (inaturalist.org › Your observations › Export).

Each row becomes an `InatRecord`: the observation in WildLife's terms (date, UK clock
time, position, how sure the ID is), plus the names iNaturalist used, which the
importer then matches to the UK species list. Rows that can't become a sighting
(no date, no name) keep a `problem` explaining why, so the preview can show them.
"""

from __future__ import annotations

import csv
import io
import re
import zipfile
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path

from wildlife.domain.codes import Evidence, Identification
from wildlife.domain.dates import uk_local
from wildlife.domain.errors import ImportFileError

SOURCE = "inaturalist"
OBSERVATION_URL = "https://www.inaturalist.org/observations/{}"
NEEDED = ("id", "observed_on", "scientific_name", "latitude", "longitude")
MAX_NOTES, MAX_LOCATION_TEXT, MAX_UNCERTAINTY = 10_000, 200, 100_000
MAX_FILE = 500 * 1024 * 1024  # far more than any export, but not unlimited

# iNaturalist's broad "iconic" groups -> the kingdom used to tell apart names shared
# between kingdoms (Prunella is both the Dunnock's genus and Selfheal's).
_PLANT_FUNGUS = {"Plantae": "Plantae", "Fungi": "Fungi"}
_NOT_ANIMAL = {"", "Protozoa", "Chromista", "Bacteria", "Archaea", "Viruses"}

# "2026-05-03 07:40:12", "2026-05-03T07:40:12+01:00", "2026/05/03 7:40 AM", "2026-05-03"
_ENTERED = re.compile(
    r"^\s*(\d{4})[-/](\d{1,2})[-/](\d{1,2})"
    r"(?:[ T](\d{1,2}):(\d{2})(?::\d{2}(?:\.\d+)?)?\s*([AaPp][Mm])?)?"
)


@dataclass(frozen=True, slots=True)
class InatRecord:
    line: int  # line in the file (the header is line 1), for messages
    source_id: str
    url: str
    observed_date: date | None
    observed_time: str | None  # 'HH:MM', UK clock time
    latitude: float | None
    longitude: float | None
    uncertainty_m: int | None
    location_text: str | None
    notes: str | None
    identification: Identification
    evidence: Evidence
    is_not_wild: bool
    scientific_name: str | None
    common_name: str | None
    kingdom: str | None  # 'Animalia', 'Plantae', 'Fungi' or None if unknown
    image_url: str | None
    updated_at: str | None  # iNaturalist's "last changed", to spot later edits there
    problem: str | None = None  # why this row can't be imported

    @property
    def name(self) -> str:
        return self.scientific_name or self.common_name or "(no name)"


def is_inaturalist(header: list[str]) -> bool:
    """Does this CSV header look like an iNaturalist export?"""
    return all(col in header for col in NEEDED) and (
        "quality_grade" in header or "iconic_taxon_name" in header
    )


def read_file(path: Path) -> list[InatRecord]:
    """Read an export: the .csv, or the .zip iNaturalist downloads it in.
    Raises ImportFileError if it isn't an iNaturalist export."""
    try:
        raw = _zipped_csv(path) if zipfile.is_zipfile(path) else path.read_bytes()
    except (OSError, zipfile.BadZipFile) as exc:
        raise ImportFileError("The file couldn't be opened. Is it still there?") from exc
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")  # re-saved by Excel
    return read_text(text)


def _zipped_csv(path: Path) -> bytes:
    with zipfile.ZipFile(path) as archive:
        csvs = [i for i in archive.infolist() if i.filename.lower().endswith(".csv")]
        if not csvs:
            raise ImportFileError("There's no .csv file inside this .zip.")
        if csvs[0].file_size > MAX_FILE:
            raise ImportFileError("The file inside this .zip is too large to be an export.")
        return archive.read(csvs[0])


def read_text(text: str) -> list[InatRecord]:
    reader = csv.DictReader(io.StringIO(text, newline=""))
    header = [h.strip() for h in reader.fieldnames or []]
    if not is_inaturalist(header):
        raise ImportFileError(
            "This doesn't look like an iNaturalist export. On iNaturalist, choose "
            "Your observations › Export, then pick the CSV file it gives you."
        )
    reader.fieldnames = header
    return [parse_row(i + 2, row) for i, row in enumerate(reader)]


def _text(row: dict, key: str) -> str | None:
    value = (row.get(key) or "").strip()
    return value or None


def _float(row: dict, key: str) -> float | None:
    try:
        return float(row[key]) if _text(row, key) else None
    except ValueError:
        return None


def _when(row: dict) -> tuple[date | None, str | None]:
    """The date and UK clock time. The time as the observer entered it is used when
    it can be read (it's the clock they saw); otherwise iNaturalist's UTC time is
    turned into UK time."""
    entered = _text(row, "observed_on_string") or ""
    if m := _ENTERED.match(entered):
        y, mo, d, h, mi, ampm = m.groups()
        try:
            day = date(int(y), int(mo), int(d))
            if h is None:
                return day, None
            hour = int(h)
            if ampm:
                hour = hour % 12 + (12 if ampm.lower() == "pm" else 0)
            if hour < 24 and int(mi) < 60:
                return day, f"{hour:02d}:{int(mi):02d}"
        except ValueError:
            pass
    utc = _text(row, "time_observed_at")
    if utc:
        try:
            moment = uk_local(datetime.fromisoformat(utc.removesuffix(" UTC")))
            return moment.date(), moment.strftime("%H:%M")
        except ValueError:
            pass
    try:
        return date.fromisoformat(_text(row, "observed_on") or ""), None
    except ValueError:
        return None, None


def _position(row: dict) -> tuple[float | None, float | None, int | None]:
    """Latitude, longitude and uncertainty. The exact position is used when the export
    includes it (your own obscured records); otherwise the public one, with the extra
    uncertainty iNaturalist added by obscuring it."""
    lat, lon = _float(row, "private_latitude"), _float(row, "private_longitude")
    accuracy = _float(row, "positional_accuracy")
    if lat is None or lon is None:
        lat, lon = _float(row, "latitude"), _float(row, "longitude")
        public = _float(row, "public_positional_accuracy")
        if _text(row, "coordinates_obscured") == "true" and public is not None:
            accuracy = max(accuracy or 0, public)
    if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
        return None, None, None
    uncertainty = None
    if accuracy is not None and accuracy > 0:
        uncertainty = min(max(round(accuracy), 1), MAX_UNCERTAINTY)
    return round(lat, 6), round(lon, 6), uncertainty


def _notes(row: dict) -> str | None:
    parts = [_text(row, "description")]
    if tags := _text(row, "tag_list"):
        parts.append(f"Tags: {tags}")
    notes = "\n\n".join(p for p in parts if p)
    return notes[:MAX_NOTES] or None


def parse_row(line: int, row: dict) -> InatRecord:
    source_id = _text(row, "id") or ""
    day, clock = _when(row)
    lat, lon, uncertainty = _position(row)
    iconic = _text(row, "iconic_taxon_name") or ""
    kingdom = _PLANT_FUNGUS.get(iconic) or (None if iconic in _NOT_ANIMAL else "Animalia")
    scientific = _text(row, "scientific_name")
    # Not identified yet on iNaturalist: the observer's own guess may still name it
    common = _text(row, "common_name") or (None if scientific else _text(row, "species_guess"))
    place = _text(row, "private_place_guess") or _text(row, "place_guess")
    image = _text(row, "image_url")
    sound_only = bool(_text(row, "sound_url")) and not image
    problem = None
    if not source_id:
        problem = "No iNaturalist id"
    elif day is None:
        problem = "No date"
    elif not scientific and not common:
        problem = "Not identified yet"
    return InatRecord(
        line=line,
        source_id=source_id,
        url=_text(row, "url") or OBSERVATION_URL.format(source_id),
        observed_date=day,
        observed_time=clock,
        latitude=lat,
        longitude=lon,
        uncertainty_m=uncertainty,
        location_text=place[:MAX_LOCATION_TEXT] if place else None,
        notes=_notes(row),
        identification=(
            Identification.CERTAIN
            if _text(row, "quality_grade") == "research"
            else Identification.PROBABLE
        ),
        evidence=Evidence.HEARD if sound_only else Evidence.SEEN,
        is_not_wild=_text(row, "captive_cultivated") == "true",
        scientific_name=scientific,
        common_name=common,
        kingdom=kingdom,
        image_url=image,
        updated_at=_text(row, "updated_at"),
        problem=problem,
    )
