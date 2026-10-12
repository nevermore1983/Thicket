"""Importing observations exported from iNaturalist.

Importing happens in two steps so nothing changes until you've seen what will:

1. `preview(path)` reads the file and works out, for every row, what would happen:
   add it, update it (it changed on iNaturalist since the last import), leave it
   (already here), or skip it (no date, not identified, deleted here...). Names are
   matched to the UK species list; names that can't be matched are listed so you
   can choose the species yourself.
2. `run(plan, choices)` makes the changes in one transaction, as one "import batch"
   that can be undone in one go.

Photos are a separate, optional step (`fetch_photos`) because it needs the internet.
"""

from __future__ import annotations

import json
import logging
import re
import tempfile
import time
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date
from pathlib import Path

from wildlife.config.paths import DataPaths
from wildlife.data.db import Database
from wildlife.data.repositories import imports as repo
from wildlife.data.repositories import photos as photos_repo
from wildlife.data.repositories import places as places_repo
from wildlife.data.repositories import sightings as sightings_repo
from wildlife.domain.codes import LocationMethod
from wildlife.domain.errors import OnlineServiceError
from wildlife.domain.geo import distance_m
from wildlife.domain.inaturalist import SOURCE, InatRecord, read_file
from wildlife.domain.models import Place, SightingDraft
from wildlife.domain.validation import validate_sighting
from wildlife.services import online
from wildlife.services.events import EventHub
from wildlife.services.photos import PhotoService
from wildlife.services.settings import SettingsService
from wildlife.services.sightings import Undo

log = logging.getLogger(__name__)

ADD, UPDATE, SAME, SKIP = "add", "update", "same", "skip"
_RANK_ORDER = {"species": 0, "subspecies": 1, "species_group": 2, "genus": 3}
_SUBGENUS = re.compile(r" \([A-Z][a-z]+\)")
_PHOTO_ID = re.compile(r"/photos/(\d+)/")
_PHOTO_SIZE = re.compile(r"/(square|thumb|small|medium|large|original)\.")
API = "https://api.inaturalist.org/v1/observations?id={}&per_page={}"
API_BATCH = 100


@dataclass(frozen=True, slots=True)
class PlannedRow:
    record: InatRecord
    action: str  # ADD, UPDATE, SAME or SKIP
    taxon_id: int | None = None
    matched_by: str = ""  # 'name', 'synonym', 'english', 'remembered', 'chosen'
    reason: str = ""  # why it's left or skipped
    existing_id: int | None = None  # the sighting an update changes


@dataclass
class ImportPlan:
    file_name: str
    rows: list[PlannedRow]

    def count(self, action: str) -> int:
        return sum(1 for r in self.rows if r.action == action)

    @property
    def unmatched(self) -> dict[str, list[PlannedRow]]:
        """Names to choose a species for: name -> the rows using it (most used first)."""
        out: dict[str, list[PlannedRow]] = {}
        for row in self.rows:
            if row.action in (ADD, UPDATE) and row.taxon_id is None:
                out.setdefault(row.record.name, []).append(row)
        return dict(sorted(out.items(), key=lambda kv: (-len(kv[1]), kv[0].lower())))

    @property
    def skipped(self) -> list[PlannedRow]:
        return [r for r in self.rows if r.action == SKIP]


@dataclass
class ImportResult:
    batch_id: int
    added: list[int] = field(default_factory=list)
    updated: list[int] = field(default_factory=list)
    skipped: int = 0
    image_urls: dict[int, str] = field(default_factory=dict)  # sighting id -> first photo
    undo: Undo | None = None

    def describe(self) -> str:
        parts = [f"{len(self.added):,} added"]
        if self.updated:
            parts.append(f"{len(self.updated):,} updated")
        if self.skipped:
            parts.append(f"{self.skipped:,} skipped")
        return " · ".join(parts)


@dataclass
class PhotoFetchResult:
    fetched: int = 0
    already: int = 0
    failed: list[tuple[str, str]] = field(default_factory=list)  # (observation, reason)
    cancelled: bool = False

    def describe(self) -> str:
        parts = [f"{self.fetched:,} photo{'s' if self.fetched != 1 else ''} added"]
        if self.already:
            parts.append(f"{self.already:,} already here")
        if self.failed:
            parts.append(f"{len(self.failed):,} couldn't be fetched")
        return " · ".join(parts)


