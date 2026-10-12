"""Turns a SightingFilter into a parameterised SQL WHERE clause on `sighting_v v`.

Every screen (list, calendar, map, statistics, export) uses this one function,
which is how a filter is guaranteed to mean the same thing everywhere.
User text is only ever passed as a parameter, never pasted into SQL.
"""

from __future__ import annotations

from typing import Any

from wildlife.domain.filters import SightingFilter


def countable_sql(alias: str = "v", include_probable: bool = False) -> str:
    """Rule for life/year lists: species level or below, wild, confident ID."""
    ids = "('certain', 'probable')" if include_probable else "('certain')"
    return f"{alias}.species_id IS NOT NULL AND {alias}.is_not_wild = 0 AND {alias}.identification IN {ids}"


def where(flt: SightingFilter, alias: str = "v") -> tuple[str, dict[str, Any]]:
    a = alias
    parts: list[str] = []
    params: dict[str, Any] = {}

    def ids(name: str, values) -> str:
        keys = []
        for i, value in enumerate(sorted(values)):
            key = f"{name}{i}"
            params[key] = value
            keys.append(f":{key}")
        return ", ".join(keys)

    if flt.category_ids:
        parts.append(f"{a}.category_id IN ({ids('cat', flt.category_ids)})")
    if flt.taxon_ids:
        listed = ids("tax", flt.taxon_ids)
        parts.append(f"({a}.taxon_id IN ({listed}) OR {a}.species_id IN ({listed}))")
    if flt.place_ids:
        parts.append(f"{a}.place_id IN ({ids('place', flt.place_ids)})")
    if flt.date_from:
        parts.append(f"{a}.observed_date >= :date_from")
        params["date_from"] = flt.date_from.isoformat()
    if flt.date_to:
        parts.append(f"{a}.observed_date <= :date_to")
        params["date_to"] = flt.date_to.isoformat()
    if flt.outing_id is not None:
        parts.append(f"{a}.outing_id = :outing")
        params["outing"] = flt.outing_id
    if flt.evidence:
        parts.append(f"{a}.evidence IN ({ids('ev', {e.value for e in flt.evidence})})")
    if flt.has_photos is not None:
        exists = f"EXISTS (SELECT 1 FROM sighting_photo sp WHERE sp.sighting_id = {a}.id)"
        parts.append(exists if flt.has_photos else f"NOT {exists}")
    if flt.months:
        parts.append(
            f"CAST(strftime('%m', {a}.observed_date) AS INTEGER) IN ({ids('mon', flt.months)})"
        )
    if flt.hours:
        parts.append(
            f"{a}.observed_time IS NOT NULL AND "
            f"CAST(substr({a}.observed_time, 1, 2) AS INTEGER) IN ({ids('hr', flt.hours)})"
        )
    if flt.import_batch_id is not None:
        parts.append(f"{a}.import_batch_id = :batch")
        params["batch"] = flt.import_batch_id
    if flt.needs_location:
        parts.append(f"{a}.eff_latitude IS NULL")
    text = " ".join(flt.text.split())
    if text:
        params["text"] = text
        if len(text) >= 3:  # use the full-text indexes
            params["fts"] = '"' + text.replace('"', '""') + '"'
            name_match = "SELECT n.taxon_id FROM taxon_name_fts f JOIN taxon_name n ON n.id = f.rowid WHERE taxon_name_fts MATCH :fts"
            notes_match = f"{a}.id IN (SELECT rowid FROM sighting_text_fts WHERE sighting_text_fts MATCH :fts)"
        else:
            name_match = "SELECT taxon_id FROM taxon_name WHERE name LIKE :text || '%'"
            notes_match = f"({a}.notes LIKE '%' || :text || '%')"
        parts.append(
            f"({a}.taxon_id IN ({name_match}) OR {a}.species_id IN ({name_match})"
            f" OR {a}.place_name LIKE '%' || :text || '%' OR {notes_match})"
        )
    return (" AND ".join(parts) or "1"), params
