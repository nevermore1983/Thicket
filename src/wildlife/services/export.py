"""Exporting sightings: to share them, submit them, or keep a complete copy.

Two kinds of export:

* **For sharing** (a spreadsheet, Darwin Core for iRecord / NBN Atlas / GBIF, or map
  data): locations can be blurred to a 1 km or 10 km square, and photos can be added
  (as a .zip), with where they were taken removed.
* **Complete** (Thicket data as JSON, or a .zip with every photo): everything, exact,
  and Thicket can import it again, here or on another PC.

Files are written to a temporary name and renamed when complete, so a half-written
export never looks finished.
"""

from __future__ import annotations

import csv
import io
import json
import logging
import re
import sqlite3
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from wildlife import __version__
from wildlife.config.paths import DataPaths
from wildlife.data.db import Database
from wildlife.data.migrate import current_version
from wildlife.data.repositories import exchange as repo
from wildlife.data.repositories import taxa as taxa_repo
from wildlife.domain.codes import (
    CountQualifier,
    Evidence,
    Habitat,
    Identification,
    LifeStage,
    Sex,
)
from wildlife.domain.filters import SightingFilter
from wildlife.domain.geo import generalise, grid_ref_for
from wildlife.domain.photo_privacy import jpeg_without_gps
from wildlife.services.photos import open_image
from wildlife.services.settings import SettingsService

log = logging.getLogger(__name__)
Progress = Callable[[int, int], None]

FORMAT_NAME = "wildlife-export"
FORMAT_VERSION = 1


@dataclass(frozen=True, slots=True)
class ExportFormat:
    key: str
    label: str
    suffix: str
    for_sharing: bool  # offers blurring and photos-with-GPS-removed
    description: str


FORMATS = {
    f.key: f
    for f in (
        ExportFormat(
            "csv",
            "Spreadsheet (CSV)",
            ".csv",
            True,
            "One row per sighting, for Excel or Google Sheets.",
        ),
        ExportFormat(
            "dwc",
            "Darwin Core (CSV)",
            ".csv",
            True,
            "The standard for biological records: for iRecord, the NBN Atlas, GBIF "
            "or your local records centre.",
        ),
        ExportFormat(
            "geojson",
            "Map data (GeoJSON)",
            ".geojson",
            True,
            "Points for mapping software such as QGIS or uMap. Sightings without a "
            "location are left out.",
        ),
        ExportFormat(
            "json",
            "Thicket data (JSON)",
            ".json",
            False,
            "Everything except photo files, exact. Thicket can import it again.",
        ),
        ExportFormat(
            "archive",
            "Everything, with photos (.zip)",
            ".zip",
            False,
            "All your sightings, places and outings and every photo file, plus spreadsheet and Darwin "
            "Core copies and a README. Thicket can import it again.",
        ),
    )
}


@dataclass(frozen=True, slots=True)
class ExportOptions:
    format: str
    flt: SightingFilter = field(default_factory=SightingFilter)
    blur_m: int = 0  # 0 = exact; 1000 or 10000 = the centre of that grid square
    with_photos: bool = False  # sharing formats: a .zip with the file and the photos
    strip_gps: bool = True  # remove where photos were taken from the shared copies

    @property
    def suffix(self) -> str:
        fmt = FORMATS[self.format]
        return ".zip" if fmt.for_sharing and self.with_photos else fmt.suffix


@dataclass
class ExportSummary:
    path: Path
    sightings: int
    photos: int = 0
    without_location: int = 0  # left out of map data
    missing_photos: list[str] = field(default_factory=list)  # files not found in the library

    def describe(self) -> str:
        parts = [f"{self.sightings:,} sighting{'s' if self.sightings != 1 else ''}"]
        if self.photos:
            parts.append(f"{self.photos:,} photo{'s' if self.photos != 1 else ''}")
        if self.without_location:
            parts.append(f"{self.without_location:,} without a location left out")
        if self.missing_photos:
            parts.append(f"{len(self.missing_photos):,} photo files missing")
        return " · ".join(parts)


