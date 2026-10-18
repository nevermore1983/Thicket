"""The app's data shapes. Plain, immutable data classes: no Qt, no SQL."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date

from wildlife.domain.codes import (
    CountQualifier,
    Evidence,
    Habitat,
    Identification,
    LifeStage,
    LocationMethod,
    Sex,
    Visibility,
    Weather,
    Wind,
)
from wildlife.domain.dates import fmt_date
from wildlife.domain.photo_files import RAW_SUFFIXES


@dataclass(frozen=True, slots=True)
class Category:
    id: int
    name: str
    colour: str
    icon: str
    sort_order: int
    is_fallback: bool


@dataclass(frozen=True, slots=True)
class Taxon:
    id: int
    scientific_name: str
    common_name: str | None
    rank: str
    category_id: int
    species_id: int | None  # None = broader than a species (doesn't count in lists)
    is_custom: bool = False
    catalogue_key: str | None = None  # a UKSI key, or 'gbif:2490384' from a species pack

    @property
    def display_name(self) -> str:
        return self.common_name or self.scientific_name


@dataclass(frozen=True, slots=True)
class TaxonMatch:
    """One suggestion in the species picker."""

    taxon: Taxon
    uses: int  # how many times you've recorded it
    matched_name: str  # the name that matched (may be a synonym)


@dataclass(frozen=True, slots=True)
class Place:
    id: int
    name: str
    latitude: float
    longitude: float
    radius_m: int = 250
    habitat: Habitat | None = None
    notes: str | None = None
    is_favourite: bool = False
    is_archived: bool = False


@dataclass(frozen=True, slots=True)
class PlaceDraft:
    name: str
    latitude: float
    longitude: float
    radius_m: int = 250
    habitat: Habitat | None = None
    notes: str | None = None
    is_favourite: bool = False
    id: int | None = None


@dataclass(frozen=True, slots=True)
class SightingDraft:
    """What the add/edit form produces. Only taxon_id and observed_date are required."""

    taxon_id: int | None
    observed_date: date | None
    observed_time: str | None = None  # 'HH:MM'
    place_id: int | None = None
    latitude: float | None = None
    longitude: float | None = None
    uncertainty_m: int | None = None
    location_method: LocationMethod | None = None
    location_text: str | None = None
    count: int | None = 1
    count_qualifier: CountQualifier = CountQualifier.EXACT
    evidence: Evidence = Evidence.SEEN
    identification: Identification = Identification.CERTAIN
    sex: Sex | None = None
    life_stage: LifeStage | None = None
    habitat: Habitat | None = None
    is_not_wild: bool = False
    outing_id: int | None = None
    notes: str | None = None
    id: int | None = None  # set when editing an existing sighting


@dataclass(frozen=True, slots=True)
class Sighting:
    """A saved sighting, with the names the UI needs already joined in."""

    id: int
    uuid: str
    taxon_id: int
    common_name: str | None
    scientific_name: str
    rank: str
    species_id: int | None
    category_id: int
    observed_date: date
    observed_time: str | None
    place_id: int | None
    place_name: str | None
    latitude: float | None
    longitude: float | None
    uncertainty_m: int | None
    location_method: str | None
    location_text: str | None
    eff_latitude: float | None  # own coordinates, else the place's centre
    eff_longitude: float | None
    eff_uncertainty_m: int | None
    count: int | None
    count_qualifier: CountQualifier
    evidence: Evidence
    identification: Identification
    sex: Sex | None
    life_stage: LifeStage | None
    habitat: Habitat | None
    is_not_wild: bool
    outing_id: int | None
    notes: str | None
    created_at: str
    updated_at: str
    photo_count: int = 0
    cover_photo: str | None = None  # relative path of the first photo
    source: str | None = None  # None = recorded in Thicket; "inaturalist" = imported
    source_id: str | None = None  # the record's id there

    @property
    def display_name(self) -> str:
        return self.common_name or self.scientific_name

    @property
    def has_location(self) -> bool:
        return self.eff_latitude is not None

    @property
    def countable(self) -> bool:
        """Counts towards life/year lists (probable IDs handled by the caller's setting)."""
        return self.species_id is not None and not self.is_not_wild

    def to_draft(self) -> SightingDraft:
        return SightingDraft(
            id=self.id,
            taxon_id=self.taxon_id,
            observed_date=self.observed_date,
            observed_time=self.observed_time,
            place_id=self.place_id,
            latitude=self.latitude,
            longitude=self.longitude,
            uncertainty_m=self.uncertainty_m,
            location_method=LocationMethod(self.location_method) if self.location_method else None,
            location_text=self.location_text,
            count=self.count,
            count_qualifier=self.count_qualifier,
            evidence=self.evidence,
            identification=self.identification,
            sex=self.sex,
            life_stage=self.life_stage,
            habitat=self.habitat,
            is_not_wild=self.is_not_wild,
            outing_id=self.outing_id,
            notes=self.notes,
        )


@dataclass(frozen=True, slots=True)
class Photo:
    id: int
    uuid: str
    sha256: str
    rel_path: str
    original_name: str
    file_size: int
    width: int | None
    height: int | None
    taken_at: str | None  # 'YYYY-MM-DD HH:MM:SS' local camera time
    gps_latitude: float | None
    gps_longitude: float | None
    rotation: int = 0
    caption: str | None = None
    sighting_ids: tuple[int, ...] = field(default_factory=tuple)
    raw_rel_path: str | None = None  # the RAW original kept beside it (e.g. a Pixel .dng)
    raw_name: str | None = None
    raw_size: int | None = None
    camera: str | None = None  # e.g. 'Google Pixel 10 Pro'
    taken_source: str | None = None  # 'exif', 'file_name' or 'manual'

    @property
    def is_raw(self) -> bool:
        """The main file is itself a RAW file (imported without a JPEG)."""
        return self.rel_path.lower().endswith(RAW_SUFFIXES)

    @property
    def has_raw(self) -> bool:
        return self.raw_rel_path is not None or self.is_raw

    @property
    def in_inbox(self) -> bool:
        return not self.sighting_ids


@dataclass(frozen=True, slots=True)
class OutingDraft:
    """A trip or visit: groups sightings and holds the weather. Only the date is required."""

    outing_date: date | None
    start_time: str | None = None
    end_time: str | None = None
    place_id: int | None = None
    title: str | None = None
    weather: Weather | None = None
    temperature_c: float | None = None
    wind: Wind | None = None
    visibility: Visibility | None = None
    is_complete_list: bool = False
    notes: str | None = None
    id: int | None = None


@dataclass(frozen=True, slots=True)
class Outing:
    id: int
    uuid: str
    outing_date: date
    start_time: str | None
    end_time: str | None
    place_id: int | None
    place_name: str | None
    title: str | None
    weather: Weather | None
    temperature_c: float | None
    wind: Wind | None
    visibility: Visibility | None
    is_complete_list: bool
    notes: str | None
    sightings: int = 0
    species: int = 0

    @property
    def display_title(self) -> str:
        """The title, or 'Rainham Marshes · Sun 12 Oct 2026' made from place and date."""
        if self.title:
            return self.title
        day = fmt_date(self.outing_date)
        return f"{self.place_name} · {day}" if self.place_name else f"Outing · {day}"

    @property
    def in_progress(self) -> bool:
        return self.start_time is not None and self.end_time is None

    def covers(self, time: str | None) -> bool:
        """True if a sighting at `time` ('HH:MM') falls within this outing's times."""
        if time is None or self.start_time is None:
            return True
        return self.start_time <= time and (self.end_time is None or time <= self.end_time)

    def to_draft(self) -> OutingDraft:
        return OutingDraft(
            id=self.id,
            outing_date=self.outing_date,
            start_time=self.start_time,
            end_time=self.end_time,
            place_id=self.place_id,
            title=self.title,
            weather=self.weather,
            temperature_c=self.temperature_c,
            wind=self.wind,
            visibility=self.visibility,
            is_complete_list=self.is_complete_list,
            notes=self.notes,
        )
