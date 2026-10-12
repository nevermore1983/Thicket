"""Importing WildLife's own export (the .json, or the .zip with photos).

This is how records move between libraries or PCs, or come back from an export.
Everything is matched by its permanent id (uuid), so importing the same export twice
adds nothing the second time. Species are matched by their UK Species Inventory key,
then by scientific name; a species this library doesn't know is added as one of your
own species, so nothing is lost.
"""

from __future__ import annotations

import json
import logging
import re
import sqlite3
import tempfile
import zipfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from wildlife.config.paths import DataPaths
from wildlife.data.db import Database
from wildlife.data.repositories import exchange as repo
from wildlife.data.repositories import imports as imports_repo
from wildlife.data.repositories import photos as photos_repo
from wildlife.data.repositories import sightings as sightings_repo
from wildlife.domain.errors import ImportFileError
from wildlife.services.events import EventHub
from wildlife.services.export import FORMAT_NAME, FORMAT_VERSION
from wildlife.services.photos import PhotoService
from wildlife.services.sightings import Undo

log = logging.getLogger(__name__)
SOURCE = "wildlife"
JSON_NAME = "wildlife-export.json"
MAX_JSON = 1024 * 1024 * 1024  # 1 GB of text is far beyond any real export
MAX_PHOTO = 500 * 1024 * 1024
_SAFE = re.compile(r"[^A-Za-z0-9 ._()-]+")


@dataclass
class WildlifePlan:
    path: Path
    data: dict
    is_archive: bool
    new_sightings: int = 0
    already: int = 0
    new_places: int = 0
    new_outings: int = 0
    new_species: list[str] = field(default_factory=list)
    photos_to_add: int = 0
    photos_missing: int = 0

    @property
    def file_name(self) -> str:
        return self.path.name

    def describe(self) -> str:
        parts = [f"<b>{self.new_sightings:,}</b> new sightings"]
        if self.already:
            parts.append(f"{self.already:,} already in WildLife")
        if self.new_places:
            parts.append(f"{self.new_places:,} new places")
        if self.new_outings:
            parts.append(f"{self.new_outings:,} new outings")
        if self.photos_to_add:
            parts.append(f"{self.photos_to_add:,} photos")
        return " · ".join(parts)


@dataclass
class WildlifeImportResult:
    batch_id: int
    added: list[int] = field(default_factory=list)
    places: list[int] = field(default_factory=list)
    outings: list[int] = field(default_factory=list)
    species: list[int] = field(default_factory=list)
    photos: list[int] = field(default_factory=list)  # newly brought into the library
    skipped: list[str] = field(default_factory=list)  # what couldn't be imported, and why
    undo: Undo | None = None

    def describe(self) -> str:
        parts = [f"{len(self.added):,} added"]
        if self.photos:
            parts.append(f"{len(self.photos):,} photos")
        if self.skipped:
            parts.append(f"{len(self.skipped):,} skipped")
        return " · ".join(parts)


def read_export(path: Path) -> tuple[dict, bool]:
    """(the export's data, is it an archive with photos?)"""
    try:
        if zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as z:
                try:
                    info = z.getinfo(JSON_NAME)
                except KeyError as exc:
                    raise ImportFileError(
                        "This .zip isn't a WildLife export (it has no wildlife-export.json)."
                    ) from exc
                if info.file_size > MAX_JSON:
                    raise ImportFileError("The export is too large to read.")
                raw, archive = z.read(info), True
        else:
            raw, archive = path.read_bytes(), False
        data = json.loads(raw.decode("utf-8"))
    except (OSError, zipfile.BadZipFile) as exc:
        raise ImportFileError("The file couldn't be opened. Is it still there?") from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ImportFileError("This file isn't a WildLife export, or it's damaged.") from exc
    if not isinstance(data, dict) or data.get("format") != FORMAT_NAME:
        raise ImportFileError("This file isn't a WildLife export.")
    if not isinstance(data.get("format_version"), int) or data["format_version"] > FORMAT_VERSION:
        raise ImportFileError(
            "This export was made by a newer version of WildLife. Please update WildLife first."
        )
    for key in ("taxa", "places", "outings", "photos", "sightings"):
        if not isinstance(data.get(key, []), list):
            raise ImportFileError("This export is damaged (its records are unreadable).")
    return data, archive