# ---- turning rows into the formats ------------------------------------------------------
CSV_COLUMNS = (
    "Date",
    "Time",
    "Species",
    "Scientific name",
    "Category",
    "Count",
    "Count type",
    "Evidence",
    "Identification",
    "Sex",
    "Life stage",
    "Habitat",
    "Wild",
    "Place",
    "Location description",
    "Latitude",
    "Longitude",
    "Uncertainty (m)",
    "Grid reference",
    "Location blurred",
    "Outing",
    "Notes",
    "Photos",
    "Imported from",
    "Source ID",
    "Species key (UKSI)",
    "Thicket ID",
)
DWC_COLUMNS = (
    "occurrenceID",
    "basisOfRecord",
    "eventID",
    "eventDate",
    "scientificName",
    "scientificNameAuthorship",
    "vernacularName",
    "taxonRank",
    "taxonID",
    "nameAccordingTo",
    "kingdom",
    "identificationQualifier",
    "individualCount",
    "occurrenceStatus",
    "sex",
    "lifeStage",
    "habitat",
    "samplingProtocol",
    "degreeOfEstablishment",
    "decimalLatitude",
    "decimalLongitude",
    "coordinateUncertaintyInMeters",
    "geodeticDatum",
    "verbatimCoordinates",
    "verbatimCoordinateSystem",
    "countryCode",
    "locality",
    "dataGeneralizations",
    "recordedBy",
    "occurrenceRemarks",
    "associatedMedia",
    "modified",
)
SOURCE_LABELS = {
    "inaturalist": "iNaturalist",
    "ebird": "eBird",
    "csv": "Spreadsheet",
    "wildlife": "Thicket export",
}


@dataclass(frozen=True, slots=True)
class Spot:
    """Where a sighting was, as it will be shared."""

    latitude: float | None
    longitude: float | None
    uncertainty_m: int | None
    grid_ref: str | None
    blurred: str  # '' or e.g. '1 km square'


def spot_of(row: sqlite3.Row, blur_m: int) -> Spot:
    lat, lon, unc = row["eff_latitude"], row["eff_longitude"], row["eff_uncertainty_m"]
    if lat is None:
        return Spot(None, None, None, None, "")
    if blur_m:
        g = generalise(lat, lon, blur_m)
        label = "1 km square" if blur_m == 1_000 else "10 km square"
        return Spot(g.latitude, g.longitude, max(g.uncertainty_m, unc or 0), g.grid_ref, label)
    return Spot(round(lat, 6), round(lon, 6), unc, grid_ref_for(lat, lon, unc), "")


def _label(enum, value) -> str:
    return enum(value).label if value else ""


GBIF_KEY = "gbif:"  # species from a GBIF species pack (data/migrations/0007_…)


def uksi_key(key: str | None) -> str | None:
    """A UK Species Inventory key, or None (a species from a GBIF pack, or your own)."""
    return key if key and not key.startswith(GBIF_KEY) else None


def taxon_id_of(key: str | None) -> str:
    """Darwin Core taxonID: the UKSI key, or the species' page on GBIF."""
    if key and key.startswith(GBIF_KEY):
        return f"https://www.gbif.org/species/{key.removeprefix(GBIF_KEY)}"
    return key or ""


def name_source(key: str | None) -> str:
    """Darwin Core nameAccordingTo: where the species' name comes from."""
    if not key:
        return ""
    return "GBIF Backbone Taxonomy" if key.startswith(GBIF_KEY) else "UK Species Inventory"


def csv_row(row: sqlite3.Row, spot: Spot, photos: list[str], photo_count: int) -> list:
    exact = not spot.blurred
    return [
        row["observed_date"],
        row["observed_time"] or "",
        row["common_name"] or "",
        row["scientific_name"],
        row["category_name"],
        row["count"] if row["count"] is not None else "",
        _label(CountQualifier, row["count_qualifier"]) if row["count"] is not None else "",
        _label(Evidence, row["evidence"]),
        _label(Identification, row["identification"]),
        _label(Sex, row["sex"]),
        _label(LifeStage, row["life_stage"]),
        _label(Habitat, row["habitat"]),
        "No" if row["is_not_wild"] else "Yes",
        (row["place_name"] or "") if exact else "",
        (row["location_text"] or "") if exact else "",
        spot.latitude if spot.latitude is not None else "",
        spot.longitude if spot.longitude is not None else "",
        spot.uncertainty_m or "",
        spot.grid_ref or "",
        spot.blurred,
        row["outing_title"] or (row["outing_date"] or ""),
        row["notes"] or "",
        "; ".join(photos) if photos else (photo_count or ""),
        SOURCE_LABELS.get(row["source"] or "", row["source"] or ""),
        row["source_id"] or "",
        uksi_key(row["catalogue_key"]) or "",
        row["uuid"],
    ]


