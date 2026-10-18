"""SQL for species (taxa), their names and categories."""

from __future__ import annotations

import re
import sqlite3
from collections.abc import Callable, Iterable

from wildlife.domain.models import Category, Taxon, TaxonMatch

# "Deraeocoris (Deraeocoris) flavilinea": the subgenus in brackets, which most people leave out
SUBGENUS = re.compile(r" \([A-Z][a-z]+\)")
_TAXON_COLS = "t.id, t.scientific_name, t.common_name, t.rank, t.category_id, t.species_id, t.is_custom, t.catalogue_key"


def _taxon(row: sqlite3.Row) -> Taxon:
    return Taxon(
        id=row["id"],
        scientific_name=row["scientific_name"],
        common_name=row["common_name"],
        rank=row["rank"],
        category_id=row["category_id"],
        species_id=row["species_id"],
        is_custom=bool(row["is_custom"]),
        catalogue_key=row["catalogue_key"],
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


UK = "uk"


def install_catalogue(
    conn: sqlite3.Connection,
    records: Iterable[dict],
    progress: Callable[[str, float], None] = lambda step, fraction: None,
    version: str = "",
) -> int:
    """Install or update the built-in UK list (the UK Species Inventory)."""
    return install_pack(conn, records, UK, "United Kingdom", "uksi", version, progress)


def install_pack(
    conn: sqlite3.Connection,
    records: Iterable[dict],
    region: str,
    name: str,
    source: str,
    version: str,
    progress: Callable[[str, float], None] = lambda step, fraction: None,
) -> int:
    """Install or update a species pack: the UK list, or a region's pack from GBIF.

    Packs only ever add. For each species in the pack:
    - its key is known: it's that species (its details are updated only if this pack
      added it in the first place);
    - else the same scientific name, rank and kingdom is already in the list (Red Fox in
      the UK list and in a US pack): the pack links to it, never makes a copy;
    - else it's new, and added.
    The pack's common names and suggestion order are kept for its region (see
    apply_region). Custom species and your choices (hidden, a category you set) are
    kept. Runs inside the caller's transaction. Returns the number of species in it."""
    fallback = conn.execute("SELECT id FROM category WHERE is_fallback = 1").fetchone()[0]
    key_to_id: dict[str, int] = dict(conn.execute("SELECT key, taxon_id FROM taxon_key"))
    added_by = dict(conn.execute("SELECT id, catalogue_key FROM taxon"))
    same_name = _name_index(conn)
    records = list(records)
    total = len(records) or 1
    owned: set[str] = set()  # keys of species this pack added (its family tree is used)
    parent_of: dict[str, str | None] = {}
    rank_of: dict[str, str] = {}
    progress("Adding species", 0.0)
    for i, rec in enumerate(records):
        key = rec["k"]
        lineage = (rec.get("l") or [None] * 5) + [None] * 5
        values = (
            rec["s"],
            rec.get("a"),
            rec.get("c"),
            rec["r"],
            *lineage[:5],
            rec.get("g"),
            int(rec.get("nn", False)),
        )
        taxon_id = key_to_id.get(key)
        if taxon_id is None:
            taxon_id = same_name.get(_name_key(rec["s"], rec["r"], lineage[0]))
            if taxon_id is None:
                cur = conn.execute(
                    "INSERT INTO taxon (scientific_name, authority, common_name, rank, tax_kingdom, "
                    "tax_phylum, tax_class, tax_order, tax_family, informal_group, is_non_native, "
                    "catalogue_key, category_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (*values, key, fallback),
                )
                taxon_id = cur.lastrowid
                added_by[taxon_id] = key
                same_name[_name_key(rec["s"], rec["r"], lineage[0])] = taxon_id
            conn.execute("INSERT INTO taxon_key (key, taxon_id) VALUES (?, ?)", (key, taxon_id))
            key_to_id[key] = taxon_id
        elif added_by.get(taxon_id) == key:
            conn.execute(
                "UPDATE taxon SET scientific_name=?, authority=?, common_name=?, rank=?, tax_kingdom=?, "
                "tax_phylum=?, tax_class=?, tax_order=?, tax_family=?, informal_group=?, "
                "is_non_native=?, updated_at=strftime('%Y-%m-%dT%H:%M:%SZ','now') WHERE id=?",
                (*values, taxon_id),
            )
        if added_by.get(taxon_id) == key:
            owned.add(key)
        conn.execute(
            "INSERT INTO taxon_region (region, taxon_id, priority, common_name) VALUES (?, ?, ?, ?) "
            "ON CONFLICT (region, taxon_id) DO UPDATE SET priority = excluded.priority, "
            "common_name = excluded.common_name",
            (region, taxon_id, rec.get("pr", 0), rec.get("c")),
        )
        parent_of[key] = rec.get("p")
        rank_of[key] = rec["r"]
        if i % 5000 == 0:
            progress("Adding species", 0.5 * i / total)

    progress("Linking the family tree", 0.5)
    # Only for species this pack added: a linked species keeps the tree it came with
    conn.executemany(
        "UPDATE taxon SET parent_id = ? WHERE id = ?",
        [
            (key_to_id.get(p) if p else None, key_to_id[k])
            for k, p in parent_of.items()
            if k in owned
        ],
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
            if k in owned
        ],
    )
    progress("Sorting into categories", 0.6)
    resolve_categories(conn)

    progress("Indexing names for search", 0.65)
    conn.execute("DELETE FROM taxon_name WHERE pack = ?", (region,))  # this pack's old names
    names: list[tuple[int, str, str, str]] = []
    for rec in records:
        tid = key_to_id[rec["k"]]
        names.append((tid, rec["s"], "scientific", region))
        if rec.get("c"):
            names.append((tid, rec["c"], "common", region))
        names.extend((tid, n, "common", region) for n in rec.get("en", ()))
        names.extend((tid, n, "synonym", region) for n in rec.get("sy", ()))
        if (bare := SUBGENUS.sub("", rec["s"])) != rec["s"]:
            names.append((tid, bare, "synonym", region))
    batch = 20_000
    for start in range(0, len(names), batch):
        conn.executemany(
            "INSERT OR IGNORE INTO taxon_name (taxon_id, name, kind, pack) VALUES (?, ?, ?, ?)",
            names[start : start + batch],
        )
        progress("Indexing names for search", 0.65 + 0.3 * min(1.0, (start + batch) / len(names)))
    conn.execute(
        "INSERT INTO species_pack (region, name, source, version, taxa) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT (region) DO UPDATE SET name = excluded.name, source = excluded.source, "
        "version = excluded.version, taxa = excluded.taxa, "
        "installed_at = strftime('%Y-%m-%dT%H:%M:%SZ', 'now')",
        (region, name, source, version, len(records)),
    )
    progress("Showing your region's names", 0.95)
    apply_region(conn, current_region(conn))
    progress("Done", 1.0)
    return len(records)


