"""Business rules that need context the database can't check (e.g. 'today').

Each function returns {field: message}; an empty dict means valid. Messages
are written for the person filling in the form: what's wrong and how to fix it.
"""

from __future__ import annotations

import re
from datetime import date

from wildlife.domain.models import OutingDraft, PlaceDraft, SightingDraft

EARLIEST = date(1900, 1, 1)
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def validate_sighting(draft: SightingDraft, today: date) -> dict[str, str]:
    errors: dict[str, str] = {}
    if draft.taxon_id is None:
        errors["species"] = "Choose a species. Type part of its name, then pick from the list."
    if draft.observed_date is None:
        errors["date"] = "Choose the date of the sighting."
    elif draft.observed_date > today:
        errors["date"] = "The date can't be in the future."
    elif draft.observed_date < EARLIEST:
        errors["date"] = "That date is too long ago. Please check the year."
    if draft.observed_time is not None and not _TIME.match(draft.observed_time):
        errors["time"] = "Use 24-hour time like 09:30, or leave it empty if you don't know."
    if (draft.latitude is None) != (draft.longitude is None):
        errors["location"] = "A position needs both latitude and longitude."
    elif draft.latitude is not None and not (
        -90 <= draft.latitude <= 90 and -180 <= draft.longitude <= 180
    ):
        errors["location"] = "That position is off the map. Check latitude and longitude."
    if draft.uncertainty_m is not None and not 1 <= draft.uncertainty_m <= 100_000:
        errors["location"] = "Uncertainty must be between 1 m and 100 km."
    if draft.count is not None and draft.count < 1:
        errors["count"] = "The count must be 1 or more. Leave it empty if you didn't count."
    if draft.notes and len(draft.notes) > 10_000:
        errors["notes"] = "Notes can be up to 10,000 characters."
    if draft.location_text and len(draft.location_text) > 200:
        errors["location_text"] = "Keep the location description under 200 characters."
    return errors


def validate_place(draft: PlaceDraft) -> dict[str, str]:
    errors: dict[str, str] = {}
    if not draft.name.strip():
        errors["name"] = "Give the place a name, e.g. “Garden” or “Rainham Marshes”."
    if not -90 <= draft.latitude <= 90 or not -180 <= draft.longitude <= 180:
        errors["location"] = "That position is off the map. Check latitude and longitude."
    if not 1 <= draft.radius_m <= 100_000:
        errors["radius"] = "The radius must be between 1 m and 100 km."
    return errors


def validate_outing(draft: OutingDraft, today: date) -> dict[str, str]:
    errors: dict[str, str] = {}
    if draft.outing_date is None:
        errors["date"] = "Choose the date of the outing."
    elif draft.outing_date > today:
        errors["date"] = "The date can't be in the future."
    elif draft.outing_date < EARLIEST:
        errors["date"] = "That date is too long ago. Please check the year."
    for key, value in (("start", draft.start_time), ("end", draft.end_time)):
        if value is not None and not _TIME.match(value):
            errors[key] = "Use 24-hour time like 09:30, or leave it empty."
    if (
        draft.start_time
        and draft.end_time
        and "start" not in errors
        and "end" not in errors
        and draft.end_time < draft.start_time
    ):
        errors["end"] = "The outing can't end before it starts."
    if draft.temperature_c is not None and not -50 <= draft.temperature_c <= 60:
        errors["temperature"] = "That temperature looks wrong (−50 to 60 °C)."
    if draft.title and len(draft.title) > 120:
        errors["title"] = "Keep the title under 120 characters."
    return errors
