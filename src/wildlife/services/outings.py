"""Outings: trips that group sightings and record the weather.

An outing can be planned after the fact ("Rainham, Sat morning") or started
live ("Start outing" now, "End outing" later). While one is in progress, new
sightings on that day are added to it by default.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

from wildlife.data.db import Database
from wildlife.data.repositories import outings as repo
from wildlife.data.repositories import places as places_repo
from wildlife.domain.errors import NotFoundError, ValidationError
from wildlife.domain.models import Outing, OutingDraft
from wildlife.domain.validation import validate_outing
from wildlife.services.events import EventHub
from wildlife.services.settings import SettingsService
from wildlife.services.sightings import TOPIC as SIGHTINGS
from wildlife.services.sightings import Undo

log = logging.getLogger(__name__)
TOPIC = "outings"


def _clock() -> str:
    return datetime.now().strftime("%H:%M")


class OutingService:
    def __init__(
        self,
        db: Database,
        events: EventHub,
        settings: SettingsService,
        today: Callable[[], date] = date.today,
        clock: Callable[[], str] = _clock,
    ) -> None:
        self._db, self._events, self._settings = db, events, settings
        self._today, self._clock = today, clock

    # ---- reading ------------------------------------------------------------
    def get(self, outing_id: int) -> Outing:
        with self._db.connection() as conn:
            found = repo.get(conn, outing_id)
        if found is None:
            raise NotFoundError("That outing no longer exists. It may have been deleted.")
        return found

    def on_date(self, day: date) -> list[Outing]:
        with self._db.connection() as conn:
            return repo.on_date(conn, day)

    def between(self, start: date, end: date) -> list[Outing]:
        with self._db.connection() as conn:
            return repo.between(conn, start, end)

    def page(self, offset: int = 0, limit: int = 200) -> list[Outing]:
        with self._db.connection() as conn:
            return repo.page(conn, offset, limit)

    def count(self) -> int:
        with self._db.connection() as conn:
            return repo.count(conn)

    def in_progress(self) -> Outing | None:
        """Today's outing that has started but not ended, if any."""
        with self._db.connection() as conn:
            return repo.in_progress(conn, self._today())

    def default_for(self, day: date | None, time: str | None) -> Outing | None:
        """The outing a new sighting on `day` at `time` probably belongs to.

        Only answers when there's no doubt: exactly one outing that day covers the time.
        """
        if day is None:
            return None
        matches = [o for o in self.on_date(day) if o.covers(time)]
        return matches[0] if len(matches) == 1 else None

    # ---- writing ------------------------------------------------------------
    def save(self, draft: OutingDraft) -> tuple[Outing, Undo]:
        errors = validate_outing(draft, self._today())
        with self._db.connection() as conn:
            if draft.place_id is not None and places_repo.get(conn, draft.place_id) is None:
                errors["place"] = "That place no longer exists. Please choose another."
        if errors:
            raise ValidationError(errors)
        with self._db.transaction() as conn:
            if draft.id is None:
                outing_id, before = repo.insert(conn, draft), None
            else:
                before = repo.get(conn, draft.id)
                if before is None:
                    raise NotFoundError("That outing no longer exists. It may have been deleted.")
                repo.update(conn, draft)
                outing_id = draft.id
            saved = repo.get(conn, outing_id)
        self._events.publish(TOPIC, (outing_id,))
        if before is None:
            undo = Undo(f"Add {saved.display_title}", lambda: self._remove_new(outing_id))
        else:
            previous = before.to_draft()
            undo = Undo(f"Edit {saved.display_title}", lambda: self._put_back(previous))
        return saved, undo

    def start(self, place_id: int | None = None, title: str | None = None) -> Outing:
        """Start an outing now (today, current time)."""
        saved, _ = self.save(
            OutingDraft(
                outing_date=self._today(), start_time=self._clock(), place_id=place_id, title=title
            )
        )
        return saved

    def end(self, outing_id: int) -> Outing:
        """End an outing now. One left running from an earlier day ends at 23:59."""
        outing = self.get(outing_id)
        end = self._clock() if outing.outing_date == self._today() else "23:59"
        if outing.start_time and end < outing.start_time:
            end = outing.start_time
        with self._db.transaction() as conn:
            repo.set_end_time(conn, outing_id, end)
        self._events.publish(TOPIC, (outing_id,))
        return self.get(outing_id)

    def add_sightings(self, sighting_ids: list[int], outing_id: int | None) -> None:
        """Put sightings into an outing (or take them out with None)."""
        with self._db.transaction() as conn:
            if outing_id is not None and repo.get(conn, outing_id) is None:
                raise NotFoundError("That outing no longer exists. It may have been deleted.")
            repo.link(conn, sighting_ids, outing_id)
        self._events.publish(SIGHTINGS, tuple(sighting_ids))
        self._events.publish(TOPIC, () if outing_id is None else (outing_id,))

    def delete(self, outing_id: int) -> Undo:
        """Hide the outing. Its sightings are kept, just no longer grouped; Undo regroups them."""
        with self._db.transaction() as conn:
            outing = repo.get(conn, outing_id)
            if outing is None:
                raise NotFoundError("That outing no longer exists. It may have been deleted.")
            linked = repo.sighting_ids(conn, outing_id)
            repo.link(conn, linked, None)
            repo.soft_delete(conn, outing_id)
        self._events.publish(TOPIC, (outing_id,))
        self._events.publish(SIGHTINGS, tuple(linked))

        def undo() -> None:
            with self._db.transaction() as c:
                repo.restore(c, outing_id)
                repo.link(c, linked, outing_id)
            self._events.publish(TOPIC, (outing_id,))
            self._events.publish(SIGHTINGS, tuple(linked))

        return Undo(f"Delete {outing.display_title}", undo)

    def purge_deleted(self, older_than_days: int | None = None) -> int:
        """Permanently remove outings deleted more than N days ago (same rule as sightings)."""
        days = (
            self._settings.current.recycle_bin_days if older_than_days is None else older_than_days
        )
        cutoff = (datetime.now(UTC) - timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with self._db.transaction() as conn:
            removed = repo.purge_deleted_before(conn, cutoff)
        if removed:
            log.info("Removed %d deleted outings", removed)
        return removed

    # ---- undo helpers -------------------------------------------------------
    def _remove_new(self, outing_id: int) -> None:
        with self._db.transaction() as conn:
            linked = repo.sighting_ids(conn, outing_id)
            repo.link(conn, linked, None)
            repo.hard_delete(conn, outing_id)
        self._events.publish(TOPIC, (outing_id,))
        if linked:
            self._events.publish(SIGHTINGS, tuple(linked))

    def _put_back(self, draft: OutingDraft) -> None:
        with self._db.transaction() as conn:
            repo.update(conn, draft)
        self._events.publish(TOPIC, (draft.id,))
