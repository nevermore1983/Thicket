"""SQL for photos and their links to sightings."""

from __future__ import annotations

import sqlite3
import uuid as uuid_mod
from dataclasses import dataclass

from wildlife.domain.models import Photo


@dataclass(frozen=True, slots=True)
class NewPhoto:
    sha256: str
    rel_path: str
    original_name: str
    file_size: int
    width: int | None
    height: int | None
    taken_at: str | None
    gps_latitude: float | None
    gps_longitude: float | None


def _photo(r: sqlite3.Row, sighting_ids: tuple[int, ...] = ()) -> Photo:
    return Photo(
        id=r["id"],
        uuid=r["uuid"],
        sha256=r["sha256"],
        rel_path=r["rel_path"],
        original_name=r["original_name"],
        file_size=r["file_size"],
        width=r["width"],
        height=r["height"],
        taken_at=r["taken_at"],
        gps_latitude=r["gps_latitude"],
        gps_longitude=r["gps_longitude"],
        rotation=r["rotation"],
        caption=r["caption"],
        sighting_ids=sighting_ids,
    )


def insert(conn: sqlite3.Connection, p: NewPhoto) -> int:
    return conn.execute(
        "INSERT INTO photo (uuid, sha256, rel_path, original_name, file_size, width, height, taken_at, "
        "gps_latitude, gps_longitude) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (
            str(uuid_mod.uuid4()),
            p.sha256,
            p.rel_path,
            p.original_name,
            p.file_size,
            p.width,
            p.height,
            p.taken_at,
            p.gps_latitude,
            p.gps_longitude,
        ),
    ).lastrowid


def get(conn: sqlite3.Connection, photo_id: int) -> Photo | None:
    row = conn.execute("SELECT * FROM photo WHERE id = ?", (photo_id,)).fetchone()
    if not row:
        return None
    links = tuple(
        r[0]
        for r in conn.execute(
            "SELECT sighting_id FROM sighting_photo WHERE photo_id = ?", (photo_id,)
        )
    )
    return _photo(row, links)


def by_sha(conn: sqlite3.Connection, sha256: str) -> Photo | None:
    row = conn.execute("SELECT id FROM photo WHERE sha256 = ?", (sha256,)).fetchone()
    return get(conn, row[0]) if row else None


def for_sighting(conn: sqlite3.Connection, sighting_id: int) -> list[Photo]:
    rows = conn.execute(
        "SELECT p.* FROM photo p JOIN sighting_photo sp ON sp.photo_id = p.id "
        "WHERE sp.sighting_id = ? AND p.deleted_at IS NULL ORDER BY sp.sort_order, p.id",
        (sighting_id,),
    )
    return [_photo(r, (sighting_id,)) for r in rows]


def attach(conn: sqlite3.Connection, sighting_id: int, photo_ids: list[int]) -> None:
    start = conn.execute(
        "SELECT COALESCE(MAX(sort_order) + 1, 0) FROM sighting_photo WHERE sighting_id = ?",
        (sighting_id,),
    ).fetchone()[0]
    conn.executemany(
        "INSERT OR IGNORE INTO sighting_photo (sighting_id, photo_id, sort_order) VALUES (?, ?, ?)",
        [(sighting_id, pid, start + i) for i, pid in enumerate(photo_ids)],
    )


def detach(conn: sqlite3.Connection, sighting_id: int, photo_ids: list[int]) -> None:
    conn.executemany(
        "DELETE FROM sighting_photo WHERE sighting_id = ? AND photo_id = ?",
        [(sighting_id, pid) for pid in photo_ids],
    )


def inbox(conn: sqlite3.Connection) -> list[Photo]:
    rows = conn.execute(
        "SELECT p.* FROM photo p WHERE p.deleted_at IS NULL AND NOT EXISTS "
        "(SELECT 1 FROM sighting_photo sp WHERE sp.photo_id = p.id) ORDER BY p.taken_at, p.id"
    )
    return [_photo(r) for r in rows]


def inbox_count(conn: sqlite3.Connection) -> int:
    return conn.execute(
        "SELECT COUNT(*) FROM photo p WHERE p.deleted_at IS NULL AND NOT EXISTS "
        "(SELECT 1 FROM sighting_photo sp WHERE sp.photo_id = p.id)"
    ).fetchone()[0]


def all_rel_paths(conn: sqlite3.Connection) -> list[str]:
    return [r[0] for r in conn.execute("SELECT rel_path FROM photo")]
