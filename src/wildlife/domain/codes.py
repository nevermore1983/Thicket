"""Fixed lists of choices. The value is what's stored; `label` is what people see.

The database's CHECK constraints list the same values (see 0001_initial.sql);
tests make sure the two stay in step.
"""

from __future__ import annotations

from enum import StrEnum


class _Labelled(StrEnum):
    @property
    def label(self) -> str:
        return _LABELS.get(self.value, self.value.replace("_", " ").capitalize())

    @property
    def explanation(self) -> str:
        """A longer description for menus and tooltips (empty if the label says it all)."""
        return _EXPLANATIONS.get(self.value, "")


class Evidence(_Labelled):
    SEEN = "seen"
    HEARD = "heard"
    SEEN_HEARD = "seen_heard"
    SIGNS = "signs"
    DEAD = "dead"
    TRAPPED = "trapped"


class Identification(_Labelled):
    CERTAIN = "certain"
    PROBABLE = "probable"
    POSSIBLE = "possible"


class Sex(_Labelled):
    MALE = "male"
    FEMALE = "female"
    MIXED = "mixed"
    UNKNOWN = "unknown"


class LifeStage(_Labelled):
    ADULT = "adult"
    JUVENILE = "juvenile"
    IMMATURE = "immature"
    EGG = "egg"
    LARVA = "larva"
    PUPA = "pupa"
    NYMPH = "nymph"
    OTHER = "other"


class Habitat(_Labelled):
    WOODLAND = "woodland"
    GRASSLAND = "grassland"
    FARMLAND = "farmland"
    HEATH_MOORLAND = "heath_moorland"
    WETLAND = "wetland"
    FRESHWATER = "freshwater"
    COASTAL = "coastal"
    MARINE = "marine"
    GARDEN_URBAN = "garden_urban"
    UPLAND = "upland"
    OTHER = "other"


class CountQualifier(_Labelled):
    EXACT = "exact"
    APPROX = "approx"
    AT_LEAST = "at_least"


class LocationMethod(_Labelled):
    PLACE = "place"
    GRID_REF = "grid_ref"
    MAP = "map"
    PHOTO = "photo"
    TYPED = "typed"
    DEVICE = "device"
    IMPORT = "import"


class Weather(_Labelled):
    SUNNY = "sunny"
    PARTLY_CLOUDY = "partly_cloudy"
    OVERCAST = "overcast"
    RAIN = "rain"
    DRIZZLE = "drizzle"
    SNOW = "snow"
    FOG = "fog"


class Wind(_Labelled):
    CALM = "calm"
    LIGHT = "light"
    MODERATE = "moderate"
    STRONG = "strong"
    GALE = "gale"


class Visibility(_Labelled):
    GOOD = "good"
    MODERATE = "moderate"
    POOR = "poor"


_EXPLANATIONS = {
    "signs": "Tracks, droppings, feathers, nests, feeding remains",
    "trapped": "For example in a moth trap or small-mammal trap",
    "heard": "Identified by call or song only",
    "probable": "Fairly sure, but not certain",
    "possible": "Not sure: worth checking later",
}

_LABELS = {
    "seen_heard": "Seen & heard",
    "larva": "Larva / caterpillar",
    "heath_moorland": "Heath & moorland",
    "garden_urban": "Garden & urban",
    "approx": "Approximate",
    "at_least": "At least",
    "grid_ref": "Grid reference",
    "fog": "Fog / mist",
}
