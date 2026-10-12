"""Filters saved under a name, and your notes on each species."""

from __future__ import annotations

import json
from dataclasses import dataclass

from wildlife.data.db import Database
from wildlife.domain.errors import ValidationError
from wildlife.domain.filters import SightingFilter, filter_from_dict, filter_to_dict
from wildlife.services.events import EventHub

TOPIC = "saved_filters"


@dataclass(frozen=True, slots=True)
class SavedFilter:
    id: int
    name: str
    filter: SightingFilter


class SavedFilters:
    def __init__(self, db: Database, events: EventHub) -> None:
        self._db, self._events = db, events

    def all(self) -> list[SavedFilter]:
        with self._db.connection() as conn:
            rows = conn.execute(
                "SELECT id, name, filter FROM saved_filter ORDER BY name"
            ).fetchall()
        return [SavedFilter(r[0], r[1], filter_from_dict(json.loads(r[2]))) for r in rows]

    def save(self, name: str, flt: SightingFilter) -> SavedFilter:
        """Save (or replace) a filter under `name`."""
        name = " ".join(name.split())
        if not name:
            raise ValidationError({"name": "Give the filter a name."})
        if len(name) > 80:
            raise ValidationError({"name": "Keep the name under 80 characters."})
        if flt.is_empty:
            raise ValidationError({"filter": "Choose some filters first."})
        data = json.dumps(filter_to_dict(flt))
        with self._db.transaction() as conn:
            conn.execute(
                "INSERT INTO saved_filter (name, filter) VALUES (?, ?) "
                "ON CONFLICT (name) DO UPDATE SET filter = excluded.filter",
                (name, data),
            )
            row = conn.execute(
                "SELECT id, name FROM saved_filter WHERE name = ?", (name,)
            ).fetchone()
        self._events.publish(TOPIC)
        return SavedFilter(row[0], row[1], flt)

    def delete(self, filter_id: int) -> None:
        with self._db.transaction() as conn:
            conn.execute("DELETE FROM saved_filter WHERE id = ?", (filter_id,))
        self._events.publish(TOPIC)


class SpeciesNotes:
    def __init__(self, db: Database, events: EventHub) -> None:
        self._db, self._events = db, events

    def get(self, taxon_id: int) -> str:
        with self._db.connection() as conn:
            row = conn.execute(
                "SELECT notes FROM species_note WHERE taxon_id = ?", (taxon_id,)
            ).fetchone()
        return row[0] if row else ""

    def set(self, taxon_id: int, notes: str) -> None:
        """Save notes on a species (empty notes are removed)."""
        notes = notes.strip()
        if len(notes) > 10_000:
            raise ValidationError({"notes": "Notes can be up to 10,000 characters."})
        with self._db.transaction() as conn:
            if notes:
                conn.execute(
                    "INSERT INTO species_note (taxon_id, notes) VALUES (?, ?) ON CONFLICT "
                    "(taxon_id) DO UPDATE SET notes = excluded.notes, "
                    "updated_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')",
                    (taxon_id, notes),
                )
            else:
                conn.execute("DELETE FROM species_note WHERE taxon_id = ?", (taxon_id,))
        self._events.publish("species_notes", (taxon_id,))