def dwc_row(row: sqlite3.Row, spot: Spot, photos: list[str], recorder: str) -> list:
    when = row["observed_date"] + (f"T{row['observed_time']}" if row["observed_time"] else "")
    exact = not spot.blurred
    locality = ", ".join(x for x in (row["place_name"], row["location_text"]) if x)
    generalised = ""
    if spot.blurred:
        where = f" {spot.grid_ref}" if spot.grid_ref else ""
        generalised = f"Coordinates generalised to the centre of the {spot.blurred}{where}"
    identification = row["identification"]
    return [
        row["uuid"],
        "HumanObservation",
        row["outing_uuid"] or "",
        when,
        row["scientific_name"],
        row["authority"] or "",
        row["common_name"] or "",
        row["rank"] if row["rank"] in ("species", "subspecies", "genus", "family") else "",
        taxon_id_of(row["catalogue_key"]),
        name_source(row["catalogue_key"]),
        row["tax_kingdom"] or "",
        "" if identification == "certain" else "cf.",
        row["count"] if row["count"] is not None else "",
        "present",
        row["sex"] or "",
        _label(LifeStage, row["life_stage"]).lower(),
        _label(Habitat, row["habitat"]).lower(),
        "trap" if row["evidence"] == "trapped" else "",
        "captive" if row["is_not_wild"] else "",
        spot.latitude if spot.latitude is not None else "",
        spot.longitude if spot.longitude is not None else "",
        spot.uncertainty_m or "",
        "WGS84" if spot.latitude is not None else "",
        spot.grid_ref or "",
        "British National Grid" if spot.grid_ref else "",
        "GB" if spot.grid_ref else "",
        locality if exact else "",
        generalised,
        recorder,
        row["notes"] or "",
        " | ".join(photos),
        row["updated_at"],
    ]


def geojson_feature(row: sqlite3.Row, spot: Spot, photos: list[str]) -> dict:
    exact = not spot.blurred
    props = {
        "id": row["uuid"],
        "date": row["observed_date"],
        "time": row["observed_time"],
        "species": row["common_name"] or row["scientific_name"],
        "scientific_name": row["scientific_name"],
        "category": row["category_name"],
        "count": row["count"],
        "evidence": row["evidence"],
        "identification": row["identification"],
        "uncertainty_m": spot.uncertainty_m,
        "grid_ref": spot.grid_ref,
        "place": row["place_name"] if exact else None,
        "blurred": spot.blurred or None,
        "notes": row["notes"],
    }
    if photos:
        props["photos"] = photos
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [spot.longitude, spot.latitude]},
        "properties": {k: v for k, v in props.items() if v not in (None, "")},
    }


def _write_csv(columns, rows) -> bytes:
    out = io.StringIO()
    writer = csv.writer(out, lineterminator="\r\n")
    writer.writerow(columns)
    writer.writerows([safe_cell(c) for c in row] for row in rows)
    return ("﻿" + out.getvalue()).encode("utf-8")  # the BOM tells Excel it's UTF-8


FORMULA_START = ("=", "+", "-", "@", "\t", "\r")


def safe_cell(value):
    """Text that Excel would run as a formula (it starts with = + - or @) gets a leading
    ' so it stays text. Numbers, such as a negative longitude, are left as they are.
    Thicket's spreadsheet import takes the ' off again (domain/csv_import.py)."""
    if not isinstance(value, str) or not value.startswith(FORMULA_START):
        return value
    try:
        float(value)
    except ValueError:
        return "'" + value
    return value