def name_variants(name: str) -> list[str]:
    """Spellings to try: as given, with '×' as 'x', without a subgenus, and with
    'subsp.'/'var.' for a three-part plant name (iNaturalist leaves them out)."""
    name = " ".join(name.replace("×", "x").split())
    out = [name, _SUBGENUS.sub("", name)]
    parts = out[-1].split()
    if len(parts) == 3 and parts[1] != "x":
        out += [
            f"{parts[0]} {parts[1]} subsp. {parts[2]}",
            f"{parts[0]} {parts[1]} var. {parts[2]}",
        ]
    return list(dict.fromkeys(out))


def _best(hits: list[repo.NameHit], kingdom: str | None) -> int | None:
    """The one taxon these hits mean, preferring the record's kingdom, then species
    over broader ranks, then the more commonly recorded."""
    if kingdom:
        hits = [h for h in hits if h.kingdom == kingdom] or hits
    if not hits:
        return None
    hits.sort(key=lambda h: (_RANK_ORDER.get(h.rank, 9), -h.priority, h.taxon_id))
    return hits[0].taxon_id


class InaturalistImporter:
    def __init__(
        self,
        paths: DataPaths,
        db: Database,
        events: EventHub,
        settings: SettingsService,
        photos: PhotoService,
        today: Callable[[], date] = date.today,
        fetch: online.Fetch = online.fetch,
        pause: Callable[[float], None] = time.sleep,
    ) -> None:
        self._paths, self._db, self._events = paths, db, events
        self._settings, self._photos, self._today = settings, photos, today
        self._fetch, self._pause = fetch, pause

    # ---- step 1: preview -------------------------------------------------------------
    def preview(
        self, path: Path, progress: Callable[[int, int], None] = lambda d, t: None
    ) -> ImportPlan:
        records = read_file(path)
        today = self._today()
        with self._db.connection() as conn:
            known = repo.existing(conn, SOURCE)
            remembered = repo.remembered(conn, SOURCE)
            cache: dict[tuple, tuple[int | None, str]] = {}
            rows = []
            for i, rec in enumerate(records):
                if i % 200 == 0:
                    progress(i, len(records))
                rows.append(self._plan_row(conn, rec, known, remembered, cache, today))
        progress(len(records), len(records))
        return ImportPlan(path.name, rows)

    def match(self, conn, rec: InatRecord, remembered: dict[str, int]) -> tuple[int | None, str]:
        for name in (rec.scientific_name, rec.common_name):
            if name and name.lower() in remembered:
                return remembered[name.lower()], "remembered"
        if rec.scientific_name:
            variants = name_variants(rec.scientific_name)
            hits = [h for v in variants for h in repo.taxa_named(conn, v)]
            for kind, how in (("scientific", "name"), ("synonym", "synonym")):
                found = _best([h for h in hits if h.kind == kind], rec.kingdom)
                if found:
                    return found, how
        if rec.common_name:
            hits = [h for h in repo.taxa_named(conn, rec.common_name) if h.kind == "common"]
            if rec.kingdom:
                hits = [h for h in hits if h.kingdom == rec.kingdom]
            species = {h.taxon_id for h in hits if h.rank == "species"}
            ids = species or {h.taxon_id for h in hits}
            if len(ids) == 1:  # only a name that means exactly one thing
                return ids.pop(), "english"
        return None, ""

    def _plan_row(self, conn, rec, known, remembered, cache, today) -> PlannedRow:
        if rec.problem:
            return PlannedRow(rec, SKIP, reason=rec.problem)
        before = known.get(rec.source_id)
        if before and before.deleted:
            return PlannedRow(rec, SKIP, reason="You deleted it in WildLife")
        if before and (rec.updated_at is None or rec.updated_at == before.source_updated_at):
            return PlannedRow(
                rec, SAME, reason="Already in WildLife", existing_id=before.sighting_id
            )
        if before and before.edited_here:
            return PlannedRow(
                rec,
                SKIP,
                reason="Changed in WildLife and on iNaturalist: your WildLife version is kept",
                existing_id=before.sighting_id,
            )
        if rec.observed_date > today:
            return PlannedRow(rec, SKIP, reason="The date is in the future")
        key = (rec.scientific_name, rec.common_name, rec.kingdom)
        if key not in cache:
            cache[key] = self.match(conn, rec, remembered)
        taxon_id, how = cache[key]
        action = UPDATE if before else ADD
        return PlannedRow(
            rec, action, taxon_id, how, existing_id=before.sighting_id if before else None
        )

    # ---- step 2: import --------------------------------------------------------------
    def run(
        self,
        plan: ImportPlan,
        choices: dict[str, int] | None = None,
        remember: bool = True,
    ) -> ImportResult:
        """Import the plan. `choices` gives a species for unmatched names (name -> taxon
        id); rows whose name still has no species are skipped."""
        choices = choices or {}
        with self._db.transaction() as conn:
            batch = repo.new_batch(conn, SOURCE, plan.file_name)
            result = ImportResult(batch)
            places = places_repo.all_places(conn)
            if remember:
                for name, taxon_id in choices.items():
                    repo.remember(conn, SOURCE, name, taxon_id)
            previous: dict[int, tuple[SightingDraft, tuple]] = {}
            for row in plan.rows:
                taxon_id = row.taxon_id or choices.get(row.record.name)
                if row.action not in (ADD, UPDATE) or taxon_id is None:
                    result.skipped += row.action != SAME
                    continue
                draft = self._draft(row.record, taxon_id, places)
                if validate_sighting(draft, self._today()):
                    result.skipped += 1
                    continue
                rec = row.record
                if row.action == ADD:
                    sid = repo.insert(conn, draft, SOURCE, rec.source_id, rec.updated_at, batch)
                    result.added.append(sid)
                else:
                    old = sightings_repo.get(conn, row.existing_id)
                    if old is None:
                        result.skipped += 1
                        continue
                    previous[old.id] = (old.to_draft(), repo.source_state(conn, old.id))
                    draft = replace(draft, id=old.id)
                    repo.update(conn, draft, SOURCE, rec.source_id, rec.updated_at, batch)
                    sid = old.id
                    result.updated.append(sid)
                if rec.image_url:
                    result.image_urls[sid] = rec.image_url
            repo.finish_batch(conn, batch, len(result.added), len(result.updated), result.skipped)
        log.info("iNaturalist import %s: %s", plan.file_name, result.describe())
        self._events.publish("sightings", tuple(result.added + result.updated))
        result.undo = Undo(
            f"Import of {len(result.added) + len(result.updated):,} sightings",
            lambda: self._undo(result, previous),
        )
        return result

    def _draft(self, rec: InatRecord, taxon_id: int, places: list[Place]) -> SightingDraft:
        place_id = None
        if rec.latitude is not None:
            place_id = _place_at(places, rec.latitude, rec.longitude)
        return SightingDraft(
            taxon_id=taxon_id,
            observed_date=rec.observed_date,
            observed_time=rec.observed_time,
            place_id=place_id,
            latitude=rec.latitude,
            longitude=rec.longitude,
            uncertainty_m=rec.uncertainty_m,
            location_method=LocationMethod.IMPORT if rec.latitude is not None else None,
            location_text=rec.location_text,
            count=None,  # iNaturalist records presence, not numbers
            evidence=rec.evidence,
            identification=rec.identification,
            is_not_wild=rec.is_not_wild,
            notes=rec.notes,
        )

    def _undo(self, result: ImportResult, previous: dict[int, tuple[SightingDraft, tuple]]) -> None:
        with self._db.transaction() as conn:
            photo_ids = sightings_repo.photo_ids(conn, result.added)
            sightings_repo.hard_delete(conn, result.added)
            for sid, (draft, state) in previous.items():
                sightings_repo.update(conn, draft)
                repo.set_source_state(conn, sid, state)
            # Photos fetched for the removed sightings go to the recycle bin
            orphans = [p.id for p in photos_repo.unlinked(conn, photo_ids)]
            photos_repo.soft_delete(conn, orphans)
            repo.delete_batch(conn, result.batch_id)
        self._events.publish("sightings", tuple(result.added + result.updated))
        if orphans:
            self._events.publish("photos", tuple(orphans))

    # ---- photos (optional, online) ---------------------------------------------------
    def fetch_photos(
        self,
        result: ImportResult,
        progress: Callable[[int, int], None] = lambda d, t: None,
        cancelled: Callable[[], bool] = lambda: False,
    ) -> PhotoFetchResult:
        """Download the photos of the sightings just imported that have none yet."""
        if not self._settings.current.allow_online:
            raise OnlineServiceError(
                "Photos need the internet. Turn on “Allow online features” in Settings first."
            )
        out = PhotoFetchResult()
        with self._db.connection() as conn:
            waiting = repo.sightings_without_photos(conn, SOURCE)
        mine = set(result.added) | set(result.updated)
        wanted = {src: sid for src, sid in waiting.items() if sid in mine}
        if not wanted:
            return out
        urls = self._photo_urls(list(wanted), result, wanted)
        total = sum(len(v) for v in urls.values())
        done = 0
        changed: list[int] = []  # sightings given photos, announced in batches

        def announce() -> None:
            if changed:
                self._events.publish("sightings", tuple(changed))
                changed.clear()

        with tempfile.TemporaryDirectory(dir=self._paths.root, prefix="inat-") as tmp:
            for source_id, photos in urls.items():
                attached: list[int] = []
                for photo_id, url in photos:
                    if cancelled():
                        out.cancelled = True
                        break
                    progress(done, total)
                    done += 1
                    try:
                        pid, new = self._one_photo(photo_id, url, Path(tmp))
                    except OnlineServiceError as exc:
                        out.failed.append((source_id, exc.user_message))
                        continue
                    attached.append(pid)
                    if new:
                        out.fetched += 1
                        self._pause(0.5)  # be gentle with iNaturalist's servers
                    else:
                        out.already += 1
                if attached:
                    with self._db.transaction() as conn:
                        photos_repo.attach(conn, wanted[source_id], attached)
                    changed.append(wanted[source_id])
                    if len(changed) >= 25:  # not once per photo: open pages would redraw constantly
                        announce()
                if out.cancelled:
                    break
        announce()
        progress(total, total)
        return out

    def _photo_urls(
        self, source_ids: list[str], result: ImportResult, wanted: dict[str, int]
    ) -> dict[str, list[tuple[str, str]]]:
        """Every photo of each observation (iNaturalist's API), or just the first one
        from the export file if the API can't be reached."""
        urls: dict[str, list[tuple[str, str]]] = {}
        for start in range(0, len(source_ids), API_BATCH):
            chunk = source_ids[start : start + API_BATCH]
            try:
                data = json.loads(self._fetch(API.format(",".join(chunk), len(chunk))))
                for obs in data.get("results", []):
                    photos = [
                        (str(p["id"]), p["url"])
                        for p in obs.get("photos", [])
                        if p.get("id") and p.get("url")
                    ]
                    if photos:
                        urls[str(obs["id"])] = photos
            except (OnlineServiceError, ValueError, KeyError, TypeError) as exc:
                log.warning("iNaturalist API unavailable, using the export's photo links: %s", exc)
            self._pause(1.0)
        for source_id in source_ids:
            first = result.image_urls.get(wanted[source_id])
            if source_id not in urls and first and (m := _PHOTO_ID.search(first)):
                urls[source_id] = [(m[1], first)]
        return urls

    def _one_photo(self, photo_id: str, url: str, tmp: Path) -> tuple[int, bool]:
        """(library photo id, newly downloaded?). A photo fetched before is reused."""
        with self._db.connection() as conn:
            known = repo.photo_by_source(conn, SOURCE, photo_id)
        if known is not None:
            with self._db.transaction() as conn:
                photos_repo.restore(conn, [known])
            return known, False
        data, error = None, None
        for size in ("original", "large", "medium"):
            try:
                data = self._fetch(_PHOTO_SIZE.sub(f"/{size}.", url, count=1))
                break
            except OnlineServiceError as exc:
                error = exc
        if data is None:
            raise error or OnlineServiceError("The photo couldn't be fetched.")
        suffix = Path(url.split("?")[0]).suffix.lower() or ".jpg"
        file = tmp / f"inaturalist-{photo_id}{suffix}"
        file.write_bytes(data)
        summary = self._photos.import_files([file])
        file.unlink(missing_ok=True)
        if not summary.photos:
            reason = summary.failed[0][1] if summary.failed else "Not a photo"
            raise OnlineServiceError(f"The photo couldn't be read ({reason}).")
        photo = summary.photos[0]
        with self._db.transaction() as conn:
            repo.set_photo_source(conn, photo.id, SOURCE, photo_id)
            photos_repo.restore(conn, [photo.id])
        return photo.id, bool(summary.imported)


def _place_at(places: list[Place], lat: float, lon: float) -> int | None:
    """The closest saved place whose circle contains the point."""
    best: tuple[float, int] | None = None
    for p in places:
        if p.is_archived:
            continue
        d = distance_m(lat, lon, p.latitude, p.longitude)
        if d <= p.radius_m and (best is None or d < best[0]):
            best = (d, p.id)
    return best[1] if best else None
