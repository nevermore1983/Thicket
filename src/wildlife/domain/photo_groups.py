"""Grouping Inbox photos into encounters, and turning photos into a new sighting."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, datetime

from wildlife.domain import geo
from wildlife.domain.codes import LocationMethod
from wildlife.domain.models import Photo, SightingDraft

GAP_MINUTES = 10
NEAR_METRES = 200
PHOTO_GPS_UNCERTAINTY_M = 10  # a phone's GPS fix, unless the photo says otherwise


@dataclass(frozen=True, slots=True)
class Encounter:
    """Photos probably of the same moment: close together in time and place."""

    photos: tuple[Photo, ...]

    @property
    def start(self) -> str | None:
        return self.photos[0].taken_at

    @property
    def end(self) -> str | None:
        return self.photos[-1].taken_at

    @property
    def located(self) -> int:
        return sum(p.gps_latitude is not None for p in self.photos)


def _moment(photo: Photo) -> datetime | None:
    try:
        return datetime.strptime(photo.taken_at, "%Y-%m-%d %H:%M:%S") if photo.taken_at else None
    except ValueError:
        return None


def group_encounters(
    photos: Iterable[Photo], minutes: int = GAP_MINUTES, metres: float = NEAR_METRES
) -> list[Encounter]:
    """Split photos (in time order) wherever there's a gap of more than `minutes`, or a jump
    of more than `metres` from the group's last known position. Undated photos form a
    final group of their own. Grouping only helps selection; it never creates sightings."""
    photos = list(photos)  # read twice below
    dated = sorted((p for p in photos if _moment(p)), key=lambda p: (_moment(p), p.id))
    undated = [p for p in photos if not _moment(p)]
    groups: list[list[Photo]] = []
    last_time: datetime | None = None
    last_place: tuple[float, float] | None = None
    for photo in dated:
        moment = _moment(photo)
        here = (photo.gps_latitude, photo.gps_longitude) if photo.gps_latitude is not None else None
        new_group = (
            not groups
            or (moment - last_time).total_seconds() > minutes * 60
            or (here and last_place and geo.distance_m(*here, *last_place) > metres)
        )
        if new_group:
            groups.append([])
            last_place = None
        groups[-1].append(photo)
        last_time = moment
        last_place = here or last_place
    encounters = [Encounter(tuple(g)) for g in groups]
    if undated:
        encounters.append(Encounter(tuple(undated)))
    return encounters


def draft_from_photos(photos: Iterable[Photo], today: date) -> SightingDraft:
    """A new sighting's details from its photos: date and time from the earliest photo,
    position from the first photo with GPS. The species is for you to choose."""
    photos = list(photos)
    dated = sorted((p for p in photos if _moment(p)), key=_moment)
    first = _moment(dated[0]) if dated else None
    located = next((p for p in dated + photos if p.gps_latitude is not None), None)
    return SightingDraft(
        taxon_id=None,
        observed_date=min(first.date(), today) if first else today,
        observed_time=first.strftime("%H:%M") if first else None,
        latitude=located.gps_latitude if located else None,
        longitude=located.gps_longitude if located else None,
        uncertainty_m=PHOTO_GPS_UNCERTAINTY_M if located else None,
        location_method=LocationMethod.PHOTO if located else None,
    )
