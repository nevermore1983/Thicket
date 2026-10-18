"""SQL for imports: matching names, import batches, and where records came from."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from wildlife.data.repositories import sightings as sightings_repo
from wildlife.domain.models import SightingDraft


@dataclass(frozen=True, slots=True)
class NameHit:
    taxon_id: int
    kind: str  # 'scientific', 'common' or 'synonym'
    rank: str
    kingdom: str | None
    priority: int


@dataclass(frozen=True, slots=True)
class Existing:
    """A sighting imported before from the same source."""

    sighting_id: int
    source_updated_at: str | None
    edited_here: bool  # changed in Thicket since it was last imported
    deleted: bool  # in the recycle bin


def taxa_named(conn: sqlite3.Connection, name: str) -> list[NameHit]:
    """Every taxon with this exact name (any case), scientific, English or synonym."""
    rows = conn.execute(
        "SELECT t.id, n.kind, t.rank, t.tax_kingdom, t.priority FROM taxon_name n "
        "JOIN taxon t ON t.id = n.taxon_id WHERE n.name = ?",
        (name,),
    )
    return [NameHit(*r) for r in rows]


def remembered(conn: sqlite3.Connection, source: str) -> dict[str, int]:
    """Names matched by hand before: lower-case name -> taxon id."""
    rows = conn.execute("SELECT name, taxon_id FROM name_match WHERE source = ?", (source,))
    return {name.lower(): taxon_id for name, taxon_id in rows}


def remember(conn: sqlite3.Connection, source: str, name: str, taxon_id: int) -> None:
    conn.execute(
        "INSERT INTO name_match (source, name, taxon_id) VALUES (?, ?, ?) "
        "ON CONFLICT (source, name) DO UPDATE SET taxon_id = excluded.taxon_id",
        (source, name, taxon_id),
    )


def existing(conn: sqlite3.Connection, source: str) -> dict[str, Existing]:
    rows = conn.execute(
        "SELECT source_id, id, source_updated_at, source_edited, deleted_at IS NOT NULL "
        "FROM sighting WHERE source = ?",
        (source,),
    )
    return {r[0]: Existing(r[1], r[2], bool(r[3]), bool(r[4])) for r in rows}


def new_batch(conn: sqlite3.Connection, source: str, file_name: str | None) -> int:
    return conn.execute(
        "INSERT INTO import_batch (source, file_name) VALUES (?, ?)", (source, file_name)
    ).lastrowid


def finish_batch(
    conn: sqlite3.Connection, batch_id: int, added: int, updated: int, skipped: int
) -> None:
    conn.execute(
        "UPDATE import_batch SET added = ?, updated = ?, skipped = ? WHERE id = ?",
        (added, updated, skipped, batch_id),
    )


def _mark(
    conn: sqlite3.Connection,
    sighting_id: int,
    source: str,
    source_id: str,
    source_updated_at: str | None,
    batch_id: int,
) -> None:
    # source_edited = 0: this version is exactly what the source said
    conn.execute(
        "UPDATE sighting SET source = ?, source_id = ?, source_updated_at = ?, "
        "import_batch_id = ?, source_edited = 0 WHERE id = ?",
        (source, source_id, source_updated_at, batch_id, sighting_id),
    )


def insert(
    conn: sqlite3.Connection,
    draft: SightingDraft,
    source: str,
    source_id: str,
    source_updated_at: str | None,
    batch_id: int,
) -> int:
    sighting_id = sightings_repo.insert(conn, draft)
    _mark(conn, sighting_id, source, source_id, source_updated_at, batch_id)
    return sighting_id


def update(
    conn: sqlite3.Connection,
    draft: SightingDraft,
    source: str,
    source_id: str,
    source_updated_at: str | None,
    batch_id: int,
) -> None:
    sightings_repo.update(conn, draft)
    _mark(conn, draft.id, source, source_id, source_updated_at, batch_id)


def source_state(conn: sqlite3.Connection, sighting_id: int) -> tuple:
    """(source_updated_at, import_batch_id, source_edited): put back by Undo."""
    return tuple(
        conn.execute(
            "SELECT source_updated_at, import_batch_id, source_edited FROM sighting WHERE id = ?",
            (sighting_id,),
        ).fetchone()
    )


def set_source_state(conn: sqlite3.Connection, sighting_id: int, state: tuple) -> None:
    conn.execute(
        "UPDATE sighting SET source_updated_at = ?, import_batch_id = ?, source_edited = ? "
        "WHERE id = ?",
        (*state, sighting_id),
    )


def delete_batch(conn: sqlite3.Connection, batch_id: int) -> None:
    conn.execute("DELETE FROM import_batch WHERE id = ?", (batch_id,))


# --- photos fetched from a website ---------------------------------------------
def photo_by_source(conn: sqlite3.Connection, source: str, source_id: str) -> int | None:
    row = conn.execute(
        "SELECT id FROM photo WHERE source = ? AND source_id = ?", (source, source_id)
    ).fetchone()
    return row[0] if row else None


def set_photo_source(conn: sqlite3.Connection, photo_id: int, source: str, source_id: str) -> None:
    conn.execute(
        "UPDATE photo SET source = ?, source_id = ? WHERE id = ? AND source_id IS NULL",
        (source, source_id, photo_id),
    )


def sightings_without_photos(conn: sqlite3.Connection, source: str) -> dict[str, int]:
    """Imported sightings (not deleted) with no photo yet: source id -> sighting id."""
    rows = conn.execute(
        """SELECT s.source_id, s.id FROM sighting s
           WHERE s.source = ? AND s.deleted_at IS NULL
             AND NOT EXISTS (SELECT 1 FROM sighting_photo sp JOIN photo p ON p.id = sp.photo_id
                             WHERE sp.sighting_id = s.id AND p.deleted_at IS NULL)""",
        (source,),
    )
    return dict(rows.fetchall())


def taxon_by_key(conn: sqlite3.Connection, key: str) -> int | None:
    """The species with this key from any pack (a UKSI key, or 'gbif:2490384')."""
    row = conn.execute("SELECT taxon_id FROM taxon_key WHERE key = ?", (key.strip(),)).fetchone()
    return row[0] if row else None


def live_drafts(conn: sqlite3.Connection) -> list[SightingDraft]:
    """Just enough of every live sighting to spot duplicates (see importer.duplicate_key)."""
    rows = conn.execute(
        "SELECT taxon_id, observed_date, observed_time, latitude, longitude, place_id, "
        "location_text FROM sighting WHERE deleted_at IS NULL"
    )
    return [
        SightingDraft(
            taxon_id=r[0],
            observed_date=date.fromisoformat(r[1]),
            observed_time=r[2],
            latitude=r[3],
            longitude=r[4],
            place_id=r[5],
            location_text=r[6],
        )
        for r in rows
    ]


@dataclass(frozen=True, slots=True)
class Batch:
    id: int
    source: str
    file_name: str | None
    imported_at: str  # UTC ISO
    added: int
    updated: int
    live: int  # its sightings not in the recycle bin


def batches(conn: sqlite3.Connection) -> list[Batch]:
    rows = conn.execute(
        """SELECT b.id, b.source, b.file_name, b.imported_at, b.added, b.updated,
                  (SELECT COUNT(*) FROM sighting s WHERE s.import_batch_id = b.id
                   AND s.deleted_at IS NULL)
           FROM import_batch b ORDER BY b.imported_at DESC, b.id DESC"""
    )
    return [Batch(*r) for r in rows]


def batch_sightings(conn: sqlite3.Connection, batch_id: int) -> list[int]:
    return [
        r[0]
        for r in conn.execute(
            "SELECT id FROM sighting WHERE import_batch_id = ? AND deleted_at IS NULL", (batch_id,)
        )
    ]
