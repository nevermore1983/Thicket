"""One record from any import file, in Thicket's terms, before it's matched to a species.

Every importer (iNaturalist, a spreadsheet, Darwin Core) turns its rows into
`ImportRecord`s; the shared import pipeline then matches names, checks for
duplicates and creates the sightings.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from wildlife.domain.codes import (
    CountQualifier,
    Evidence,
    Habitat,
    Identification,
    LifeStage,
    Sex,
)


@dataclass(frozen=True, slots=True)
class ImportRecord:
    line: int  # line in the file (the header is line 1), for messages
    observed_date: date | None
    scientific_name: str | None = None
    common_name: str | None = None
    observed_time: str | None = None  # 'HH:MM', UK clock time
    latitude: float | None = None
    longitude: float | None = None
    uncertainty_m: int | None = None
    location_text: str | None = None
    place_name: str | None = None  # matched to a saved place by name
    count: int | None = None
    count_qualifier: CountQualifier = CountQualifier.EXACT
    evidence: Evidence = Evidence.SEEN
    identification: Identification = Identification.CERTAIN
    sex: Sex | None = None
    life_stage: LifeStage | None = None
    habitat: Habitat | None = None
    is_not_wild: bool = False
    notes: str | None = None
    kingdom: str | None = None  # 'Animalia', 'Plantae', 'Fungi' or None if unknown
    uksi_key: str | None = None  # a UK Species Inventory key, when the file has one
    source_id: str | None = None  # the record's id in the other app, if it has one
    url: str | None = None
    image_url: str | None = None
    updated_at: str | None = None  # the other app's "last changed", to spot later edits
    problem: str | None = None  # why this row can't be imported

    @property
    def name(self) -> str:
        return self.scientific_name or self.common_name or "(no name)"
