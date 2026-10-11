"""Day-by-day summaries for the calendar's year, month and week views."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import date

from wildlife.data.db import Database
from wildlife.data.repositories import calendar as repo
from wildlife.domain.filters import SightingFilter
from wildlife.services.settings import SettingsService

TOP_NAMES = 6


@dataclass(frozen=True, slots=True)
class DaySummary:
    day: date
    sightings: int
    species: int  # different kinds seen (species, or broader groups like 'Gull')
    category_ids: tuple[int, ...]  # most-seen category first
    names: tuple[str, ...]  # up to TOP_NAMES species to show: new ones first, then the most seen
    new_names: int  # how many of `names` (from the start) are lifers or year firsts
    lifers: int
    year_firsts: int  # includes lifers (a lifer is also new for the year)

    @property
    def headline(self) -> str:
        return self.names[0]


@dataclass(frozen=True, slots=True)
class Firsts:
    """Which sightings were 'firsts'. Only the earliest sighting of a species that day is marked."""

    lifers: frozenset[int]
    year_firsts: frozenset[int]

    def mark(self, sighting_id: int) -> str | None:
        if sighting_id in self.lifers:
            return "lifer"
        if sighting_id in self.year_firsts:
            return "year"
        return None


def summarise(rows: list[repo.CalendarRow]) -> dict[date, DaySummary]:
    by_day: dict[date, list[repo.CalendarRow]] = {}
    for row in rows:
        by_day.setdefault(row.day, []).append(row)
    out = {}
    for day, items in by_day.items():
        cats = Counter(r.category_id for r in items)
        kinds = Counter(r.species_id or r.name for r in items)  # subspecies count as their species
        names: dict = {}
        for r in items:
            names.setdefault(r.species_id or r.name, r.name)
        firsts = _firsts(items)
        lifers = [r for r in items if r.id in firsts.lifers]
        year = [r for r in items if r.id in firsts.year_firsts]
        # New species first (lifers, then year firsts, in time order), then the most seen;
        # sorted() is stable, so equal counts stay in the order they were seen.
        order = [r.species_id or r.name for r in lifers + year]
        new_kinds = list(dict.fromkeys(order))
        rest = [k for k in sorted(kinds, key=lambda k: -kinds[k]) if k not in new_kinds]
        out[day] = DaySummary(
            day=day,
            sightings=len(items),
            species=len(kinds),
            category_ids=tuple(c for c, _ in sorted(cats.items(), key=lambda kv: (-kv[1], kv[0]))),
            names=tuple(names[k] for k in (new_kinds + rest)[:TOP_NAMES]),
            new_names=len(new_kinds),
            lifers=len(lifers),
            year_firsts=len(year),
        )
    return out


def _firsts(rows: list[repo.CalendarRow]) -> Firsts:
    """Rows arrive in time order, so the first one seen per species is the 'first'."""
    lifers, year, seen_l, seen_y = set(), set(), set(), set()
    for r in rows:
        key = (r.day, r.species_id)
        if r.lifer_day and key not in seen_l:
            seen_l.add(key)
            lifers.add(r.id)
        if r.year_first_day and key not in seen_y:
            seen_y.add(key)
            year.add(r.id)
    return Firsts(frozenset(lifers), frozenset(year))


class CalendarService:
    def __init__(self, db: Database, settings: SettingsService) -> None:
        self._db, self._settings = db, settings

    def _rows(self, flt: SightingFilter, start: date, end: date) -> list[repo.CalendarRow]:
        with self._db.connection() as conn:
            return repo.rows_between(
                conn, flt, start, end, self._settings.current.count_probable_ids
            )

    def days(self, flt: SightingFilter, start: date, end: date) -> dict[date, DaySummary]:
        """Summaries for days that have sightings (days without any are simply missing)."""
        return summarise(self._rows(flt, start, end))

    def firsts(self, flt: SightingFilter, start: date, end: date) -> Firsts:
        """Which sightings in the range are lifers / first of the year (for the day lists)."""
        return _firsts(self._rows(flt, start, end))
