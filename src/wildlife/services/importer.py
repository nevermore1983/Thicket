"""The import pipeline every import format shares.

Importing happens in two steps so nothing changes until you've seen what will:

1. `preview_records(records, ...)` works out, for every record, what would happen:
   add it, update it (it changed in the other app since the last import), leave it
   (already here, or a duplicate of a sighting you have), or skip it (no date, not
   identified, deleted here...). Names are matched to the UK species list; names that
   can't be matched are listed so you can choose the species yourself.
2. `run(plan, choices)` makes the changes in one transaction, as one "import batch"
   that can be undone in one go.

Records with an id from their app (iNaturalist) are tracked by that id. Records
without one (a spreadsheet) are compared by content: the same species on the same
date and time at the same spot counts as a duplicate.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import date

from wildlife.config.paths import DataPaths
from wildlife.data.db import Database
from wildlife.data.repositories import imports as repo
from wildlife.data.repositories import photos as photos_repo
from wildlife.data.repositories import places as places_repo
from wildlife.data.repositories import sightings as sightings_repo
from wildlife.data.repositories import taxa as taxa_repo
from wildlife.domain.codes import LocationMethod
from wildlife.domain.geo import distance_m
from wildlife.domain.import_records import ImportRecord
from wildlife.domain.models import Place, SightingDraft
from wildlife.domain.validation import validate_sighting
from wildlife.services.events import EventHub
from wildlife.services.photos import PhotoService
from wildlife.services.settings import SettingsService
from wildlife.services.sightings import Undo

log = logging.getLogger(__name__)

ADD, UPDATE, SAME, SKIP = "add", "update", "same", "skip"
_RANK_ORDER = {"species": 0, "subspecies": 1, "species_group": 2, "genus": 3}
_SUBGENUS = re.compile(r" \([A-Z][a-z]+\)")
Progress = Callable[[int, int], None]


@dataclass(frozen=True, slots=True)
class PlannedRow:
    record: ImportRecord
    action: str  # ADD, UPDATE, SAME or SKIP
    taxon_id: int | None = None
    matched_by: str = ""  # 'key', 'name', 'synonym', 'english', 'remembered'
    reason: str = ""  # why it's left or skipped
    existing_id: int | None = None  # the sighting an update changes


@dataclass
class ImportPlan:
    file_name: str
    source: str  # 'inaturalist', 'csv', ...
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


def duplicate_key(d: SightingDraft) -> tuple:
    """What makes two sightings 'the same': species, date, time and spot (to ~100 m)."""
    if d.latitude is not None:
        spot = (round(d.latitude, 3), round(d.longitude, 3))
    elif d.place_id is not None:
        spot = ("place", d.place_id)
    else:
        spot = ("text", (d.location_text or "").strip().lower())
    return (d.taxon_id, d.observed_date, d.observed_time, spot)


class RecordImporter:
    def __init__(
        self,
        paths: DataPaths,
        db: Database,
        events: EventHub,
        settings: SettingsService,
        photos: PhotoService,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._paths, self._db, self._events = paths, db, events
        self._settings, self._photos, self._today = settings, photos, today

    def region(self) -> str:
        """Where you record ('uk', 'us-oh'...): how dates and times in files are read."""
        with self._db.connection() as conn:
            return taxa_repo.current_region(conn)

    # ---- step 1: preview -------------------------------------------------------------
    def preview_records(
        self,
        records: list[ImportRecord],
        file_name: str,
        source: str,
        progress: Progress = lambda d, t: None,
    ) -> ImportPlan:
        today = self._today()
        with self._db.connection() as conn:
            known = repo.existing(conn, source)
            remembered = repo.remembered(conn, source)
            places = places_repo.all_places(conn, include_archived=True)
            have = {duplicate_key(d) for d in repo.live_drafts(conn)}
            cache: dict[tuple, tuple[int | None, str]] = {}
            seen: set[str] = set()  # ids met earlier in this file
            rows = []
            for i, rec in enumerate(records):
                if i % 200 == 0:
                    progress(i, len(records))
                if rec.source_id and not rec.problem:  # (a row with a problem says that)
                    if rec.source_id in seen:
                        # The same record twice (two exports pasted together, say): one is
                        # enough, and two would break the rule that an id is imported once
                        rows.append(PlannedRow(rec, SAME, reason="Appears twice in this file"))
                        continue
                    seen.add(rec.source_id)
                row = self._plan_row(conn, rec, known, remembered, cache, today)
                if row.action == ADD and row.taxon_id and not rec.source_id:
                    key = duplicate_key(self._draft(rec, row.taxon_id, places))
                    if key in have:
                        row = replace(row, action=SAME, reason="Looks like a sighting you have")
                    have.add(key)  # the same row twice in one file is a duplicate too
                rows.append(row)
        progress(len(records), len(records))
        return ImportPlan(file_name, source, rows)

    def match(self, conn, rec: ImportRecord, remembered: dict[str, int]) -> tuple[int | None, str]:
        if rec.uksi_key and (found := repo.taxon_by_key(conn, rec.uksi_key)):
            return found, "key"
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
        before = known.get(rec.source_id) if rec.source_id else None
        if before and before.deleted:
            return PlannedRow(rec, SKIP, reason="You deleted it in Thicket")
        if before and (rec.updated_at is None or rec.updated_at == before.source_updated_at):
            return PlannedRow(
                rec, SAME, reason="Already in Thicket", existing_id=before.sighting_id
            )
        if before and before.edited_here:
            return PlannedRow(
                rec,
                SKIP,
                reason="Changed in Thicket and in the file: your Thicket version is kept",
                existing_id=before.sighting_id,
            )
        if rec.observed_date > today:
            return PlannedRow(rec, SKIP, reason="The date is in the future")
        key = (rec.uksi_key, rec.scientific_name, rec.common_name, rec.kingdom)
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
            batch = repo.new_batch(conn, plan.source, plan.file_name)
            result = ImportResult(batch)
            places = places_repo.all_places(conn, include_archived=True)
            have = {duplicate_key(d) for d in repo.live_drafts(conn)}
            if remember:
                for name, taxon_id in choices.items():
                    repo.remember(conn, plan.source, name, taxon_id)
            previous: dict[int, tuple[SightingDraft, tuple]] = {}
            for row in plan.rows:
                taxon_id = row.taxon_id or choices.get(row.record.name)
                if row.action not in (ADD, UPDATE) or taxon_id is None:
                    result.skipped += row.action != SAME
                    continue
                rec = row.record
                draft = self._draft(rec, taxon_id, places)
                if validate_sighting(draft, self._today()):
                    result.skipped += 1
                    continue
                if row.action == ADD:
                    if not rec.source_id:  # a species chosen just now may make it a duplicate
                        if duplicate_key(draft) in have:
                            result.skipped += 1
                            continue
                        have.add(duplicate_key(draft))
                    sid = repo.insert(
                        conn, draft, plan.source, rec.source_id, rec.updated_at, batch
                    )
                    result.added.append(sid)
                else:
                    old = sightings_repo.get(conn, row.existing_id)
                    if old is None:
                        result.skipped += 1
                        continue
                    previous[old.id] = (old.to_draft(), repo.source_state(conn, old.id))
                    draft = replace(draft, id=old.id)
                    repo.update(conn, draft, plan.source, rec.source_id, rec.updated_at, batch)
                    sid = old.id
                    result.updated.append(sid)
                if rec.image_url:
                    result.image_urls[sid] = rec.image_url
            repo.finish_batch(conn, batch, len(result.added), len(result.updated), result.skipped)
        log.info("Import (%s) %s: %s", plan.source, plan.file_name, result.describe())
        self._events.publish("sightings", tuple(result.added + result.updated))
        result.undo = Undo(
            f"Import of {len(result.added) + len(result.updated):,} sightings",
            lambda: self._undo(result, previous),
        )
        return result

    def _draft(self, rec: ImportRecord, taxon_id: int, places: list[Place]) -> SightingDraft:
        place_id = None
        if rec.place_name:
            wanted = rec.place_name.strip().lower()
            place_id = next((p.id for p in places if p.name.lower() == wanted), None)
        if place_id is None and rec.latitude is not None:
            place_id = _place_at(places, rec.latitude, rec.longitude)
        location_text = rec.location_text
        if rec.place_name and place_id is None and not location_text:
            location_text = rec.place_name[:200]  # an unknown place name is still useful
        return SightingDraft(
            taxon_id=taxon_id,
            observed_date=rec.observed_date,
            observed_time=rec.observed_time,
            place_id=place_id,
            latitude=rec.latitude,
            longitude=rec.longitude,
            uncertainty_m=rec.uncertainty_m,
            location_method=LocationMethod.IMPORT if rec.latitude is not None else None,
            location_text=location_text,
            count=rec.count,
            count_qualifier=rec.count_qualifier,
            evidence=rec.evidence,
            identification=rec.identification,
            sex=rec.sex,
            life_stage=rec.life_stage,
            habitat=rec.habitat,
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