_UNSAFE = re.compile(r"[^A-Za-z0-9 ._-]+")


def photo_name(row: sqlite3.Row, n: int, suffix: str) -> str:
    """'2026-05-03 Robin 1.jpg': readable, and safe as a file name everywhere."""
    species = _UNSAFE.sub("", row["common_name"] or row["scientific_name"]).strip()[:60]
    return f"{row['observed_date']} {species or 'sighting'} {row['id']}-{n}{suffix}"


# ---- the service ------------------------------------------------------------------------
class ExportService:
    def __init__(self, paths: DataPaths, db: Database, settings: SettingsService) -> None:
        self._paths, self._db, self._settings = paths, db, settings

    def count(self, flt: SightingFilter) -> int:
        with self._db.connection() as conn:
            return len(repo.sightings(conn, flt))

    def export(
        self, options: ExportOptions, dest: Path, progress: Progress = lambda d, t: None
    ) -> ExportSummary:
        fmt = FORMATS[options.format]
        dest = dest.with_suffix(options.suffix) if dest.suffix.lower() != options.suffix else dest
        part = dest.with_name(dest.name + ".part")
        with self._db.connection() as conn:
            rows = repo.sightings(conn, options.flt)
            photo_rows = repo.photos_of(conn, [r["id"] for r in rows])
            summary = ExportSummary(dest, len(rows))
            try:
                if options.format == "archive":
                    self._archive(conn, options, rows, photo_rows, part, summary, progress)
                elif options.format == "json":
                    part.write_bytes(self._json(conn, options, rows, photo_rows, {}))
                elif options.with_photos:
                    self._shared_zip(options, rows, photo_rows, part, summary, progress)
                else:
                    part.write_bytes(self._shared_file(options, rows, photo_rows, {}, summary))
                part.replace(dest)
            except BaseException:
                part.unlink(missing_ok=True)
                raise
        log.info("Exported %s (%s): %s", dest.name, fmt.key, summary.describe())
        return summary

    # ---- sharing formats ----------------------------------------------------------------
    def _shared_file(
        self, options, rows, photo_rows, names: dict[int, list[str]], summary
    ) -> bytes:
        recorder = self._settings.current.recorder_name
        if options.format == "geojson":
            features = []
            for r in rows:
                spot = spot_of(r, options.blur_m)
                if spot.latitude is None:
                    summary.without_location += 1
                    continue
                features.append(geojson_feature(r, spot, names.get(r["id"], [])))
            data = {"type": "FeatureCollection", "features": features}
            return json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")
        if options.format == "dwc":
            body = [
                dwc_row(r, spot_of(r, options.blur_m), names.get(r["id"], []), recorder)
                for r in rows
            ]
            return _write_csv(DWC_COLUMNS, body)
        body = [
            csv_row(
                r,
                spot_of(r, options.blur_m),
                names.get(r["id"], []),
                len(photo_rows.get(r["id"], [])),
            )
            for r in rows
        ]
        return _write_csv(CSV_COLUMNS, body)

    def _shared_zip(self, options, rows, photo_rows, part, summary, progress) -> None:
        fmt = FORMATS[options.format]
        names: dict[int, list[str]] = {}
        total = sum(len(v) for v in photo_rows.values())
        done = 0
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
            for r in rows:
                for n, p in enumerate(photo_rows.get(r["id"], []), 1):
                    progress(done, total)
                    done += 1
                    source = self._paths.root / p["rel_path"]
                    if not source.exists():
                        summary.missing_photos.append(p["original_name"])
                        continue
                    data, suffix = self._shareable_photo(source, p["rotation"], options.strip_gps)
                    name = f"photos/{photo_name(r, n, suffix)}"
                    z.writestr(zipfile.ZipInfo(name, _zip_time(p)), data, zipfile.ZIP_STORED)
                    names.setdefault(r["id"], []).append(name)
                    summary.photos += 1
            z.writestr(
                f"{'darwin-core' if options.format == 'dwc' else 'sightings'}{fmt.suffix}",
                self._shared_file(options, rows, photo_rows, names, summary),
            )
        progress(total, total)

    @staticmethod
    def _shareable_photo(path: Path, rotation: int, strip_gps: bool) -> tuple[bytes, str]:
        """A photo for sharing. With strip_gps: a JPEG with its location removed and the
        picture untouched; other formats (and photos turned in Thicket) are saved as a
        new JPEG, which carries no location at all."""
        suffix = path.suffix.lower()
        data = path.read_bytes()
        if not strip_gps and not rotation:
            return data, suffix
        if suffix in (".jpg", ".jpeg") and not rotation:
            try:
                return jpeg_without_gps(data), ".jpg"
            except ValueError:
                pass  # not really a JPEG: make a fresh one below
        out = io.BytesIO()
        open_image(path, rotation).save(out, "JPEG", quality=92)
        return out.getvalue(), ".jpg"

    # ---- complete formats ---------------------------------------------------------------
    def _json(self, conn, options, rows, photo_rows, files: dict[int, dict]) -> bytes:
        """Thicket's own format: every field, linked by uuid. `files` maps a photo id to
        where its files are inside an archive."""
        everything = options.flt.is_empty
        taxon_ids = {r["taxon_id"] for r in rows}
        place_ids = {r["place_id"] for r in rows if r["place_id"]}
        outing_ids = {r["outing_id"] for r in rows if r["outing_id"]}
        outings = repo.outings(conn, None if everything else outing_ids)
        place_ids |= {o["place_id"] for o in outings if o["place_id"]}
        photos = {p["id"]: p for v in photo_rows.values() for p in v}
        data = {
            "format": FORMAT_NAME,
            "format_version": FORMAT_VERSION,
            "exported_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "app_version": __version__,
            "schema_version": current_version(conn),
            "recorder": self._settings.current.recorder_name,
            "species_list": taxa_repo.get_meta(conn, "catalogue_version"),
            "complete": everything,
            "taxa": [_taxon_json(t) for t in repo.taxa(conn, taxon_ids, everything)],
            "places": [
                _place_json(p) for p in repo.places(conn, None if everything else place_ids)
            ],
            "outings": [_outing_json(o) for o in outings],
            "photos": [_photo_json(p, files.get(p["id"], {})) for p in photos.values()],
            "sightings": [
                _sighting_json(r, [p["uuid"] for p in photo_rows.get(r["id"], [])]) for r in rows
            ],
            "species_notes": [
                {
                    "taxon": _keys(n["catalogue_key"]) | {"scientific_name": n["scientific_name"]},
                    "notes": n["notes"],
                }
                for n in repo.species_notes(conn, None if everything else taxon_ids)
            ],
        }
        return json.dumps(data, ensure_ascii=False, indent=1).encode("utf-8")

    def _archive(self, conn, options, rows, photo_rows, part, summary, progress) -> None:
        photos = {p["id"]: p for v in photo_rows.values() for p in v}
        total = len(photos)
        files: dict[int, dict] = {}
        with zipfile.ZipFile(part, "w", zipfile.ZIP_DEFLATED) as z:
            for i, p in enumerate(photos.values()):
                progress(i, total)
                entry: dict = {}
                for key, rel in (("file", p["rel_path"]), ("raw_file", p["raw_rel_path"])):
                    if not rel:
                        continue
                    source = self._paths.root / rel
                    if not source.exists():
                        summary.missing_photos.append(rel)
                        continue
                    # Photos are already compressed: storing them is as small and much faster
                    z.write(source, rel, zipfile.ZIP_STORED)
                    entry[key] = rel
                files[p["id"]] = entry
                summary.photos += "file" in entry
            z.writestr("wildlife-export.json", self._json(conn, options, rows, photo_rows, files))
            plain = ExportOptions("csv", options.flt)
            z.writestr("sightings.csv", self._shared_file(plain, rows, photo_rows, {}, summary))
            dwc = ExportOptions("dwc", options.flt)
            z.writestr("darwin-core.csv", self._shared_file(dwc, rows, photo_rows, {}, summary))
            z.writestr("README.txt", _readme(len(rows), summary.photos))
        progress(total, total)


