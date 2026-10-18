"""Reading sightings from any spreadsheet saved as CSV.

Every spreadsheet names its columns differently, so the columns are *mapped*:
WildLife guesses which column holds what (it knows its own export, Darwin Core,
iRecord-style and common English headings), and you can change the guess before
importing. Each row then becomes an ordinary `ImportRecord`.

Dates are read the UK way: 03/05/2026 is 3 May 2026.
"""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from wildlife.domain.codes import (
    CountQualifier,
    Evidence,
    Habitat,
    Identification,
    LifeStage,
    Sex,
)
from wildlife.domain.errors import ImportFileError
from wildlife.domain.geo import grid_to_wgs84, parse_grid_ref
from wildlife.domain.import_records import ImportRecord

SOURCE = "csv"
MAX_ROWS = 200_000


@dataclass(frozen=True, slots=True)
class Field:
    key: str
    label: str
    names: tuple[str, ...]  # column headings that mean this, lower case
    required: bool = False


FIELDS = (
    Field(
        "species",
        "Species (English name)",
        (
            "species",
            "common name",
            "english name",
            "vernacularname",
            "vernacular name",
            "species name",
            "name",
            "common_name",
            "bird",
            "animal",
            "plant",
            "organism",
            "what",
        ),
    ),
    Field(
        "scientific",
        "Scientific name",
        (
            "scientific name",
            "scientificname",
            "latin name",
            "taxon",
            "taxon name",
            "scientific_name",
            "binomial",
        ),
    ),
    Field(
        "date",
        "Date",
        (
            "date",
            "eventdate",
            "event date",
            "observed_on",
            "date seen",
            "observation date",
            "sample date",
            "day",
        ),
        required=True,
    ),
    Field("time", "Time", ("time", "eventtime", "event time", "time seen", "observed time")),
    Field("latitude", "Latitude", ("latitude", "lat", "decimallatitude", "decimal latitude", "y")),
    Field(
        "longitude",
        "Longitude",
        ("longitude", "lon", "long", "lng", "decimallongitude", "decimal longitude", "x"),
    ),
    Field(
        "grid_ref",
        "Grid reference",
        (
            "grid reference",
            "grid ref",
            "gridref",
            "os grid ref",
            "os grid reference",
            "gridreference",
            "verbatimcoordinates",
            "spatial reference",
        ),
    ),
    Field(
        "uncertainty",
        "Uncertainty (m)",
        (
            "uncertainty (m)",
            "uncertainty",
            "accuracy",
            "coordinateuncertaintyinmeters",
            "positional_accuracy",
            "precision",
        ),
    ),
    Field("place", "Place", ("place", "site", "site name", "location name", "locality")),
    Field(
        "location_text",
        "Location description",
        ("location description", "location", "where", "place_guess"),
    ),
    Field(
        "count",
        "Count",
        ("count", "individualcount", "number", "quantity", "abundance", "how many", "no."),
    ),
    Field("count_type", "Count type", ("count type", "count qualifier", "count accuracy")),
    Field(
        "notes",
        "Notes",
        ("notes", "note", "comments", "comment", "occurrenceremarks", "remarks", "description"),
    ),
    Field("evidence", "Evidence", ("evidence", "seen/heard", "record type")),
    Field(
        "identification",
        "Identification",
        ("identification", "id confidence", "certainty", "identificationqualifier"),
    ),
    Field("sex", "Sex", ("sex", "gender")),
    Field("life_stage", "Life stage", ("life stage", "lifestage", "stage", "age")),
    Field("habitat", "Habitat", ("habitat",)),
    Field("wild", "Wild", ("wild", "degreeofestablishment", "captive/cultivated")),
    Field(
        "uksi_key",
        "Species key (UKSI)",
        ("species key (uksi)", "taxonid", "tvk", "taxon version key", "uksi key"),
    ),
)
FIELD_KEYS = tuple(f.key for f in FIELDS)


@dataclass(frozen=True, slots=True)
class Table:
    """A CSV file's header and rows (cells as text)."""

    name: str
    header: list[str]
    rows: list[list[str]]

    def samples(self, column: int, n: int = 3) -> list[str]:
        """The first few non-empty values in a column, to show while mapping."""
        out = []
        for row in self.rows:
            if column < len(row) and row[column].strip():
                out.append(row[column].strip())
                if len(out) == n:
                    break
        return out


