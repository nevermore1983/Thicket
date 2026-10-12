"""The one filter shared by every screen (list, calendar, map, statistics, export)."""

from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date

from wildlife.domain.codes import Evidence


@dataclass(frozen=True, slots=True)
class SightingFilter:
    text: str = ""  # free text: species names, place, notes
    category_ids: frozenset[int] = field(default_factory=frozenset)
    taxon_ids: frozenset[int] = field(default_factory=frozenset)  # includes their subspecies
    date_from: date | None = None
    date_to: date | None = None
    place_ids: frozenset[int] = field(default_factory=frozenset)
    outing_id: int | None = None
    evidence: frozenset[Evidence] = field(default_factory=frozenset)
    has_photos: bool | None = None
    needs_location: bool = False
    months: frozenset[int] = field(default_factory=frozenset)  # 1-12, any year (e.g. "in May")
    hours: frozenset[int] = field(default_factory=frozenset)  # 0-23, of the recorded time
    import_batch_id: int | None = None  # the sightings one import added or updated

    @property
    def is_empty(self) -> bool:
        return self == SightingFilter()

    def cleared(self) -> SightingFilter:
        return SightingFilter()

    def with_(self, **changes) -> SightingFilter:
        return replace(self, **changes)


_SETS = ("category_ids", "taxon_ids", "place_ids", "months", "hours")


def filter_to_dict(flt: SightingFilter) -> dict:
    """A filter as plain JSON-ready values (only the parts that are set)."""
    out: dict = {}
    for name in flt.__dataclass_fields__:
        value = getattr(flt, name)
        if value in (None, "", False, frozenset()):
            continue
        if name in _SETS:
            value = sorted(value)
        elif name == "evidence":
            value = sorted(e.value for e in value)
        elif isinstance(value, date):
            value = value.isoformat()
        out[name] = value
    return out


def filter_from_dict(data: dict) -> SightingFilter:
    """The reverse of filter_to_dict. Unknown keys (from a newer WildLife) are ignored."""
    known = SightingFilter.__dataclass_fields__
    values: dict = {}
    for name, value in data.items():
        if name not in known:
            continue
        if name in _SETS:
            value = frozenset(value)
        elif name == "evidence":
            value = frozenset(Evidence(v) for v in value)
        elif name in ("date_from", "date_to"):
            value = date.fromisoformat(value)
        values[name] = value
    return SightingFilter(**values)
