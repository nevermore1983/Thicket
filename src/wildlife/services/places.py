"""Saved places: create, edit, archive, and suggest the nearest one."""

from __future__ import annotations

from wildlife.data.db import Database
from wildlife.data.repositories import places as repo
from wildlife.domain.errors import ConflictError, NotFoundError, ValidationError
from wildlife.domain.geo import distance_m
from wildlife.domain.models import Place, PlaceDraft
from wildlife.domain.validation import validate_place
from wildlife.services.events import EventHub

TOPIC = "places"


class PlaceService:
    def __init__(self, db: Database, events: EventHub) -> None:
        self._db, self._events = db, events

    def all(self, include_archived: bool = False) -> list[Place]:
        with self._db.connection() as conn:
            return repo.all_places(conn, include_archived)

    def get(self, place_id: int) -> Place:
        with self._db.connection() as conn:
            place = repo.get(conn, place_id)
        if place is None:
            raise NotFoundError("That place no longer exists.")
        return place

    def save(self, draft: PlaceDraft) -> Place:
        errors = validate_place(draft)
        if errors:
            raise ValidationError(errors)
        with self._db.transaction() as conn:
            place_id = repo.save(conn, draft)
            place = repo.get(conn, place_id)
        self._events.publish(TOPIC, (place_id,))
        return place

    def archive(self, place_id: int, archived: bool = True) -> None:
        with self._db.transaction() as conn:
            repo.set_archived(conn, place_id, archived)
        self._events.publish(TOPIC, (place_id,))

    def delete(self, place_id: int) -> None:
        with self._db.transaction() as conn:
            sightings, binned, outings = repo.in_use(conn, place_id)
            if sightings or outings:
                raise ConflictError(
                    f"This place is used by {_users(sightings, binned, outings)}, so it can't be "
                    "deleted. Archive it instead to hide it from lists."
                )
            repo.delete(conn, place_id)
        self._events.publish(TOPIC, (place_id,))

    def usage(self) -> dict[int, tuple[int, int, str | None]]:
        with self._db.connection() as conn:
            return repo.usage(conn)

    def recent(self, limit: int = 4) -> list[Place]:
        with self._db.connection() as conn:
            ids = repo.recent(conn, limit)
            return [p for i in ids if (p := repo.get(conn, i)) and not p.is_archived]

    def nearest(self, latitude: float, longitude: float) -> Place | None:
        """The closest saved place whose radius contains the point, if any."""
        best: tuple[float, Place] | None = None
        for place in self.all():
            d = distance_m(latitude, longitude, place.latitude, place.longitude)
            if d <= place.radius_m and (best is None or d < best[0]):
                best = (d, place)
        return best[1] if best else None


def _users(sightings: int, binned: int, outings: int) -> str:
    """'3 sightings (1 in the recycle bin) and 1 outing'."""
    parts = []
    if sightings:
        text = f"{sightings} sighting{'s' if sightings != 1 else ''}"
        if binned == sightings:
            text += " in the recycle bin"
        elif binned:
            text += f" ({binned} in the recycle bin)"
        parts.append(text)
    if outings:
        parts.append(f"{outings} outing{'s' if outings != 1 else ''}")
    return " and ".join(parts)