def _zip_time(photo) -> tuple:
    taken = photo["taken_at"] or "1980-01-01 00:00:00"
    try:
        t = datetime.strptime(taken[:19], "%Y-%m-%d %H:%M:%S")
        return (max(t.year, 1980), t.month, t.day, t.hour, t.minute, t.second)
    except ValueError:
        return (1980, 1, 1, 0, 0, 0)


def _keys(key: str | None) -> dict:
    """A species' keys in Thicket's own export: `catalogue_key` (any pack's) and, for
    older versions of Thicket reading it, `uksi_key` (UK species only)."""
    return {"catalogue_key": key, "uksi_key": uksi_key(key)}


def _pick(row: sqlite3.Row, *keys: str) -> dict:
    return {k: row[k] for k in keys}


def _taxon_json(t) -> dict:
    return (
        _keys(t["catalogue_key"])
        | _pick(
            t,
            "scientific_name",
            "authority",
            "common_name",
            "rank",
            "is_custom",
            "tax_kingdom",
            "tax_phylum",
            "tax_class",
            "tax_order",
            "tax_family",
        )
        | {"category": t["category_name"]}
    )


def _place_json(p) -> dict:
    return _pick(
        p,
        "uuid",
        "name",
        "latitude",
        "longitude",
        "radius_m",
        "habitat",
        "notes",
        "is_favourite",
        "is_archived",
        "created_at",
    )