class WildlifeImporter:
    def __init__(
        self,
        paths: DataPaths,
        db: Database,
        events: EventHub,
        photos: PhotoService,
    ) -> None:
        self._paths, self._db, self._events, self._photos = paths, db, events, photos

    # ---- step 1: what would happen -----------------------------------------------------
    def preview(self, path: Path) -> WildlifePlan:
        data, archive = read_export(path)
        plan = WildlifePlan(path, data, archive)
        with self._db.connection() as conn:
            sightings = repo.ids_by_uuid(conn, "sighting")
            places = repo.ids_by_uuid(conn, "place")
            outings = repo.ids_by_uuid(conn, "outing")
            photos = repo.ids_by_uuid(conn, "photo")
            by_key, by_name = repo.taxon_lookup(conn)
            new = [s for s in data.get("sightings", []) if s.get("uuid") not in sightings]
            plan.already = len(data.get("sightings", [])) - len(new)
            plan.new_sightings = len(new)
            plan.new_places = sum(1 for p in data.get("places", []) if p.get("uuid") not in places)
            plan.new_outings = sum(
                1 for o in data.get("outings", []) if o.get("uuid") not in outings
            )
            unknown = set()
            for s in new:
                t = s.get("taxon") or {}
                if not (
                    by_key.get(t.get("uksi_key"))
                    or by_name.get((t.get("scientific_name") or "").lower())
                ):
                    unknown.add(t.get("common_name") or t.get("scientific_name") or "?")
            plan.new_species = sorted(unknown)
            wanted = {u for s in new for u in s.get("photos", [])}
            for p in data.get("photos", []):
                if p.get("uuid") not in wanted:
                    continue
                if p["uuid"] in photos or repo.photo_by_sha(conn, p.get("sha256")):
                    continue
                if archive and p.get("file"):
                    plan.photos_to_add += 1
                else:
                    plan.photos_missing += 1
        return plan

    # ---- step 2: import ----------------------------------------------------------------
    def run(
        self, plan: WildlifePlan, progress: Callable[[int, int], None] = lambda d, t: None
    ) -> WildlifeImportResult:
        data = plan.data
        links: list[tuple[int, list[str]]] = []
        with self._db.transaction() as conn:
            batch = imports_repo.new_batch(conn, SOURCE, plan.file_name)
            result = WildlifeImportResult(batch)
            taxa = self._taxon_resolver(conn, data, result)
            place_ids = self._places(conn, data, result)
            outing_ids = self._outings(conn, data, place_ids, result)
            known = repo.ids_by_uuid(conn, "sighting")
            for n, s in enumerate(data.get("sightings", []), 1):
                if s.get("uuid") in known:
                    continue
                try:
                    sid = repo.insert_sighting(
                        conn,
                        s,
                        taxa(s.get("taxon") or {}),
                        place_ids.get(s.get("place")),
                        outing_ids.get(s.get("outing")),
                        batch,
                    )
                except (sqlite3.IntegrityError, KeyError, TypeError) as exc:
                    result.skipped.append(f"Sighting {n}: {_why(exc)}")
                    continue
                result.added.append(sid)
                if s.get("photos"):
                    links.append((sid, list(s["photos"])))
            imports_repo.finish_batch(conn, batch, len(result.added), 0, len(result.skipped))
        self._bring_photos(plan, links, result, progress)
        log.info("WildLife import %s: %s", plan.file_name, result.describe())
        self._events.publish("places", tuple(result.places))
        self._events.publish("outings", tuple(result.outings))
        self._events.publish("sightings", tuple(result.added))
        result.undo = Undo(f"Import of {len(result.added):,} sightings", lambda: self._undo(result))
        return result

    def _taxon_resolver(self, conn, data: dict, result: WildlifeImportResult):
        by_key, by_name = repo.taxon_lookup(conn)
        categories = repo.category_ids(conn)
        fallback = conn.execute("SELECT id FROM category WHERE is_fallback = 1").fetchone()[0]
        details = {(t.get("uksi_key"), t.get("scientific_name")): t for t in data.get("taxa", [])}

        def resolve(t: dict) -> int:
            key, name = t.get("uksi_key"), t.get("scientific_name")
            found = by_key.get(key) or by_name.get((name or "").lower())
            if found:
                return found
            if not name:
                raise KeyError("no species name")
            full = details.get((key, name), t)
            category = categories.get((full.get("category") or "").lower(), fallback)
            new_id = repo.insert_custom_taxon(conn, {**t, **full}, category)
            repo.set_species_of_custom(conn, new_id)
            by_name[name.lower()] = new_id
            result.species.append(new_id)
            return new_id

        return resolve

    def _places(self, conn, data: dict, result: WildlifeImportResult) -> dict[str, int]:
        ids = repo.ids_by_uuid(conn, "place")
        for p in data.get("places", []):
            if p.get("uuid") in ids or not p.get("uuid"):
                continue
            try:
                ids[p["uuid"]] = repo.insert_place(conn, p)
                result.places.append(ids[p["uuid"]])
            except (sqlite3.IntegrityError, TypeError) as exc:
                result.skipped.append(f"Place “{p.get('name')}”: {_why(exc)}")
        return ids

    def _outings(self, conn, data, place_ids, result: WildlifeImportResult) -> dict[str, int]:
        ids = repo.ids_by_uuid(conn, "outing")
        for o in data.get("outings", []):
            if o.get("uuid") in ids or not o.get("uuid"):
                continue
            try:
                ids[o["uuid"]] = repo.insert_outing(conn, o, place_ids.get(o.get("place")))
                result.outings.append(ids[o["uuid"]])
            except (sqlite3.IntegrityError, TypeError) as exc:
                result.skipped.append(f"Outing on {o.get('outing_date')}: {_why(exc)}")
        return ids

    def _bring_photos(self, plan, links, result, progress) -> None:
        """Attach each new sighting's photos: ones already in the library are reused;
        others are copied in from the archive."""
        if not links:
            return
        details = {p["uuid"]: p for p in plan.data.get("photos", []) if p.get("uuid")}
        total, done = sum(len(u) for _, u in links), 0
        with self._db.connection() as conn:
            by_uuid = repo.ids_by_uuid(conn, "photo")
        archive = zipfile.ZipFile(plan.path) if plan.is_archive else None
        try:
            with tempfile.TemporaryDirectory(dir=self._paths.root, prefix="import-") as tmp:
                for sighting_id, uuids in links:
                    attach = []
                    for u in uuids:
                        progress(done, total)
                        done += 1
                        p = details.get(u)
                        if p is None:
                            continue
                        with self._db.connection() as conn:
                            pid = by_uuid.get(u) or repo.photo_by_sha(conn, p.get("sha256"))
                        if pid is None and archive is not None:
                            pid = self._photo_from_archive(archive, p, Path(tmp), result)
                        if pid is not None:
                            by_uuid[u] = pid
                            attach.append(pid)
                    if attach:
                        with self._db.transaction() as conn:
                            photos_repo.restore(conn, attach)
                            photos_repo.attach(conn, sighting_id, attach)
        finally:
            if archive is not None:
                archive.close()
        progress(total, total)
        if result.photos:
            self._events.publish("photos", tuple(result.photos))

    def _photo_from_archive(self, archive, p: dict, tmp: Path, result) -> int | None:
        member = p.get("file")
        try:
            info = archive.getinfo(member) if member else None
        except KeyError:
            info = None
        if info is None or info.file_size > MAX_PHOTO:
            result.skipped.append(f"Photo {p.get('original_name')}: not in the archive")
            return None
        # Our own file name (never a path from the archive), keeping the original's name
        name = _SAFE.sub("", Path(p.get("original_name") or "photo").name)[:100] or "photo"
        suffix = Path(member).suffix.lower()
        target = tmp / (name if name.lower().endswith(suffix) else name + suffix)
        target.write_bytes(archive.read(info))
        summary = self._photos.import_files([target])
        if not summary.photos:
            result.skipped.append(f"Photo {name}: couldn't be read")
            return None
        photo = summary.photos[0]
        raw_member = p.get("raw_file")
        if raw_member and raw_member in archive.namelist():
            raw_name = _SAFE.sub("", Path(p.get("raw_name") or "original").name)[:100]
            raw_suffix = Path(raw_member).suffix.lower()
            if not raw_name.lower().endswith(raw_suffix):
                raw_name = (raw_name or "original") + raw_suffix
            raw_target = tmp / raw_name
            raw_target.write_bytes(archive.read(raw_member))
            self._photos.add_raw(photo.id, raw_target)
        with self._db.transaction() as conn:
            repo.restore_photo_details(conn, photo.id, p)
        if summary.imported:
            result.photos.append(photo.id)
        return photo.id

    def _undo(self, result: WildlifeImportResult) -> None:
        with self._db.transaction() as conn:
            photo_ids = sightings_repo.photo_ids(conn, result.added)
            sightings_repo.hard_delete(conn, result.added)
            repo.delete_unused(conn, result.outings, result.places, result.species)
            orphans = [p.id for p in photos_repo.unlinked(conn, photo_ids)]
            photos_repo.soft_delete(conn, orphans)
            imports_repo.delete_batch(conn, result.batch_id)
        for topic in ("sightings", "places", "outings", "photos"):
            self._events.publish(topic, ())


def _why(exc: Exception) -> str:
    if isinstance(exc, sqlite3.IntegrityError) and "UNIQUE" in str(exc):
        return "it's already in WildLife"
    return "some of its details aren't valid"
