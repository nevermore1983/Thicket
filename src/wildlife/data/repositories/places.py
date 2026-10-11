"""SQL for saved places."""

from __future__ import annotations

import sqlite3

from wildlife.domain.codes import Habitat
from wildlife.domain.models import Place, PlaceDraft

NOW = "strftime('%Y-%m-%dT%H:%M:%SZ', 'now')"


def _place(r: sqlite3.Row) -> Place:
    return Place(
        id=r["id"],
        name=r["name"],
        latitude=r["latitude"],
        longitude=r["longitude"],
        radius_m=r["radius_m"],
        habitat=Habitat(r["habitat"]) if r["habitat"] else None,
        notes=r["notes"],
        is_favourite=bool(r["is_favourite"]),
        is_archived=bool(r["is_archived"]),
    )


def all_places(conn: sqlite3.Connection, include_archived: bool = False) -> list[Place]:
    sql = "SELECT * FROM place" + ("" if include_archived else " WHERE is_archived = 0")
    return [
        _place(r) for r in conn.execute(sql + " ORDER BY is_favourite DESC, name COLLATE NOCASE")
    ]


def get(conn: sqlite3.Connection, place_id: int) -> Place | None:
    row = conn.execute("SELECT * FROM place WHERE id = ?", (place_id,)).fetchone()
    return _place(row) if row else None


def save(conn: sqlite3.Connection, d: PlaceDraft) -> int:
    values = (
        d.name.strip(),
        d.latitude,
        d.longitude,
        d.radius_m,
        str(d.habitat) if d.habitat else None,  # enum or plain string
        d.notes,
        int(d.is_favourite),
    )
    if d.id is None:
        return conn.execute(
            "INSERT INTO place (name, latitude, longitude, radius_m, habitat, notes, is_favourite) "
            "VALUES (?,?,?,?,?,?,?)",
            values,
        ).lastrowid
    conn.execute(
        f"UPDATE place SET name=?, latitude=?, longitude=?, radius_m=?, habitat=?, notes=?, "
        f"is_favourite=?, updated_at={NOW} WHERE id=?",
        (*values, d.id),
    )
    return d.id


def set_archived(conn: sqlite3.Connection, place_id: int, archived: bool) -> None:
    conn.execute(
        f"UPDATE place SET is_archived = ?, updated_at = {NOW} WHERE id = ?",
        (int(archived), place_id),
    )


def usage(conn: sqlite3.Connection) -> dict[int, tuple[int, int, str | None]]:
    """place id -> (sightings, distinct species, last visit date) over live sightings."""
    rows = conn.execute(
        "SELECT place_id, COUNT(*), COUNT(DISTINCT species_id), MAX(observed_date) "
        "FROM sighting_v WHERE place_id IS NOT NULL GROUP BY place_id"
    )
    return {r[0]: (r[1], r[2], r[3]) for r in rows}


def recent(conn: sqlite3.Connection, limit: int = 4) -> list[int]:
    """Places used most recently (by when sightings were added)."""
    return [
        r[0]
        for r in conn.execute(
            "SELECT place_id FROM sighting WHERE deleted_at IS NULL AND place_id IS NOT NULL "
            "GROUP BY place_id ORDER BY MAX(created_at) DESC LIMIT ?",
            (limit,),
        )
    ]


def in_use(conn: sqlite3.Connection, place_id: int) -> int:
    return conn.execute("SELECT COUNT(*) FROM sighting WHERE place_id = ?", (place_id,)).fetchone()[
        0
    ]


def delete(conn: sqlite3.Connection, place_id: int) -> None:
    conn.execute("DELETE FROM place WHERE id = ?", (place_id,))
