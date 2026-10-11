"""SQL for the calendar: light rows per sighting, tagged with 'first ever' and 'first this year'.

Firsts are worked out from *all* countable records, so filtering the calendar
(e.g. to dragonflies only) never turns an old species into a new 'lifer'.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from wildlife.data import sql_filters
from wildlife.domain.filters import SightingFilter


@dataclass(frozen=True, slots=True)
class CalendarRow:
    id: int
    day: date
    time: str | None
    category_id: int
    species_id: int | None
    name: str
    lifer_day: bool  # this is the species' first-ever countable date
    year_first_day: bool  # the species' first countable date in this year


def rows_between(
    conn: sqlite3.Connection,
    flt: SightingFilter,
    start: date,
    end: date,
    include_probable: bool = False,
) -> list[CalendarRow]:
    """Every sighting from start to end (inclusive) that passes the filter, oldest first."""
    if flt.date_from and flt.date_from > start:
        start = flt.date_from
    if flt.date_to and flt.date_to < end:
        end = flt.date_to
    if start > end:
        return []
    where, params = sql_filters.where(flt.with_(date_from=None, date_to=None), "v")
    countable = sql_filters.countable_sql("c", include_probable)
    countable_v = sql_filters.countable_sql("v", include_probable)
    params |= {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "year_start": date(start.year, 1, 1).isoformat(),
    }
    sql = f"""
        WITH firsts AS (
            SELECT c.species_id, MIN(c.observed_date) AS day
            FROM sighting_v c WHERE {countable} GROUP BY c.species_id
        ),
        year_firsts AS (
            SELECT c.species_id, MIN(c.observed_date) AS day
            FROM sighting_v c
            WHERE {countable} AND c.observed_date BETWEEN :year_start AND :end
            GROUP BY c.species_id, substr(c.observed_date, 1, 4)
        )
        SELECT v.id, v.observed_date, v.observed_time, v.category_id, v.species_id,
               COALESCE(v.common_name, v.scientific_name) AS name,
               ({countable_v}) AS ok,
               EXISTS (SELECT 1 FROM firsts f
                       WHERE f.species_id = v.species_id AND f.day = v.observed_date) AS lifer_day,
               EXISTS (SELECT 1 FROM year_firsts y
                       WHERE y.species_id = v.species_id AND y.day = v.observed_date) AS year_day
        FROM sighting_v v
        WHERE v.observed_date BETWEEN :start AND :end AND {where}
        ORDER BY v.observed_date, v.observed_time IS NULL, v.observed_time, v.id
    """
    return [
        CalendarRow(
            r[0],
            date.fromisoformat(r[1]),
            r[2],
            r[3],
            r[4],
            r[5],
            bool(r[6] and r[7]),
            bool(r[6] and r[8]),
        )
        for r in conn.execute(sql, params)
    ]
