"""SQL for exporting: sightings with everything an export needs, and the records they use."""

from __future__ import annotations

import sqlite3

from wildlife.data import sql_filters
from wildlife.domain.filters import SightingFilter


def sightings(conn: sqlite3.Connection, flt: SightingFilter) -> list[sqlite3.Row]:
    """Matching live sightings, oldest first, with species, place and outing details."""
    where, params = sql_filters.where(flt)
    return conn.execute(
        f"""SELECT v.*, s.source_updated_at,
                   t.catalogue_key, t.authority, t.is_custom, t.tax_kingdom, t.tax_phylum,
                   t.tax_class, t.tax_order, t.tax_family,
                   c.name AS category_name,
                   p.uuid AS place_uuid,
                   o.uuid AS outing_uuid, o.title AS outing_title, o.outing_date
            FROM sighting_v v
            JOIN sighting s  ON s.id = v.id
            JOIN taxon t     ON t.id = v.taxon_id
            JOIN category c  ON c.id = v.category_id
            LEFT JOIN place p  ON p.id = v.place_id
            LEFT JOIN outing o ON o.id = v.outing_id AND o.deleted_at IS NULL
            WHERE {where}
            ORDER BY v.observed_date, v.observed_time, v.id""",
        params,
    ).fetchall()


def photos_of(conn: sqlite3.Connection, sighting_ids: list[int]) -> dict[int, list[sqlite3.Row]]:
    """Photos (not in the recycle bin) of these sightings, cover first."""
    out: dict[int, list[sqlite3.Row]] = {}
    for start in range(0, len(sighting_ids), 500):
        chunk = sighting_ids[start : start + 500]
        marks = ",".join("?" * len(chunk))
        rows = conn.execute(
            f"""SELECT sp.sighting_id, p.* FROM sighting_photo sp JOIN photo p ON p.id = sp.photo_id
                WHERE p.deleted_at IS NULL AND sp.sighting_id IN ({marks})
                ORDER BY sp.sighting_id, sp.sort_order, p.id""",
            chunk,
        )
        for r in rows:
            out.setdefault(r["sighting_id"], []).append(r)
    return out


def places(conn: sqlite3.Connection, ids: set[int] | None = None) -> list[sqlite3.Row]:
    """Saved places: all of them, or just these."""
    rows = conn.execute("SELECT * FROM place ORDER BY name COLLATE NOCASE").fetchall()
    return [r for r in rows if ids is None or r["id"] in ids]


def outings(conn: sqlite3.Connection, ids: set[int] | None = None) -> list[sqlite3.Row]:
    rows = conn.execute(
        "SELECT o.*, p.uuid AS place_uuid FROM outing o LEFT JOIN place p ON p.id = o.place_id "
        "WHERE o.deleted_at IS NULL ORDER BY o.outing_date, o.start_time"
    ).fetchall()
    return [r for r in rows if ids is None or r["id"] in ids]


def taxa(conn: sqlite3.Connection, ids: set[int], all_custom: bool) -> list[sqlite3.Row]:
    """These species, plus (optionally) every species you added yourself."""
    rows = conn.execute(
        "SELECT t.*, c.name AS category_name FROM taxon t JOIN category c ON c.id = t.category_id "
        "WHERE t.is_custom = 1 OR t.id IN (SELECT DISTINCT taxon_id FROM sighting "
        "WHERE deleted_at IS NULL)"
    ).fetchall()
    return [r for r in rows if r["id"] in ids or (all_custom and r["is_custom"])]


def species_notes(conn: sqlite3.Connection, taxon_ids: set[int] | None) -> list[sqlite3.Row]:
    rows = conn.execute(
        "SELECT n.taxon_id, n.notes, t.catalogue_key, t.scientific_name FROM species_note n "
        "JOIN taxon t ON t.id = n.taxon_id"
    ).fetchall()
    return [r for r in rows if taxon_ids is None or r["taxon_id"] in taxon_ids]


def add_species_note(conn: sqlite3.Connection, taxon_id: int, notes: str) -> bool:
    """Add notes to a species that has none yet (never overwrites yours). True if added."""
    cur = conn.execute(
        "INSERT OR IGNORE INTO species_note (taxon_id, notes) VALUES (?, ?)", (taxon_id, notes)
    )
    return cur.rowcount == 1


# --- importing WildLife's own export ----------------------------------------------------
def ids_by_uuid(conn: sqlite3.Connection, table: str) -> dict[str, int]:
    """uuid -> id for places, outings, sightings or photos (deleted ones included)."""
    if table not in ("place", "outing", "sighting", "photo"):
        raise ValueError(table)
    return dict(conn.execute(f"SELECT uuid, id FROM {table} WHERE uuid IS NOT NULL"))


def taxon_lookup(conn: sqlite3.Connection) -> tuple[dict[str, int], dict[str, int]]:
    """(species key -> id, scientific name (lower case) -> id) for matching species.
    Keys are every pack's: UKSI keys and GBIF ones ('gbif:2490384')."""
    by_key = dict(conn.execute("SELECT key, taxon_id FROM taxon_key"))
    by_name: dict[str, int] = {}
    rows = conn.execute(
        "SELECT lower(scientific_name), id FROM taxon ORDER BY is_custom, "
        "rank != 'species', priority DESC"
    )
    for name, taxon_id in rows:
        by_name.setdefault(name, taxon_id)
    return by_key, by_name


