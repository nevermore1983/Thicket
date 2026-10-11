"""SQL for species (taxa), their names and categories."""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable

from wildlife.domain.models import Category, Taxon, TaxonMatch

_TAXON_COLS = "t.id, t.scientific_name, t.common_name, t.rank, t.category_id, t.species_id, t.is_custom, t.uksi_key"


def _taxon(row: sqlite3.Row) -> Taxon:
    return Taxon(
        id=row["id"],
        scientific_name=row["scientific_name"],
        common_name=row["common_name"],
        rank=row["rank"],
        category_id=row["category_id"],
        species_id=row["species_id"],
        is_custom=bool(row["is_custom"]),
        uksi_key=row["uksi_key"],
    )


def get(conn: sqlite3.Connection, taxon_id: int) -> Taxon | None:
    row = conn.execute(f"SELECT {_TAXON_COLS} FROM taxon t WHERE t.id = ?", (taxon_id,)).fetchone()
    return _taxon(row) if row else None


def categories(conn: sqlite3.Connection) -> list[Category]:
    rows = conn.execute("SELECT * FROM category ORDER BY sort_order, name").fetchall()
    return [
        Category(
            r["id"], r["name"], r["colour"], r["icon"], r["sort_order"], bool(r["is_fallback"])
        )
        for r in rows
    ]


def count(conn: sqlite3.Connection) -> int:
    return conn.execute("SELECT COUNT(*) FROM taxon").fetchone()[0]


# --- species picker ----------------------------------------------------------
def search(conn: sqlite3.Connection, text: str, limit: int = 20) -> list[TaxonMatch]:
    """Ranked suggestions: species you've recorded first, then best name match,
    then commonly recorded groups, then shorter names."""
    text = " ".join(text.split())
    if not text:
        return []
    if len(text) >= 3:
        source = "taxon_name_fts f JOIN taxon_name n ON n.id = f.rowid"
        where = "taxon_name_fts MATCH :fts"
    else:  # the trigram index needs 3+ letters; short queries match name/word starts
        source = "taxon_name n"
        where = "(n.name LIKE :q || '%' OR n.name LIKE '% ' || :q || '%' OR n.name LIKE '%-' || :q || '%')"
    sql = f"""
        WITH hits AS (
            -- match quality: 0 main name starts with it, 1 a word of the main name or another
            -- name starts with it, 2 the main name contains it, 3 anything else (synonyms...)
            SELECT n.taxon_id, n.name,
                   CASE WHEN n.name LIKE :q || '%' AND n.name IN (t.common_name, t.scientific_name) THEN 0
                        WHEN n.name LIKE :q || '%' AND n.kind = 'common' THEN 1
                        WHEN (n.name LIKE '% ' || :q || '%' OR n.name LIKE '%-' || :q || '%')
                             AND n.name IN (t.common_name, t.scientific_name) THEN 1
                        WHEN n.name IN (t.common_name, t.scientific_name) THEN 2
                        ELSE 3 END AS match_rank
            FROM {source}
            JOIN taxon t ON t.id = n.taxon_id
            WHERE {where}
        ),
        best AS (
            SELECT taxon_id, MIN(match_rank) AS match_rank, name
            FROM hits GROUP BY taxon_id
        ),
        usage AS (
            SELECT taxon_id, COUNT(*) AS n FROM sighting
            WHERE deleted_at IS NULL GROUP BY taxon_id
        )
        SELECT {_TAXON_COLS}, COALESCE(u.n, 0) AS uses, b.name AS matched, b.match_rank, t.priority
        FROM best b
        JOIN taxon t ON t.id = b.taxon_id
        LEFT JOIN usage u ON u.taxon_id = t.id
        WHERE t.is_hidden = 0
        -- Your species first; then good matches (0-2) by how commonly recorded they are,
        -- then weaker matches; ties go to the closer match and the shorter name.
        ORDER BY (u.n IS NULL), u.n DESC, (b.match_rank > 2), t.priority DESC, b.match_rank,
                 (t.common_name IS NULL), length(COALESCE(t.common_name, t.scientific_name))
        LIMIT :limit
    """
    params = {"q": text, "fts": '"' + text.replace('"', '""') + '"', "limit": limit}
    return [TaxonMatch(_taxon(r), r["uses"], r["matched"]) for r in conn.execute(sql, params)]


