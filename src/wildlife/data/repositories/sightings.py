"""SQL for sightings."""

from __future__ import annotations

import sqlite3
import uuid as uuid_mod
from datetime import date
from typing import Any

from wildlife.data import sql_filters
from wildlife.domain.codes import (
    CountQualifier,
    Evidence,
    Habitat,
    Identification,
    LifeStage,
    Sex,
)
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import Sighting, SightingDraft

NOW = "strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"

SORTS = {  # sort key -> ORDER BY (ascending); the list reverses for descending
    "date": "v.observed_date {d}, v.observed_time {d}, v.id {d}",
    "species": "COALESCE(v.common_name, v.scientific_name) COLLATE NOCASE {d}, v.observed_date DESC",
    "place": "v.place_name IS NULL, v.place_name COLLATE NOCASE {d}, v.observed_date DESC",
    "count": "v.count {d}, v.observed_date DESC",
    "category": "v.category_id {d}, v.observed_date DESC",
}

_SELECT = """
    SELECT v.*,
           (SELECT COUNT(*) FROM sighting_photo sp WHERE sp.sighting_id = v.id) AS photo_count,
           (SELECT p.rel_path FROM sighting_photo sp JOIN photo p ON p.id = sp.photo_id
             WHERE sp.sighting_id = v.id AND p.deleted_at IS NULL
             ORDER BY sp.sort_order, p.id LIMIT 1) AS cover_photo
    FROM sighting_v v
"""


def _opt(enum, value):
    return enum(value) if value is not None else None


def _sighting(r: sqlite3.Row) -> Sighting:
    return Sighting(
        id=r["id"],
        uuid=r["uuid"],
        taxon_id=r["taxon_id"],
        common_name=r["common_name"],
        scientific_name=r["scientific_name"],
        rank=r["rank"],
        species_id=r["species_id"],
        category_id=r["category_id"],
        observed_date=date.fromisoformat(r["observed_date"]),
        observed_time=r["observed_time"],
        place_id=r["place_id"],
        place_name=r["place_name"],
        latitude=r["latitude"],
        longitude=r["longitude"],
        uncertainty_m=r["uncertainty_m"],
        location_method=r["location_method"],
        location_text=r["location_text"],
        eff_latitude=r["eff_latitude"],
        eff_longitude=r["eff_longitude"],
        eff_uncertainty_m=r["eff_uncertainty_m"],
        count=r["count"],
        count_qualifier=CountQualifier(r["count_qualifier"]),
        evidence=Evidence(r["evidence"]),
        identification=Identification(r["identification"]),
        sex=_opt(Sex, r["sex"]),
        life_stage=_opt(LifeStage, r["life_stage"]),
        habitat=_opt(Habitat, r["habitat"]),
        is_not_wild=bool(r["is_not_wild"]),
        outing_id=r["outing_id"],
        notes=r["notes"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        photo_count=r["photo_count"],
        cover_photo=r["cover_photo"],
        source=r["source"],
        source_id=r["source_id"],
    )


def _code(value) -> str | None:
    """Enum or plain string -> stored code (str() of a StrEnum is its value)."""
    return None if value is None else str(value)


def _values(d: SightingDraft) -> dict[str, Any]:
    return {
        "taxon_id": d.taxon_id,
        "observed_date": d.observed_date.isoformat() if d.observed_date else None,
        "observed_time": d.observed_time,
        "place_id": d.place_id,
        "latitude": d.latitude,
        "longitude": d.longitude,
        "uncertainty_m": d.uncertainty_m,
        "location_method": _code(d.location_method),
        "location_text": d.location_text,
        "count": d.count,
        "count_qualifier": _code(d.count_qualifier),
        "evidence": _code(d.evidence),
        "identification": _code(d.identification),
        "sex": _code(d.sex),
        "life_stage": _code(d.life_stage),
        "habitat": _code(d.habitat),
        "is_not_wild": int(d.is_not_wild),
        "outing_id": d.outing_id,
        "notes": d.notes,
    }


def insert(conn: sqlite3.Connection, draft: SightingDraft) -> int:
    values = _values(draft)
    values["uuid"] = str(uuid_mod.uuid4())
    cols = ", ".join(values)
    marks = ", ".join(f":{k}" for k in values)
    return conn.execute(f"INSERT INTO sighting ({cols}) VALUES ({marks})", values).lastrowid


def update(conn: sqlite3.Connection, draft: SightingDraft) -> None:
    values = _values(draft)
    sets = ", ".join(f"{k} = :{k}" for k in values)
    values["id"] = draft.id
    conn.execute(f"UPDATE sighting SET {sets}, updated_at = {NOW} WHERE id = :id", values)


def get(conn: sqlite3.Connection, sighting_id: int) -> Sighting | None:
    row = conn.execute(f"{_SELECT} WHERE v.id = ?", (sighting_id,)).fetchone()
    return _sighting(row) if row else None


def page(
    conn: sqlite3.Connection,
    flt: SightingFilter,
    sort: str = "date",
    descending: bool = True,
    offset: int = 0,
    limit: int = 200,
) -> list[Sighting]:
    clause, params = sql_filters.where(flt)
    order = SORTS[sort].format(d="DESC" if descending else "ASC")
    params |= {"limit": limit, "offset": offset}
    sql = f"{_SELECT} WHERE {clause} ORDER BY {order} LIMIT :limit OFFSET :offset"
    return [_sighting(r) for r in conn.execute(sql, params)]


def totals(
    conn: sqlite3.Connection, flt: SightingFilter, include_probable: bool = False
) -> tuple[int, int]:
    """(number of sightings, number of countable species) matching the filter."""
    clause, params = sql_filters.where(flt)
    row = conn.execute(
        f"SELECT COUNT(*), COUNT(DISTINCT CASE WHEN {sql_filters.countable_sql('v', include_probable)} "
        f"THEN v.species_id END) FROM sighting_v v WHERE {clause}",
        params,
    ).fetchone()
    return row[0], row[1]


def soft_delete(conn: sqlite3.Connection, ids: list[int]) -> None:
    conn.executemany(
        f"UPDATE sighting SET deleted_at = {NOW} WHERE id = ? AND deleted_at IS NULL",
        [(i,) for i in ids],
    )


def restore(conn: sqlite3.Connection, ids: list[int]) -> None:
    conn.executemany("UPDATE sighting SET deleted_at = NULL WHERE id = ?", [(i,) for i in ids])


def hard_delete(conn: sqlite3.Connection, ids: list[int]) -> None:
    conn.executemany("DELETE FROM sighting WHERE id = ?", [(i,) for i in ids])


def deleted_before(conn: sqlite3.Connection, cutoff_iso: str) -> list[int]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT id FROM sighting WHERE deleted_at IS NOT NULL AND deleted_at <= ?",
            (cutoff_iso,),
        )
    ]


