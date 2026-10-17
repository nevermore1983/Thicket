"""SQL for photos and their links to sightings."""

from __future__ import annotations

import sqlite3
import uuid as uuid_mod
from dataclasses import dataclass

from wildlife.data import sql_filters
from wildlife.data.repositories import NOW
from wildlife.domain.filters import SightingFilter
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
    camera: str | None = None
    taken_source: str | None = None
    raw_sha256: str | None = None
    raw_rel_path: str | None = None
    raw_name: str | None = None
    raw_size: int | None = None


@dataclass(frozen=True, slots=True)
class LibraryItem:
    """A photo in the Library grid, with the sighting it's shown under."""

    photo: Photo
    sighting_id: int
    name: str  # species display name
    observed_date: str


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
        raw_rel_path=r["raw_rel_path"],
        raw_name=r["raw_name"],
        raw_size=r["raw_size"],
        camera=r["camera"],
        taken_source=r["taken_source"],
    )


def insert(conn: sqlite3.Connection, p: NewPhoto) -> int:
    return conn.execute(
        "INSERT INTO photo (uuid, sha256, rel_path, original_name, file_size, width, height, "
        "taken_at, gps_latitude, gps_longitude, camera, taken_source, raw_sha256, raw_rel_path, "
        "raw_name, raw_size) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
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
            p.camera,
            p.taken_source,
            p.raw_sha256,
            p.raw_rel_path,
            p.raw_name,
            p.raw_size,
        ),
    ).lastrowid


def _links(conn: sqlite3.Connection, photo_id: int) -> tuple[int, ...]:
    """Sightings this photo belongs to, including ones in the recycle bin (their photos go
    to the bin with them, so they aren't in the Inbox)."""
    return tuple(
        r[0]
        for r in conn.execute(
            "SELECT sighting_id FROM sighting_photo WHERE photo_id = ? ORDER BY sighting_id",
            (photo_id,),
        )
    )


def get(conn: sqlite3.Connection, photo_id: int) -> Photo | None:
    row = conn.execute("SELECT * FROM photo WHERE id = ?", (photo_id,)).fetchone()
    return _photo(row, _links(conn, photo_id)) if row else None


def by_sha(conn: sqlite3.Connection, sha256: str) -> Photo | None:
    row = conn.execute("SELECT id FROM photo WHERE sha256 = ?", (sha256,)).fetchone()
    return get(conn, row[0]) if row else None


def by_raw_sha(conn: sqlite3.Connection, sha256: str) -> Photo | None:
    row = conn.execute("SELECT id FROM photo WHERE raw_sha256 = ?", (sha256,)).fetchone()
    return get(conn, row[0]) if row else None


def set_raw(
    conn: sqlite3.Connection, photo_id: int, sha256: str, rel_path: str, name: str, size: int
) -> None:
    """Give an already-imported photo its RAW original."""
    conn.execute(
        "UPDATE photo SET raw_sha256 = ?, raw_rel_path = ?, raw_name = ?, raw_size = ? WHERE id = ?",
        (sha256, rel_path, name, size, photo_id),
    )


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


def make_cover(conn: sqlite3.Connection, sighting_id: int, photo_id: int) -> None:
    """Move a photo to the front of its sighting's photos (the first is the cover)."""
    order = [
        r[0]
        for r in conn.execute(
            "SELECT photo_id FROM sighting_photo WHERE sighting_id = ? ORDER BY sort_order, photo_id",
            (sighting_id,),
        )
    ]
    if photo_id not in order:
        return
    order.remove(photo_id)
    conn.executemany(
        "UPDATE sighting_photo SET sort_order = ? WHERE sighting_id = ? AND photo_id = ?",
        [(i, sighting_id, pid) for i, pid in enumerate([photo_id, *order])],
    )


def reorder(conn: sqlite3.Connection, sighting_id: int, photo_ids: list[int]) -> None:
    """Put a sighting's photos in this order (the first is the cover)."""
    conn.executemany(
        "UPDATE sighting_photo SET sort_order = ? WHERE sighting_id = ? AND photo_id = ?",
        [(i, sighting_id, pid) for i, pid in enumerate(photo_ids)],
    )


# Not linked to any sighting at all (a deleted sighting keeps its photos in the bin with it)
_IN_INBOX = (
    "p.deleted_at IS NULL AND NOT EXISTS (SELECT 1 FROM sighting_photo sp WHERE sp.photo_id = p.id)"
)


def inbox(conn: sqlite3.Connection) -> list[Photo]:
    """Photos not attached to any sighting, oldest first."""
    rows = conn.execute(
        f"SELECT p.* FROM photo p WHERE {_IN_INBOX} "
        "ORDER BY p.taken_at IS NULL, p.taken_at, p.original_name, p.id"
    )
    return [_photo(r) for r in rows]