# --- catalogue install / update ----------------------------------------------
_RESOLVE_CATEGORIES = """
    UPDATE taxon SET category_id = COALESCE(
        (SELECT category_id FROM category_rule WHERE taxon_name = taxon.tax_family),
        (SELECT category_id FROM category_rule WHERE taxon_name = taxon.tax_order),
        (SELECT category_id FROM category_rule WHERE taxon_name = taxon.tax_class),
        (SELECT category_id FROM category_rule WHERE taxon_name = taxon.tax_phylum),
        (SELECT category_id FROM category_rule WHERE taxon_name = taxon.tax_kingdom),
        (SELECT id FROM category WHERE is_fallback = 1))
    WHERE category_is_manual = 0
"""


def resolve_categories(conn: sqlite3.Connection) -> None:
    conn.execute(_RESOLVE_CATEGORIES)


def install_catalogue(
    conn: sqlite3.Connection,
    records: Iterable[dict],
    progress: Callable[[str, float], None] = lambda step, fraction: None,
) -> int:
    """Insert or update catalogue taxa (keyed by UKSI key). Custom species and the
    user's choices (hidden, manual category) are kept. Returns taxa written.
    Runs inside the caller's transaction."""
    fallback = conn.execute("SELECT id FROM category WHERE is_fallback = 1").fetchone()[0]
    existing = dict(conn.execute("SELECT uksi_key, id FROM taxon WHERE uksi_key IS NOT NULL"))
    records = list(records)
    total = len(records) or 1
    key_to_id: dict[str, int] = dict(existing)
    parent_of: dict[str, str | None] = {}
    rank_of: dict[str, str] = {}
    progress("Adding species", 0.0)
    for i, rec in enumerate(records):
        lineage = (rec.get("l") or [None] * 5) + [None] * 5
        values = (
            rec["s"],
            rec.get("a"),
            rec.get("c"),
            rec["r"],
            *lineage[:5],
            rec.get("g"),
            int(rec.get("nn", False)),
            rec.get("pr", 0),
        )
        if rec["k"] in existing:
            conn.execute(
                "UPDATE taxon SET scientific_name=?, authority=?, common_name=?, rank=?, tax_kingdom=?, "
                "tax_phylum=?, tax_class=?, tax_order=?, tax_family=?, informal_group=?, is_non_native=?, "
                "priority=?, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?",
                (*values, existing[rec["k"]]),
            )
        else:
            cur = conn.execute(
                "INSERT INTO taxon (scientific_name, authority, common_name, rank, tax_kingdom, tax_phylum, "
                "tax_class, tax_order, tax_family, informal_group, is_non_native, priority, uksi_key, "
                "category_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (*values, rec["k"], fallback),
            )
            key_to_id[rec["k"]] = cur.lastrowid
        parent_of[rec["k"]] = rec.get("p")
        rank_of[rec["k"]] = rec["r"]
        if i % 5000 == 0:
            progress("Adding species", 0.5 * i / total)

    progress("Linking the family tree", 0.5)
    conn.executemany(
        "UPDATE taxon SET parent_id = ? WHERE id = ?",
        [(key_to_id.get(p) if p else None, key_to_id[k]) for k, p in parent_of.items()],
    )

    def species_key(key: str) -> str | None:
        """The species a taxon counts as: itself, or the species above a subspecies."""
        rank = rank_of.get(key)
        if rank == "species":
            return key
        if rank == "subspecies":
            parent, steps = parent_of.get(key), 0
            while parent and steps < 5:
                if rank_of.get(parent) == "species":
                    return parent
                parent, steps = parent_of.get(parent), steps + 1
        return None

    conn.executemany(
        "UPDATE taxon SET species_id = ? WHERE id = ?",
        [
            (key_to_id.get(species_key(k)) if species_key(k) else None, key_to_id[k])
            for k in parent_of
        ],
    )
    progress("Sorting into categories", 0.6)
    resolve_categories(conn)

    progress("Indexing names for search", 0.65)
    ids = [key_to_id[r["k"]] for r in records]
    conn.executemany(
        "DELETE FROM taxon_name WHERE taxon_id = ?", [(i,) for i in ids if i in existing.values()]
    )
    names: list[tuple[int, str, str]] = []
    for rec in records:
        tid = key_to_id[rec["k"]]
        names.append((tid, rec["s"], "scientific"))
        if rec.get("c"):
            names.append((tid, rec["c"], "common"))
        names.extend((tid, n, "common") for n in rec.get("en", ()))
        names.extend((tid, n, "synonym") for n in rec.get("sy", ()))
    batch = 20_000
    for start in range(0, len(names), batch):
        conn.executemany(
            "INSERT OR IGNORE INTO taxon_name (taxon_id, name, kind) VALUES (?, ?, ?)",
            names[start : start + batch],
        )
        progress("Indexing names for search", 0.65 + 0.35 * min(1.0, (start + batch) / len(names)))
    progress("Done", 1.0)
    return len(records)


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