def read_table(path: Path) -> Table:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise ImportFileError("The file couldn't be opened. Is it still there?") from exc
    if raw[:2] == b"PK":
        raise ImportFileError(
            "This looks like an Excel workbook. In Excel, choose File › Save As › "
            "CSV UTF-8, then import the .csv file."
        )
    try:
        text = raw.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = raw.decode("cp1252", errors="replace")  # an older Excel CSV
    return read_table_text(text, path.name)


def read_table_text(text: str, name: str = "sightings.csv") -> Table:
    sample = text[:20_000]
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t")
    except csv.Error:
        dialect = csv.excel
    rows = [
        r for r in csv.reader(io.StringIO(text, newline=""), dialect) if any(c.strip() for c in r)
    ]
    if len(rows) < 2:
        raise ImportFileError("The file has no rows to import (it needs a heading row too).")
    if len(rows) > MAX_ROWS:
        raise ImportFileError(f"The file has more than {MAX_ROWS:,} rows. Please split it.")
    header = [h.strip() for h in rows[0]]
    return Table(name, header, rows[1:])


def guess_mapping(header: list[str]) -> dict[str, int]:
    """field key -> column index, for the columns whose heading WildLife recognises."""
    found: dict[str, int] = {}
    lowered = [h.strip().lower() for h in header]
    for f in FIELDS:
        for i, h in enumerate(lowered):
            if h in f.names and i not in found.values():
                found[f.key] = i
                break
    return found


# ---- reading values ----------------------------------------------------------------------
_MONTHS = {
    m: i
    for i, m in enumerate(
        ("jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"), 1
    )
}
_ISO = re.compile(r"^(\d{4})-(\d{1,2})-(\d{1,2})(?:[T ](.*))?$")
_NUMERIC = re.compile(r"^(\d{1,2})[/.-](\d{1,2})[/.-](\d{2}|\d{4})(?:\s+(.*))?$")
_WORDS = re.compile(r"^(\d{1,2})(?:st|nd|rd|th)?\s+([A-Za-z]{3,9})\.?,?\s+(\d{4})(?:\s+(.*))?$")
_TIME = re.compile(r"^(\d{1,2})[:.](\d{2})(?::\d{2}(?:\.\d+)?)?\s*([AaPp][Mm])?")


def parse_date(text: str, month_first: bool = False) -> tuple[date | None, str | None]:
    """A date (and a time, if one is written with it). Numbers are read day first
    (UK: 3/5/2026 is 3 May), or month first (US: 5 March) if month_first."""
    text = text.strip()
    rest = None
    try:
        if m := _ISO.match(text):
            day, rest = date(int(m[1]), int(m[2]), int(m[3])), m[4]
        elif m := _NUMERIC.match(text):
            year = int(m[3]) + (2000 if len(m[3]) == 2 else 0)
            first, second = int(m[1]), int(m[2])
            month, day_of_month = (first, second) if month_first else (second, first)
            day, rest = date(year, month, day_of_month), m[4]
        elif (m := _WORDS.match(text)) and m[2][:3].lower() in _MONTHS:
            day, rest = date(int(m[3]), _MONTHS[m[2][:3].lower()], int(m[1])), m[4]
        else:
            return None, None
    except ValueError:
        return None, None
    return day, parse_time(rest) if rest else None


def parse_time(text: str) -> str | None:
    if not (m := _TIME.match(text.strip())):
        return None
    hour, minute = int(m[1]), int(m[2])
    if m[3]:
        hour = hour % 12 + (12 if m[3].lower() == "pm" else 0)
    return f"{hour:02d}:{minute:02d}" if hour < 24 and minute < 60 else None


def parse_count(text: str) -> tuple[int | None, CountQualifier]:
    """'12' / 'c. 20' / '~20' / '20+' / 'present' -> (count, how exact)."""
    t = text.strip().lower()
    qualifier = CountQualifier.EXACT
    if t.startswith(("c.", "c ", "ca", "~", "approx", "about")):
        qualifier = CountQualifier.APPROX
    if t.endswith("+") or t.startswith((">", "at least")):
        qualifier = CountQualifier.AT_LEAST
    digits = re.search(r"\d+", t.replace(",", ""))
    if not digits or int(digits[0]) < 1:
        return None, CountQualifier.EXACT
    return int(digits[0]), qualifier


