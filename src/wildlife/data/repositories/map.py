"""SQL for the map: sightings that have a location (their own, or their place's centre)."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass

from wildlife.data import sql_filters
from wildlife.domain.filters import SightingFilter


@dataclass(frozen=True, slots=True)
class MapPoint:
    id: int
    lat: float
    lon: float
    uncertainty_m: int | None
    category_id: int
    species_id: int | None
    name: str
    day: str  # ISO date
    count: int | None
    countable: bool


def points(
    conn: sqlite3.Connection, flt: SightingFilter, include_probable: bool = False
) -> list[MapPoint]:
    where, params = sql_filters.where(flt, "v")
    sql = f"""
        SELECT v.id, v.eff_latitude, v.eff_longitude, v.eff_uncertainty_m, v.category_id,
               v.species_id, COALESCE(v.common_name, v.scientific_name), v.observed_date, v.count,
               ({sql_filters.countable_sql("v", include_probable)})
        FROM sighting_v v
        WHERE v.eff_latitude IS NOT NULL AND {where}
        ORDER BY v.observed_date, v.id
    """
    return [MapPoint(*r[:9], bool(r[9])) for r in conn.execute(sql, params)]


def without_location(conn: sqlite3.Connection, flt: SightingFilter) -> int:
    where, params = sql_filters.where(flt, "v")
    return conn.execute(
        f"SELECT COUNT(*) FROM sighting_v v WHERE v.eff_latitude IS NULL AND {where}", params
    ).fetchone()[0]
