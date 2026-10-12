"""Read-only summary queries: dashboard numbers, life and year lists, species profiles.
(The Statistics page's queries are in statistics.py.)"""

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
    is_lifer: bool = False  # (year lists) first seen ever in that year


@dataclass(frozen=True, slots=True)
class SpeciesProfile:
    taxon_id: int
    sightings: int
    individuals: int
    first_seen: date | None
    last_seen: date | None
    best_count: int | None
    best_count_date: date | None
    by_month: list[int]  # sightings in each month of the year, all years
    by_year: dict[int, int]  # year -> sightings
    places: list[tuple[int, str, int]]  # (place id, name, sightings), most first
    photo_ids: list[int]  # newest first


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


def life_list(
    conn: sqlite3.Connection, include_probable: bool = False, year: int | None = None
) -> list[LifeListRow]:
    """The life list, or with `year` a year list (that year's sightings, first and last dates)."""
    countable = countable_sql("v", include_probable)
    params: dict = {}
    in_year = ""
    if year is not None:
        in_year = "AND v.observed_date BETWEEN :start AND :end"
        params = {"start": f"{year}-01-01", "end": f"{year}-12-31"}
    rows = conn.execute(
        f"""SELECT t.id, t.common_name, t.scientific_name, t.category_id,
                   COUNT(*), MIN(v.observed_date), MAX(v.observed_date),
                   (SELECT MIN(c.observed_date) FROM sighting_v c
                     WHERE c.species_id = t.id AND {countable_sql("c", include_probable)}) AS ever
            FROM sighting_v v JOIN taxon t ON t.id = v.species_id
            WHERE {countable} {in_year}
            GROUP BY t.id
            ORDER BY COALESCE(t.common_name, t.scientific_name) COLLATE NOCASE""",
        params,
    )
    return [
        LifeListRow(
            r[0],
            r[1],
            r[2],
            r[3],
            r[4],
            date.fromisoformat(r[5]),
            date.fromisoformat(r[6]),
            is_lifer=year is not None and r[7][:4] == str(year),
        )
        for r in rows
    ]


def years_recorded(conn: sqlite3.Connection) -> list[int]:
    """Years with at least one sighting, newest first."""
    return [
        int(r[0])
        for r in conn.execute(
            "SELECT DISTINCT substr(observed_date, 1, 4) FROM sighting_v ORDER BY 1 DESC"
        )
    ]


def species_profile(conn: sqlite3.Connection, taxon_id: int) -> SpeciesProfile:
    """Everything about one species (its subspecies included), from all your sightings."""
    match = "(v.taxon_id = :t OR v.species_id = :t)"
    row = conn.execute(
        f"""SELECT COUNT(*), SUM(COALESCE(v.count, 1)), MIN(v.observed_date), MAX(v.observed_date)
            FROM sighting_v v WHERE {match}""",
        {"t": taxon_id},
    ).fetchone()
    best = conn.execute(
        f"SELECT v.count, v.observed_date FROM sighting_v v WHERE {match} AND v.count IS NOT NULL "
        "ORDER BY v.count DESC, v.observed_date DESC LIMIT 1",
        {"t": taxon_id},
    ).fetchone()
    by_month = [0] * 12
    for month, n in conn.execute(
        f"SELECT CAST(strftime('%m', v.observed_date) AS INTEGER), COUNT(*) FROM sighting_v v "
        f"WHERE {match} GROUP BY 1",
        {"t": taxon_id},
    ):
        by_month[month - 1] = n
    by_year = {
        int(y): n
        for y, n in conn.execute(
            f"SELECT substr(v.observed_date, 1, 4), COUNT(*) FROM sighting_v v WHERE {match} GROUP BY 1",
            {"t": taxon_id},
        )
    }
    places = [
        tuple(r)
        for r in conn.execute(
            f"SELECT v.place_id, v.place_name, COUNT(*) FROM sighting_v v "
            f"WHERE {match} AND v.place_id IS NOT NULL GROUP BY v.place_id ORDER BY 3 DESC, 2 LIMIT 5",
            {"t": taxon_id},
        )
    ]
    photo_ids = [
        r[0]
        for r in conn.execute(
            f"""SELECT p.id FROM sighting_v v JOIN sighting_photo sp ON sp.sighting_id = v.id
                JOIN photo p ON p.id = sp.photo_id AND p.deleted_at IS NULL
                WHERE {match} ORDER BY v.observed_date DESC, sp.sort_order LIMIT 12""",
            {"t": taxon_id},
        )
    ]
    return SpeciesProfile(
        taxon_id,
        row[0],
        row[1] or 0,
        date.fromisoformat(row[2]) if row[2] else None,
        date.fromisoformat(row[3]) if row[3] else None,
        best[0] if best else None,
        date.fromisoformat(best[1]) if best else None,
        by_month,
        by_year,
        places,
        list(dict.fromkeys(photo_ids)),
    )