def category_ids(conn: sqlite3.Connection) -> dict[str, int]:
    return {name.lower(): i for i, name in conn.execute("SELECT id, name FROM category")}


def _insert(conn: sqlite3.Connection, table: str, values: dict) -> int:
    cols = ", ".join(values)
    marks = ", ".join("?" * len(values))
    return conn.execute(
        f"INSERT INTO {table} ({cols}) VALUES ({marks})", tuple(values.values())
    ).lastrowid


def insert_custom_taxon(conn: sqlite3.Connection, t: dict, category_id: int) -> int:
    return _insert(
        conn,
        "taxon",
        {
            "scientific_name": t["scientific_name"],
            "authority": t.get("authority"),
            "common_name": t.get("common_name"),
            "rank": t.get("rank") or "species",
            "tax_kingdom": t.get("tax_kingdom"),
            "tax_phylum": t.get("tax_phylum"),
            "tax_class": t.get("tax_class"),
            "tax_order": t.get("tax_order"),
            "tax_family": t.get("tax_family"),
            "category_id": category_id,
            "category_is_manual": 1,
            "is_custom": 1,
        },
    )


def set_species_of_custom(conn: sqlite3.Connection, taxon_id: int) -> None:
    """A species you added yourself counts as itself."""
    conn.execute("UPDATE taxon SET species_id = id WHERE id = ? AND rank = 'species'", (taxon_id,))


_PLACE = (
    "uuid",
    "name",
    "latitude",
    "longitude",
    "radius_m",
    "habitat",
    "notes",
    "is_favourite",
    "is_archived",
    "created_at",
)
_OUTING = (
    "uuid",
    "outing_date",
    "start_time",
    "end_time",
    "title",
    "weather",
    "temperature_c",
    "wind",
    "visibility",
    "is_complete_list",
    "notes",
    "created_at",
)
_SIGHTING = (
    "uuid",
    "observed_date",
    "observed_time",
    "latitude",
    "longitude",
    "uncertainty_m",
    "location_method",
    "location_text",
    "count",
    "count_qualifier",
    "evidence",
    "identification",
    "sex",
    "life_stage",
    "habitat",
    "is_not_wild",
    "notes",
    "source",
    "source_id",
    "source_updated_at",
    "created_at",
    "updated_at",
)


def _known(record: dict, columns: tuple[str, ...]) -> dict:
    return {c: record[c] for c in columns if record.get(c) is not None}


def insert_place(conn: sqlite3.Connection, p: dict) -> int:
    return _insert(conn, "place", _known(p, _PLACE))


def insert_outing(conn: sqlite3.Connection, o: dict, place_id: int | None) -> int:
    return _insert(conn, "outing", _known(o, _OUTING) | {"place_id": place_id})


def insert_sighting(
    conn: sqlite3.Connection,
    s: dict,
    taxon_id: int,
    place_id: int | None,
    outing_id: int | None,
    batch_id: int,
) -> int:
    values = _known(s, _SIGHTING) | {
        "taxon_id": taxon_id,
        "place_id": place_id,
        "outing_id": outing_id,
        "import_batch_id": batch_id,
    }
    return _insert(conn, "sighting", values)


def delete_unused(
    conn: sqlite3.Connection, outing_ids: list[int], place_ids: list[int], taxon_ids: list[int]
) -> None:
    """Remove records an import created, unless something else uses them by now."""
    conn.executemany(
        "DELETE FROM outing WHERE id = ? AND NOT EXISTS (SELECT 1 FROM sighting WHERE outing_id = outing.id)",
        [(i,) for i in outing_ids],
    )
    conn.executemany(
        "DELETE FROM place WHERE id = ? AND NOT EXISTS (SELECT 1 FROM sighting WHERE place_id = place.id) "
        "AND NOT EXISTS (SELECT 1 FROM outing WHERE place_id = place.id)",
        [(i,) for i in place_ids],
    )
    conn.executemany(
        "DELETE FROM taxon WHERE id = ? AND is_custom = 1 AND NOT EXISTS "
        "(SELECT 1 FROM sighting WHERE taxon_id = taxon.id)",
        [(i,) for i in taxon_ids],
    )


def restore_photo_details(conn: sqlite3.Connection, photo_id: int, p: dict) -> None:
    """Give a photo brought back from an export its id, turn, caption and origin."""
    conn.execute(
        "UPDATE photo SET rotation = ?, caption = ?, taken_at = COALESCE(?, taken_at) WHERE id = ?",
        (p.get("rotation") or 0, p.get("caption"), p.get("taken_at"), photo_id),
    )
    conn.execute(
        "UPDATE photo SET uuid = ? WHERE id = ? AND NOT EXISTS (SELECT 1 FROM photo WHERE uuid = ?)",
        (p["uuid"], photo_id, p["uuid"]),
    )
    if p.get("source_id"):
        conn.execute(
            "UPDATE photo SET source = ?, source_id = ? WHERE id = ? AND source_id IS NULL "
            "AND NOT EXISTS (SELECT 1 FROM photo WHERE source = ? AND source_id = ?)",
            (p.get("source"), p["source_id"], photo_id, p.get("source"), p["source_id"]),
        )


def photo_by_sha(conn: sqlite3.Connection, sha256: str | None) -> int | None:
    if not sha256:
        return None
    row = conn.execute(
        "SELECT id FROM photo WHERE sha256 = ? OR raw_sha256 = ?", (sha256, sha256)
    ).fetchone()
    return row[0] if row else None
