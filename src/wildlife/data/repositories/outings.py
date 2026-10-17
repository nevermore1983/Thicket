"""SQL for outings (trips that group sightings and hold the weather)."""

from __future__ import annotations

import sqlite3
import uuid as uuid_mod
from datetime import date
from typing import Any

from wildlife.data.repositories import NOW
from wildlife.domain.codes import Visibility, Weather, Wind
from wildlife.domain.models import Outing, OutingDraft

# Live outings with their place name and how many live sightings / species they hold.
_SELECT = """
    SELECT o.*, p.name AS place_name,
           (SELECT COUNT(*) FROM sighting_v v WHERE v.outing_id = o.id) AS sightings,
           (SELECT COUNT(DISTINCT v.species_id) FROM sighting_v v WHERE v.outing_id = o.id) AS species
    FROM outing o LEFT JOIN place p ON p.id = o.place_id
    WHERE o.deleted_at IS NULL
"""
_ORDER = " ORDER BY o.outing_date DESC, o.start_time IS NULL, o.start_time DESC, o.id DESC"


def _opt(enum, value):
    return enum(value) if value is not None else None


def _outing(r: sqlite3.Row) -> Outing:
    return Outing(
        id=r["id"],
        uuid=r["uuid"],
        outing_date=date.fromisoformat(r["outing_date"]),
        start_time=r["start_time"],
        end_time=r["end_time"],
        place_id=r["place_id"],
        place_name=r["place_name"],
        title=r["title"],
        weather=_opt(Weather, r["weather"]),
        temperature_c=r["temperature_c"],
        wind=_opt(Wind, r["wind"]),
        visibility=_opt(Visibility, r["visibility"]),
        is_complete_list=bool(r["is_complete_list"]),
        notes=r["notes"],
        sightings=r["sightings"],
        species=r["species"],
    )


def _code(value) -> str | None:
    return None if value is None else str(value)


def _values(d: OutingDraft) -> dict[str, Any]:
    return {
        "outing_date": d.outing_date.isoformat() if d.outing_date else None,
        "start_time": d.start_time,
        "end_time": d.end_time,
        "place_id": d.place_id,
        "title": (d.title or "").strip() or None,
        "weather": _code(d.weather),
        "temperature_c": d.temperature_c,
        "wind": _code(d.wind),
        "visibility": _code(d.visibility),
        "is_complete_list": int(d.is_complete_list),
        "notes": d.notes,
    }


def insert(conn: sqlite3.Connection, draft: OutingDraft) -> int:
    values = _values(draft)
    values["uuid"] = str(uuid_mod.uuid4())
    cols = ", ".join(values)
    marks = ", ".join(f":{k}" for k in values)
    return conn.execute(f"INSERT INTO outing ({cols}) VALUES ({marks})", values).lastrowid


def update(conn: sqlite3.Connection, draft: OutingDraft) -> None:
    values = _values(draft)
    sets = ", ".join(f"{k} = :{k}" for k in values)
    values["id"] = draft.id
    conn.execute(f"UPDATE outing SET {sets}, updated_at = {NOW} WHERE id = :id", values)


def get(conn: sqlite3.Connection, outing_id: int) -> Outing | None:
    row = conn.execute(f"{_SELECT} AND o.id = ?", (outing_id,)).fetchone()
    return _outing(row) if row else None


def on_date(conn: sqlite3.Connection, day: date) -> list[Outing]:
    """Outings on one day, earliest first."""
    rows = conn.execute(
        f"{_SELECT} AND o.outing_date = ? ORDER BY o.start_time IS NULL, o.start_time, o.id",
        (day.isoformat(),),
    )
    return [_outing(r) for r in rows]


def between(conn: sqlite3.Connection, start: date, end: date) -> list[Outing]:
    rows = conn.execute(
        f"{_SELECT} AND o.outing_date BETWEEN ? AND ?{_ORDER}", (start.isoformat(), end.isoformat())
    )
    return [_outing(r) for r in rows]


def page(conn: sqlite3.Connection, offset: int = 0, limit: int = 200) -> list[Outing]:
    rows = conn.execute(f"{_SELECT}{_ORDER} LIMIT ? OFFSET ?", (limit, offset))
    return [_outing(r) for r in rows]


def count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM outing WHERE deleted_at IS NULL").fetchone()[0]


def in_progress(conn: sqlite3.Connection, day: date) -> Outing | None:
    """The latest outing on `day` that has started but not ended."""
    row = conn.execute(
        f"{_SELECT} AND o.outing_date = ? AND o.start_time IS NOT NULL AND o.end_time IS NULL "
        "ORDER BY o.start_time DESC, o.id DESC LIMIT 1",
        (day.isoformat(),),
    ).fetchone()
    return _outing(row) if row else None


def set_end_time(conn: sqlite3.Connection, outing_id: int, end_time: str | None) -> None:
    conn.execute(
        f"UPDATE outing SET end_time = ?, updated_at = {NOW} WHERE id = ?", (end_time, outing_id)
    )


def sighting_ids(conn: sqlite3.Connection, outing_id: int) -> list[int]:
    """All sightings linked to the outing, including ones in the recycle bin."""
    return [r[0] for r in conn.execute("SELECT id FROM sighting WHERE outing_id = ?", (outing_id,))]


def link(conn: sqlite3.Connection, sighting_ids: list[int], outing_id: int | None) -> None:
    conn.executemany(
        f"UPDATE sighting SET outing_id = ?, updated_at = {NOW} WHERE id = ?",
        [(outing_id, i) for i in sighting_ids],
    )


def soft_delete(conn: sqlite3.Connection, outing_id: int) -> None:
    conn.execute(
        f"UPDATE outing SET deleted_at = {NOW} WHERE id = ? AND deleted_at IS NULL", (outing_id,)
    )


def restore(conn: sqlite3.Connection, outing_id: int) -> None:
    conn.execute("UPDATE outing SET deleted_at = NULL WHERE id = ?", (outing_id,))


def hard_delete(conn: sqlite3.Connection, outing_id: int) -> None:
    conn.execute("DELETE FROM outing WHERE id = ?", (outing_id,))


def purge_deleted_before(conn: sqlite3.Connection, cutoff_iso: str) -> int:
    return conn.execute(
        "DELETE FROM outing WHERE deleted_at IS NOT NULL AND deleted_at <= ?", (cutoff_iso,)
    ).rowcount