def _name_key(scientific_name: str, rank: str, kingdom: str | None) -> tuple[str, str, str]:
    """What makes two packs' species the same: name (without a subgenus), rank, kingdom."""
    return (SUBGENUS.sub("", scientific_name).lower(), rank, (kingdom or "").lower())


def _name_index(conn: sqlite3.Connection) -> dict[tuple[str, str, str], int]:
    """Species already in the list, by _name_key. A catalogue species wins over one you
    added yourself, and the oldest wins over later ones."""
    index: dict[tuple[str, str, str], int] = {}
    for taxon_id, name, rank, kingdom in conn.execute(
        "SELECT id, scientific_name, rank, tax_kingdom FROM taxon ORDER BY is_custom DESC, id DESC"
    ):
        index[_name_key(name, rank, kingdom)] = taxon_id  # the last one written wins
    return index


# --- regions --------------------------------------------------------------------------
def current_region(conn: sqlite3.Connection) -> str:
    return get_meta(conn, "region") or UK


def apply_region(conn: sqlite3.Connection, region: str) -> None:
    """Show a region's common names and suggestion order: copy them into `taxon`, so
    every screen (lists, exports, search ranking) uses them without changing.

    A species with no name in that region keeps one from another region (the UK's
    first); species not recorded in the region drop down the suggestions (order 0).
    Species you added yourself keep their own name, unless a pack has the same species
    (it was linked to it, and the pack's name is shown)."""
    conn.execute(
        """UPDATE taxon SET
               common_name = COALESCE(
                   (SELECT r.common_name FROM taxon_region r
                    WHERE r.region = :region AND r.taxon_id = taxon.id),
                   (SELECT r.common_name FROM taxon_region r
                    WHERE r.taxon_id = taxon.id AND r.common_name IS NOT NULL
                    ORDER BY r.region != 'uk', r.region LIMIT 1),
                   common_name),
               priority = COALESCE(
                   (SELECT r.priority FROM taxon_region r
                    WHERE r.region = :region AND r.taxon_id = taxon.id), 0)
           WHERE EXISTS (SELECT 1 FROM taxon_region r WHERE r.taxon_id = taxon.id)""",
        {"region": region},
    )
    set_meta(conn, "region", region)


def packs(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    """The species packs installed, the UK first."""
    return conn.execute("SELECT * FROM species_pack ORDER BY region != 'uk', name").fetchall()


def get_meta(conn: sqlite3.Connection, key: str) -> str | None:
    row = conn.execute("SELECT value FROM app_meta WHERE key = ?", (key,)).fetchone()
    return row[0] if row else None


def set_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        "INSERT INTO app_meta (key, value) VALUES (?, ?) ON CONFLICT (key) DO UPDATE SET value = excluded.value",
        (key, value),
    )