def _outing_json(o) -> dict:
    return _pick(
        o,
        "uuid",
        "outing_date",
        "start_time",
        "end_time",
        "title",
        "weather",
        "temperature_c",
        "wind",
        "visibility",
        "is_complete_list",
        "notes",
        "created_at",
    ) | {"place": o["place_uuid"]}


def _photo_json(p, files: dict) -> dict:
    return (
        _pick(
            p,
            "uuid",
            "sha256",
            "original_name",
            "taken_at",
            "gps_latitude",
            "gps_longitude",
            "rotation",
            "caption",
            "camera",
            "raw_name",
            "raw_sha256",
            "source",
            "source_id",
        )
        | files
    )


def _sighting_json(r, photo_uuids: list[str]) -> dict:
    return _pick(
        r,
        "uuid",
        "observed_date",
        "observed_time",
        "latitude",
        "longitude",
        "uncertainty_m",
        "location_method",
        "location_text",
        "count",
        "count_qualifier",
        "evidence",
        "identification",
        "sex",
        "life_stage",
        "habitat",
        "is_not_wild",
        "notes",
        "source",
        "source_id",
        "source_updated_at",
        "created_at",
        "updated_at",
    ) | {
        "taxon": _keys(r["catalogue_key"])
        | {
            "scientific_name": r["scientific_name"],
            "common_name": r["common_name"],
        },
        "place": r["place_uuid"],
        "outing": r["outing_uuid"],
        "photos": photo_uuids,
    }


def _readme(sightings: int, photos: int) -> str:
    return f"""Thicket export
==============

Made by Thicket {__version__} on {datetime.now().strftime("%d %B %Y")}: {sightings:,} sightings, {photos:,} photos.

What's in this folder
---------------------
wildlife-export.json  Everything, exactly: species, places, outings, sightings and photo
                      details, linked by their ids. Thicket can import this file (or this
                      whole .zip) again: Settings > Import > Thicket export.
sightings.csv         One row per sighting, for Excel or Google Sheets.
darwin-core.csv       The same sightings in Darwin Core, the standard for biological records
                      (accepted by iRecord, the NBN Atlas and GBIF).
photos/               Your photo files, unchanged, in folders by year and month. A RAW
                      original (e.g. a .dng) sits next to its JPEG.

Notes
-----
* Dates and times are UK clock time. Positions are WGS84 latitude/longitude; uncertainty
  is a radius in metres. Grid references are British National Grid.
* Species names come from the UK Species Inventory (Natural History Museum, CC BY 4.0).
  "Species key (UKSI)" / taxonID is the UKSI taxon version key.
* Files are UTF-8. The CSV files start with a byte-order mark so Excel reads accents.
"""
