"""SQL for the Statistics page. Every function takes the same filter (with the period's dates
already in it), so all the numbers on the page always agree with each other."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from wildlife.data import sql_filters
from wildlife.domain.filters import SightingFilter


@dataclass(frozen=True, slots=True)
class Summary:
    sightings: int
    species: int  # by the list rules
    days: int  # days with a sighting
    outings: int
    places: int
    lifers: int  # species first ever seen in these sightings
    busiest_day: date | None
    busiest_count: int


@dataclass(frozen=True, slots=True)
class CategoryRow:
    category_id: int
    sightings: int
    species: int


@dataclass(frozen=True, slots=True)
class SpeciesRow:
    taxon_id: int  # the species (subspecies are counted with their species)
    name: str
    sightings: int
    individuals: int  # counts added up; a sighting without a count is 1


@dataclass(frozen=True, slots=True)
class PlaceRow:
    place_id: int
    name: str
    species: int
    visits: int  # different days with a sighting there
    sightings: int


@dataclass(frozen=True, slots=True)
class FirstRow:
    sighting_id: int
    name: str
    day: date
    place: str | None
    category_id: int
    kind: str  # 'lifer' or 'year' (first of its year, not a lifer)


def _where(flt: SightingFilter) -> tuple[str, dict]:
    return sql_filters.where(flt, "v")


def summary(conn: sqlite3.Connection, flt: SightingFilter, probable: bool) -> Summary:
    where, params = _where(flt)
    countable = sql_filters.countable_sql("v", probable)
    row = conn.execute(
        f"""SELECT COUNT(*),
                   COUNT(DISTINCT CASE WHEN {countable} THEN v.species_id END),
                   COUNT(DISTINCT v.observed_date),
                   COUNT(DISTINCT v.outing_id),
                   COUNT(DISTINCT v.place_id)
            FROM sighting_v v WHERE {where}""",
        params,
    ).fetchone()
    busiest = conn.execute(
        f"SELECT v.observed_date, COUNT(*) AS n FROM sighting_v v WHERE {where} "
        "GROUP BY v.observed_date ORDER BY n DESC, v.observed_date DESC LIMIT 1",
        params,
    ).fetchone()
    lifers = sum(1 for r in firsts(conn, flt, probable) if r.kind == "lifer")
    return Summary(
        row[0],
        row[1],
        row[2],
        row[3],
        row[4],
        lifers,
        date.fromisoformat(busiest[0]) if busiest else None,
        busiest[1] if busiest else 0,
    )


def species_first_dates(
    conn: sqlite3.Connection, flt: SightingFilter, probable: bool
) -> list[date]:
    """For each species in these sightings, the first date it was seen in them (sorted):
    the running total of these dates is the species-list growth curve."""
    where, params = _where(flt)
    rows = conn.execute(
        f"SELECT MIN(v.observed_date) FROM sighting_v v "
        f"WHERE {where} AND {sql_filters.countable_sql('v', probable)} "
        "GROUP BY v.species_id ORDER BY 1",
        params,
    )
    return [date.fromisoformat(r[0]) for r in rows]


def by_category(conn: sqlite3.Connection, flt: SightingFilter, probable: bool) -> list[CategoryRow]:
    where, params = _where(flt)
    countable = sql_filters.countable_sql("v", probable)
    rows = conn.execute(
        f"""SELECT v.category_id, COUNT(*),
                   COUNT(DISTINCT CASE WHEN {countable} THEN v.species_id END)
            FROM sighting_v v WHERE {where}
            GROUP BY v.category_id ORDER BY 2 DESC, v.category_id""",
        params,
    )
    return [CategoryRow(*r) for r in rows]


def seasons(conn: sqlite3.Connection, flt: SightingFilter) -> dict[tuple[int, int], int]:
    """(category id, month 1-12) -> sightings."""
    where, params = _where(flt)
    rows = conn.execute(
        f"""SELECT v.category_id, CAST(strftime('%m', v.observed_date) AS INTEGER), COUNT(*)
            FROM sighting_v v WHERE {where} GROUP BY 1, 2""",
        params,
    )
    return {(r[0], r[1]): r[2] for r in rows}


def hours(conn: sqlite3.Connection, flt: SightingFilter) -> list[int]:
    """Sightings with a recorded time, per hour 0-23."""
    where, params = _where(flt)
    counts = [0] * 24
    for hour, n in conn.execute(
        f"""SELECT CAST(substr(v.observed_time, 1, 2) AS INTEGER), COUNT(*)
            FROM sighting_v v WHERE v.observed_time IS NOT NULL AND {where} GROUP BY 1""",
        params,
    ):
        if 0 <= hour < 24:
            counts[hour] = n
    return counts


def species_totals(conn: sqlite3.Connection, flt: SightingFilter) -> list[SpeciesRow]:
    """Every species (subspecies merged into it; broader groups like 'Gull' on their own)."""
    where, params = _where(flt)
    rows = conn.execute(
        f"""SELECT COALESCE(v.species_id, v.taxon_id) AS k,
                   COALESCE(t.common_name, t.scientific_name),
                   COUNT(*), SUM(COALESCE(v.count, 1))
            FROM sighting_v v JOIN taxon t ON t.id = COALESCE(v.species_id, v.taxon_id)
            WHERE {where} GROUP BY k""",
        params,
    )
    return [SpeciesRow(*r) for r in rows]


def places(conn: sqlite3.Connection, flt: SightingFilter, probable: bool) -> list[PlaceRow]:
    where, params = _where(flt)
    countable = sql_filters.countable_sql("v", probable)
    rows = conn.execute(
        f"""SELECT v.place_id, v.place_name,
                   COUNT(DISTINCT CASE WHEN {countable} THEN v.species_id END),
                   COUNT(DISTINCT v.observed_date), COUNT(*)
            FROM sighting_v v WHERE v.place_id IS NOT NULL AND {where}
            GROUP BY v.place_id ORDER BY 3 DESC, 5 DESC, v.place_name""",
        params,
    )
    return [PlaceRow(*r) for r in rows]


def species_per_month(
    conn: sqlite3.Connection, flt: SightingFilter, year: int, probable: bool
) -> list[int]:
    """Different species seen in each month of `year` (12 numbers)."""
    where, params = _where(flt.with_(date_from=date(year, 1, 1), date_to=date(year, 12, 31)))
    counts = [0] * 12
    for month, n in conn.execute(
        f"""SELECT CAST(strftime('%m', v.observed_date) AS INTEGER),
                   COUNT(DISTINCT v.species_id)
            FROM sighting_v v WHERE {where} AND {sql_filters.countable_sql("v", probable)}
            GROUP BY 1""",
        params,
    ):
        counts[month - 1] = n
    return counts


def firsts(conn: sqlite3.Connection, flt: SightingFilter, probable: bool) -> list[FirstRow]:
    """Lifers and firsts of the year among these sightings, newest first.

    'First' is decided from all countable records (not just the filtered ones), so filtering
    to dragonflies never makes an old species look new. The earliest sighting wins
    (by date, then time, untimed last, then the order they were added)."""
    where, params = _where(flt)
    countable = sql_filters.countable_sql("c", probable)
    rows = conn.execute(
        f"""WITH ranked AS (
                SELECT c.id,
                       ROW_NUMBER() OVER (PARTITION BY c.species_id
                           ORDER BY c.observed_date, c.observed_time IS NULL, c.observed_time, c.id) AS life_rank,
                       ROW_NUMBER() OVER (PARTITION BY c.species_id, substr(c.observed_date, 1, 4)
                           ORDER BY c.observed_date, c.observed_time IS NULL, c.observed_time, c.id) AS year_rank
                FROM sighting_v c WHERE {countable}
            )
            SELECT v.id, COALESCE(t.common_name, t.scientific_name), v.observed_date, v.place_name,
                   v.category_id, r.life_rank
            FROM ranked r JOIN sighting_v v ON v.id = r.id
            JOIN taxon t ON t.id = v.species_id
            WHERE (r.life_rank = 1 OR r.year_rank = 1) AND {where}
            ORDER BY v.observed_date DESC, v.observed_time DESC, v.id DESC""",
        params,
    )
    return [
        FirstRow(r[0], r[1], date.fromisoformat(r[2]), r[3], r[4], "lifer" if r[5] == 1 else "year")
        for r in rows
    ]