def inbox_count(conn: sqlite3.Connection) -> int:
    return conn.execute(f"SELECT COUNT(*) FROM photo p WHERE {_IN_INBOX}").fetchone()[0]


def library(conn: sqlite3.Connection, flt: SightingFilter) -> list[LibraryItem]:
    """Photos of live sightings that match the filter, newest sighting first (each photo once)."""
    where, params = sql_filters.where(flt, "v")
    rows = conn.execute(
        f"""SELECT p.*, v.id AS s_id, COALESCE(v.common_name, v.scientific_name) AS s_name,
                   v.observed_date AS s_date
            FROM sighting_v v
            JOIN sighting_photo sp ON sp.sighting_id = v.id
            JOIN photo p ON p.id = sp.photo_id AND p.deleted_at IS NULL
            WHERE {where}
            ORDER BY v.observed_date DESC, v.observed_time DESC, v.id DESC, sp.sort_order""",
        params,
    )
    seen: set[int] = set()
    items = []
    for r in rows:
        if r["id"] in seen:
            continue
        seen.add(r["id"])
        items.append(LibraryItem(_photo(r, (r["s_id"],)), r["s_id"], r["s_name"], r["s_date"]))
    return items


def set_rotation(conn: sqlite3.Connection, photo_id: int, rotation: int) -> None:
    conn.execute("UPDATE photo SET rotation = ? WHERE id = ?", (rotation % 360, photo_id))


def set_caption(conn: sqlite3.Connection, photo_id: int, caption: str | None) -> None:
    conn.execute("UPDATE photo SET caption = ? WHERE id = ?", (caption, photo_id))


def set_taken(conn: sqlite3.Connection, photo_id: int, taken_at: str | None, source: str) -> None:
    conn.execute(
        "UPDATE photo SET taken_at = ?, taken_source = ? WHERE id = ?", (taken_at, source, photo_id)
    )


def soft_delete(conn: sqlite3.Connection, ids: list[int]) -> None:
    conn.executemany(
        f"UPDATE photo SET deleted_at = {NOW} WHERE id = ? AND deleted_at IS NULL",
        [(i,) for i in ids],
    )


def mark_deleted(conn: sqlite3.Connection, ids: list[int], when_iso: str) -> None:
    """Put photos in the recycle bin as if deleted at `when_iso`."""
    conn.executemany("UPDATE photo SET deleted_at = ? WHERE id = ?", [(when_iso, i) for i in ids])


def in_recycle_bin(conn: sqlite3.Connection, photo_id: int) -> bool:
    row = conn.execute("SELECT deleted_at FROM photo WHERE id = ?", (photo_id,)).fetchone()
    return bool(row and row[0])


def restore(conn: sqlite3.Connection, ids: list[int]) -> None:
    conn.executemany("UPDATE photo SET deleted_at = NULL WHERE id = ?", [(i,) for i in ids])


def deleted_before(conn: sqlite3.Connection, cutoff_iso: str) -> list[Photo]:
    rows = conn.execute(
        "SELECT * FROM photo WHERE deleted_at IS NOT NULL AND deleted_at <= ?", (cutoff_iso,)
    )
    return [_photo(r) for r in rows]


def hard_delete(conn: sqlite3.Connection, ids: list[int]) -> None:
    conn.executemany("DELETE FROM photo WHERE id = ?", [(i,) for i in ids])


def recycle_bin(conn: sqlite3.Connection) -> list[Photo]:
    rows = conn.execute("SELECT * FROM photo WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC")
    return [_photo(r) for r in rows]


def unlinked(conn: sqlite3.Connection, ids: list[int]) -> list[Photo]:
    """Of these photos, the ones no sighting uses any more."""
    found = [get(conn, i) for i in ids]
    return [p for p in found if p is not None and not p.sighting_ids]


def library_files(conn: sqlite3.Connection) -> list[tuple[str, str, int]]:
    """(sha256, relative path, size) of every file of every photo not in the recycle bin,
    RAW originals included: what the library folder should contain."""
    return conn.execute(
        """SELECT sha256, rel_path, file_size FROM photo WHERE deleted_at IS NULL
           UNION ALL
           SELECT raw_sha256, raw_rel_path, raw_size FROM photo
           WHERE deleted_at IS NULL AND raw_rel_path IS NOT NULL AND raw_sha256 IS NOT NULL"""
    ).fetchall()


def live(conn: sqlite3.Connection) -> list[Photo]:
    """Every photo not in the recycle bin (for the missing-file check)."""
    return [_photo(r) for r in conn.execute("SELECT * FROM photo WHERE deleted_at IS NULL")]


def all_rel_paths(conn: sqlite3.Connection) -> list[str]:
    """Every library file, RAW originals included (what a backup must copy)."""
    return [
        r[0]
        for r in conn.execute(
            "SELECT rel_path FROM photo UNION ALL "
            "SELECT raw_rel_path FROM photo WHERE raw_rel_path IS NOT NULL"
        )
    ]
