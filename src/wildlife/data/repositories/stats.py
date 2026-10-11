"""Read-only summary queries (dashboard, life list). Statistics proper arrive in Phase 10."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from wildlife.data.sql_filters import countable_sql


@dataclass(frozen=True, slots=True)
class DashboardNumbers:
    total_sightings: int
    life_species: int
    year_species: int
    last_year_species_to_date: int
    month_sightings: int
    month_days: int
    today_sightings: int
    without_location: int
    first_date: date | None


@dataclass(frozen=True, slots=True)
class LifeListRow:
    taxon_id: int
    common_name: str | None
    scientific_name: str
    category_id: int
    sightings: int
    first_seen: date
    last_seen: date


def dashboard(
    conn: sqlite3.Connection, today: date, include_probable: bool = False
) -> DashboardNumbers:
    countable = countable_sql("v", include_probable)
    year_start = date(today.year, 1, 1).isoformat()
    last_year_start = date(today.year - 1, 1, 1).isoformat()
    try:
        last_year_same_day = today.replace(year=today.year - 1).isoformat()
    except ValueError:  # 29 February
        last_year_same_day = date(today.year - 1, 2, 28).isoformat()
    month_start = today.replace(day=1).isoformat()
    row = conn.execute(
        f"""SELECT
            COUNT(*),
            COUNT(DISTINCT CASE WHEN {countable} THEN v.species_id END),
            COUNT(DISTINCT CASE WHEN {countable} AND v.observed_date >= :ys THEN v.species_id END),
            COUNT(DISTINCT CASE WHEN {countable} AND v.observed_date >= :lys AND v.observed_date <= :lysd
                  THEN v.species_id END),
            SUM(v.observed_date >= :ms),
            COUNT(DISTINCT CASE WHEN v.observed_date >= :ms THEN v.observed_date END),
            SUM(v.observed_date = :today),
            SUM(v.eff_latitude IS NULL),
            MIN(v.observed_date)
        FROM sighting_v v""",
        {
            "ys": year_start,
            "lys": last_year_start,
            "lysd": last_year_same_day,
            "ms": month_start,
            "today": today.isoformat(),
        },
    ).fetchone()
    return DashboardNumbers(
        row[0],
        row[1],
        row[2],
        row[3],
        row[4] or 0,
        row[5],
        row[6] or 0,
        row[7] or 0,
        date.fromisoformat(row[8]) if row[8] else None,
    )


def life_list(conn: sqlite3.Connection, include_probable: bool = False) -> list[LifeListRow]:
    rows = conn.execute(
        f"""SELECT t.id, t.common_name, t.scientific_name, t.category_id,
                   COUNT(*), MIN(v.observed_date), MAX(v.observed_date)
            FROM sighting_v v JOIN taxon t ON t.id = v.species_id
            WHERE {countable_sql("v", include_probable)}
            GROUP BY t.id
            ORDER BY COALESCE(t.common_name, t.scientific_name) COLLATE NOCASE"""
    )
    return [
        LifeListRow(
            r[0], r[1], r[2], r[3], r[4], date.fromisoformat(r[5]), date.fromisoformat(r[6])
        )
        for r in rows
    ]