def recycle_bin(conn: sqlite3.Connection) -> list[tuple[int, str, str, str]]:
    """(id, display name, observed date, deleted at) of sightings in the recycle bin."""
    return [
        tuple(r)
        for r in conn.execute(
            "SELECT s.id, COALESCE(t.common_name, t.scientific_name), s.observed_date, s.deleted_at "
            "FROM sighting s JOIN taxon t ON t.id = s.taxon_id WHERE s.deleted_at IS NOT NULL "
            "ORDER BY s.deleted_at DESC"
        )
    ]


def photo_ids(conn: sqlite3.Connection, ids: list[int]) -> list[int]:
    """Photos attached to these sightings."""
    if not ids:
        return []
    marks = ",".join("?" * len(ids))
    return [
        r[0]
        for r in conn.execute(
            f"SELECT DISTINCT photo_id FROM sighting_photo WHERE sighting_id IN ({marks})", ids
        )
    ]


def taxon_of(conn: sqlite3.Connection, ids: list[int]) -> dict[int, int]:
    marks = ",".join("?" * len(ids))
    return dict(
        conn.execute(f"SELECT id, taxon_id FROM sighting WHERE id IN ({marks})", ids).fetchall()
    )


def set_taxon(conn: sqlite3.Connection, mapping: dict[int, int]) -> None:
    conn.executemany(
        f"UPDATE sighting SET taxon_id = ?, updated_at = {NOW} WHERE id = ?",
        [(taxon, sid) for sid, taxon in mapping.items()],
    )


def last_place_since(conn: sqlite3.Connection, since_utc_iso: str) -> int | None:
    """The place of the most recently *added* sighting created after `since`."""
    row = conn.execute(
        "SELECT place_id FROM sighting WHERE deleted_at IS NULL AND place_id IS NOT NULL "
        "AND created_at >= ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (since_utc_iso,),
    ).fetchone()
    return row[0] if row else None


def is_first_record(
    conn: sqlite3.Connection, sighting: Sighting, include_probable: bool = False
) -> bool:
    """True if this is the first countable sighting of its species ever (a 'lifer')."""
    if sighting.species_id is None:
        return False
    row = conn.execute(
        f"SELECT v.id FROM sighting_v v WHERE v.species_id = ? AND {sql_filters.countable_sql('v', include_probable)} "
        "ORDER BY v.observed_date, v.observed_time IS NULL, v.observed_time, v.id LIMIT 1",
        (sighting.species_id,),
    ).fetchone()
    return bool(row and row[0] == sighting.id)