def _code(enum, text: str):
    """A code from its stored value or its label ('seen_heard' or 'Seen & heard')."""
    t = text.strip().lower()
    for member in enum:
        if t in (member.value, member.label.lower()):
            return member
    return None


def _float(text: str) -> float | None:
    try:
        return float(text.strip().replace(",", "."))
    except ValueError:
        return None


def unguard(text: str) -> str:
    """Undo the ' a spreadsheet export puts before text starting with = + - or @ (so
    Excel doesn't run it as a formula): "'=1+1" reads back as "=1+1"."""
    if len(text) > 1 and text[0] == "'" and text[1] in "=+-@":
        return text[1:]
    return text


def to_records(
    table: Table, mapping: dict[str, int], month_first: bool = False
) -> list[ImportRecord]:
    def cell(row: list[str], key: str) -> str:
        i = mapping.get(key)
        return unguard(row[i].strip()) if i is not None and i < len(row) else ""

    records = []
    for n, row in enumerate(table.rows):
        line = n + 2
        problem = None
        day, clock = parse_date(cell(row, "date"), month_first)
        if (t := cell(row, "time")) and (parsed := parse_time(t)):
            clock = parsed
        if day is None:
            raw = cell(row, "date")
            problem = f"Date not understood: “{raw}”" if raw else "No date"
        scientific, common = cell(row, "scientific") or None, cell(row, "species") or None
        key = cell(row, "uksi_key") or None
        if not (scientific or common or key) and not problem:
            problem = "No species"
        lat, lon = _float(cell(row, "latitude")), _float(cell(row, "longitude"))
        uncertainty = _float(cell(row, "uncertainty"))
        if lat is None or lon is None or not (-90 <= lat <= 90 and -180 <= lon <= 180):
            lat = lon = None
            if square := parse_grid_ref(cell(row, "grid_ref")):
                lat, lon = grid_to_wgs84(square.easting, square.northing)
                lat, lon = round(lat, 6), round(lon, 6)
                uncertainty = max(uncertainty or 0, square.size_m * 0.71)  # covers the square
        # An empty count means "not counted": nothing is invented
        count, qualifier = parse_count(cell(row, "count"))
        if count is not None and (stated := _code(CountQualifier, cell(row, "count_type"))):
            qualifier = stated  # e.g. "Approximate" in WildLife's own spreadsheet
        identification = _code(Identification, cell(row, "identification"))
        if identification is None and cell(row, "identification").lower() in ("cf.", "cf", "?"):
            identification = Identification.PROBABLE
        records.append(
            ImportRecord(
                line=line,
                observed_date=day,
                observed_time=clock,
                scientific_name=scientific,
                common_name=common,
                uksi_key=key,
                latitude=lat,
                longitude=lon,
                uncertainty_m=min(max(round(uncertainty), 1), 100_000)
                if uncertainty and lat is not None
                else None,
                place_name=cell(row, "place")[:200] or None,
                location_text=cell(row, "location_text")[:200] or None,
                count=count,
                count_qualifier=qualifier,
                evidence=_code(Evidence, cell(row, "evidence")) or Evidence.SEEN,
                identification=identification or Identification.CERTAIN,
                sex=_code(Sex, cell(row, "sex")),
                life_stage=_code(LifeStage, cell(row, "life_stage")),
                habitat=_code(Habitat, cell(row, "habitat")),
                is_not_wild=cell(row, "wild").lower() in ("no", "n", "false", "captive"),
                notes=cell(row, "notes")[:10_000] or None,
                problem=problem,
            )
        )
    return records


def describe_date_columns(
    table: Table, mapping: dict[str, int], month_first: bool = False
) -> str | None:
    """A warning if the date column looks written the other way round, else None."""
    i = mapping.get("date")
    if i is None:
        return None
    for row in table.rows[:500]:
        if i >= len(row) or not (m := _NUMERIC.match(row[i].strip())):
            continue
        if not month_first and int(m[2]) > 12:
            return (
                "Some dates look like month/day/year (American order), but they're being read "
                "as day/month/year. Choose month/day above if that's how they're written."
            )
        if month_first and int(m[1]) > 12:
            return (
                "Some dates look like day/month/year, but they're being read as "
                "month/day/year (American order). Choose day/month above if that's how "
                "they're written."
            )
    return None
