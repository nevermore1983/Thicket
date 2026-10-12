"""Recording and changing sightings: the app's most important actions."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta

from wildlife.data.db import Database
from wildlife.data.repositories import outings as outings_repo
from wildlife.data.repositories import photos as photos_repo
from wildlife.data.repositories import places as places_repo
from wildlife.data.repositories import sightings as repo
from wildlife.data.repositories import taxa as taxa_repo
from wildlife.domain.errors import NotFoundError, ValidationError
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import Sighting, SightingDraft
from wildlife.domain.validation import validate_sighting
from wildlife.services.events import EventHub
from wildlife.services.settings import SettingsService

log = logging.getLogger(__name__)
TOPIC = "sightings"


@dataclass(frozen=True, slots=True)
class Undo:
    """Something the UI can offer to reverse ("Robin saved · Undo")."""

    description: str
    run: Callable[[], None]


@dataclass(frozen=True, slots=True)
class SaveResult:
    sighting: Sighting
    created: bool
    is_lifer: bool
    undo: Undo


class SightingService:
    def __init__(
        self,
        db: Database,
        events: EventHub,
        settings: SettingsService,
        today: Callable[[], date] = date.today,
    ) -> None:
        self._db, self._events, self._settings, self._today = db, events, settings, today

    # ---- reading ------------------------------------------------------------
    def get(self, sighting_id: int) -> Sighting:
        with self._db.connection() as conn:
            found = repo.get(conn, sighting_id)
        if found is None:
            raise NotFoundError("That sighting no longer exists. It may have been deleted.")
        return found

    def page(
        self,
        flt: SightingFilter,
        sort: str = "date",
        descending: bool = True,
        offset: int = 0,
        limit: int = 200,
    ) -> list[Sighting]:
        with self._db.connection() as conn:
            return repo.page(conn, flt, sort, descending, offset, limit)

    def totals(self, flt: SightingFilter) -> tuple[int, int]:
        with self._db.connection() as conn:
            return repo.totals(conn, flt, self._settings.current.count_probable_ids)

    def is_lifer(self, sighting: Sighting) -> bool:
        with self._db.connection() as conn:
            return repo.is_first_record(conn, sighting, self._settings.current.count_probable_ids)

    def default_place(self) -> int | None:
        """The place to pre-select: the last one used within 'remember last place' hours."""
        hours = self._settings.current.remember_place_hours
        if hours <= 0:
            return None
        since = (datetime.now(UTC) - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._db.connection() as conn:
            return repo.last_place_since(conn, since)

    # ---- writing ------------------------------------------------------------
    def save(self, draft: SightingDraft) -> SaveResult:
        """Create or update. Raises ValidationError with field messages if invalid."""
        errors = validate_sighting(draft, self._today())
        with self._db.connection() as conn:
            if draft.taxon_id is not None and taxa_repo.get(conn, draft.taxon_id) is None:
                errors["species"] = (
                    "That species isn't in the catalogue any more. Please choose again."
                )
            if draft.place_id is not None and places_repo.get(conn, draft.place_id) is None:
                errors["place"] = "That place no longer exists. Please choose another."
            if draft.outing_id is not None and outings_repo.get(conn, draft.outing_id) is None:
                errors["outing"] = "That outing no longer exists. Please choose another."
        if errors:
            raise ValidationError(errors)
        with self._db.transaction() as conn:
            if draft.id is None:
                new_id = repo.insert(conn, draft)
                before = None
            else:
                before = repo.get(conn, draft.id)
                if before is None:
                    raise NotFoundError("That sighting no longer exists. It may have been deleted.")
                repo.update(conn, draft)
                new_id = draft.id
            saved = repo.get(conn, new_id)
            lifer = draft.id is None and repo.is_first_record(
                conn, saved, self._settings.current.count_probable_ids
            )
        self._events.publish(TOPIC, (new_id,))
        if before is None:
            undo = Undo(f"Add {saved.display_name}", lambda: self._remove_new(new_id))
        else:
            previous = before.to_draft()
            undo = Undo(f"Edit {saved.display_name}", lambda: self._restore_version(previous))
        return SaveResult(saved, before is None, lifer, undo)

    def delete(self, ids: list[int]) -> Undo:
        """Move sightings to the recycle bin."""
        with self._db.transaction() as conn:
            repo.soft_delete(conn, ids)
        self._events.publish(TOPIC, tuple(ids))
        noun = "sighting" if len(ids) == 1 else f"{len(ids)} sightings"
        return Undo(f"Delete {noun}", lambda: self.restore(ids))

    def restore(self, ids: list[int]) -> None:
        with self._db.transaction() as conn:
            repo.restore(conn, ids)
        self._events.publish(TOPIC, tuple(ids))

    def change_species(self, ids: list[int], taxon_id: int) -> Undo:
        with self._db.transaction() as conn:
            if taxa_repo.get(conn, taxon_id) is None:
                raise ValidationError({"species": "Choose a species from the list."})
            before = repo.taxon_of(conn, ids)
            repo.set_taxon(conn, dict.fromkeys(ids, taxon_id))
        self._events.publish(TOPIC, tuple(ids))

        def undo() -> None:
            with self._db.transaction() as c:
                repo.set_taxon(c, before)
            self._events.publish(TOPIC, tuple(ids))

        return Undo(f"Change species of {len(ids)} sightings", undo)

    def purge_recycle_bin(self, older_than_days: int | None = None) -> int:
        """Permanently remove sightings deleted more than N days ago (all if N == 0)."""
        days = (
            self._settings.current.recycle_bin_days if older_than_days is None else older_than_days
        )
        cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._db.transaction() as conn:
            ids = repo.deleted_before(conn, cutoff)
            photo_ids = repo.photo_ids(conn, ids)
            repo.hard_delete(conn, ids)
            # Their photos were in the bin with them. Any that no other sighting uses are
            # marked deleted as of the cutoff, so the photo purge that follows removes them.
            orphans = [p.id for p in photos_repo.unlinked(conn, photo_ids)]
            photos_repo.mark_deleted(conn, orphans, cutoff)
        if ids:
            log.info("Recycle bin: removed %d sightings and %d photos", len(ids), len(orphans))
            self._events.publish(TOPIC, tuple(ids))
        return len(ids)

    def recycle_bin(self) -> list[tuple[int, str, str, str]]:
        with self._db.connection() as conn:
            return repo.recycle_bin(conn)

    # ---- undo helpers -------------------------------------------------------
    def _remove_new(self, sighting_id: int) -> None:
        with self._db.transaction() as conn:
            repo.hard_delete(conn, [sighting_id])
        self._events.publish(TOPIC, (sighting_id,))

    def _restore_version(self, draft: SightingDraft) -> None:
        with self._db.transaction() as conn:
            repo.update(conn, draft)
        self._events.publish(TOPIC, (draft.id,))
