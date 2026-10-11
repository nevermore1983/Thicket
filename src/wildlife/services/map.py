"""Map data: sightings as GeoJSON, species per grid square, and saved places.

GeoJSON is the standard text format web maps read. Python builds it here and
the map page draws it; the page never queries the database itself.
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass

from wildlife.data.db import Database
from wildlife.data.repositories import map as repo
from wildlife.domain import geo
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import Place
from wildlife.services.settings import SettingsService

SQUARE_SIZES = (10_000, 2_000, 1_000)  # 10 km "hectads", 2 km "tetrads", 1 km "monads"


@dataclass(frozen=True, slots=True)
class Bounds:
    west: float
    south: float
    east: float
    north: float


@dataclass(frozen=True, slots=True)
class SightingLayer:
    geojson: bytes
    shown: int  # sightings drawn on the map
    without_location: int  # matching sightings that can't be drawn
    bounds: Bounds | None
    heat: bytes  # GeoJSON for the heat map (see heat_geojson)


@dataclass(frozen=True, slots=True)
class SquareLayer:
    geojson: bytes
    size_m: int
    squares: int
    most_species: int
    too_imprecise: int  # located sightings whose uncertainty is bigger than the square
    outside_grid: int  # e.g. Northern Ireland or abroad: the British grid doesn't cover them


def _dumps(obj) -> bytes:
    return json.dumps(obj, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _bounds(lons: list[float], lats: list[float]) -> Bounds | None:
    if not lons:
        return None
    return Bounds(min(lons), min(lats), max(lons), max(lats))


HEAT_CELL = 0.002  # degrees: sightings within about 200 m are added together for the heat map


def heat_geojson(points: list[repo.MapPoint]) -> tuple[bytes, int]:
    """Sightings added up in ~200 m cells, as weighted points for the heat map.

    Why not one point per sighting? MapLibre ignores a point whose share of the colour
    is tiny, so 4,000 sightings at one reserve, each worth 1/4,000, would vanish.
    Each cell's weight is its share of the busiest ~25 km area (so the hottest place
    reaches the top colour); 's' counts sightings and 'a' animals (square-rooted, so one
    flock of 500 doesn't outweigh a year of visits). Returns (GeoJSON, number of cells)."""
    cells: dict[tuple[int, int], list[float]] = defaultdict(lambda: [0.0, 0.0, 0.0, 0.0])
    areas_s: dict[tuple[int, int], float] = defaultdict(float)
    areas_a: dict[tuple[int, int], float] = defaultdict(float)
    for p in points:
        animals = max(1, p.count or 1) ** 0.5
        cell = cells[(round(p.lat / HEAT_CELL), round(p.lon / HEAT_CELL))]
        cell[0] += 1
        cell[1] += animals
        cell[2] += p.lat
        cell[3] += p.lon
        area = (round(p.lat * 4), round(p.lon * 4))
        areas_s[area] += 1
        areas_a[area] += animals
    peak_s = max(areas_s.values(), default=1.0)
    peak_a = max(areas_a.values(), default=1.0)
    features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [round(lon / n, 5), round(lat / n, 5)]},
            "properties": {"s": round(n / peak_s, 5), "a": round(a / peak_a, 5)},
        }
        for n, a, lat, lon in cells.values()
    ]
    return _dumps({"type": "FeatureCollection", "features": features}), len(features)


def sightings_geojson(points: list[repo.MapPoint]) -> bytes:
    """One point per sighting. Short property names keep 20,000 points to about 2 MB."""
    features = [
        {
            "type": "Feature",
            "id": p.id,
            "geometry": {"type": "Point", "coordinates": [round(p.lon, 6), round(p.lat, 6)]},
            "properties": {
                "c": p.category_id,
                "n": p.name,
                "d": p.day,
                "w": max(1, p.count or 1),  # weight for "number of animals" heat
            },
        }
        for p in points
    ]
    return _dumps({"type": "FeatureCollection", "features": features})


def _to_grid(lat: float, lon: float) -> tuple[float, float] | None:
    """National Grid position, or None where the British grid doesn't apply."""
    if not (49.7 <= lat <= 61.0 and -8.9 <= lon <= 2.0) or geo.is_northern_ireland(lat, lon):
        return None
    e, n = geo.wgs84_to_grid(lat, lon)
    return (e, n) if 0 <= e < 700_000 and 0 <= n < 1_300_000 else None


def square_counts(
    points: list[repo.MapPoint], size_m: int
) -> tuple[dict[tuple[int, int], tuple[set, int]], int, int]:
    """(square -> (species ids, sightings), too imprecise, outside the grid)."""
    squares: dict[tuple[int, int], tuple[set, list]] = defaultdict(lambda: (set(), [0]))
    imprecise = outside = 0
    grid: dict[tuple[float, float], tuple[float, float] | None] = {}
    for p in points:
        if p.uncertainty_m is not None and p.uncertainty_m > size_m:
            imprecise += 1
            continue
        position = grid.get((p.lat, p.lon), False)
        if position is False:  # convert each distinct position once (places repeat a lot)
            position = grid[(p.lat, p.lon)] = _to_grid(p.lat, p.lon)
        if position is None:
            outside += 1
            continue
        key = geo.grid_square(*position, size_m)
        species, n = squares[key]
        if p.countable:
            species.add(p.species_id)
        n[0] += 1
    return {k: (s, n[0]) for k, (s, n) in squares.items()}, imprecise, outside


def squares_geojson(counts: dict[tuple[int, int], tuple[set, int]], size_m: int) -> bytes:
    features = []
    for (e, n), (species, sightings) in counts.items():
        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [
                        [[round(x, 6), round(y, 6)] for x, y in geo.square_polygon(e, n, size_m)]
                    ],
                },
                "properties": {
                    "s": len(species),
                    "k": sightings,
                    "ref": geo.format_grid_ref(e, n, 2, spaced=False)
                    if size_m == 10_000
                    else geo.format_grid_ref(e, n, 4),
                    "e": e,
                    "n": n,
                },
            }
        )
    return _dumps({"type": "FeatureCollection", "features": features})


def places_geojson(places: list[Place]) -> bytes:
    features = [
        {
            "type": "Feature",
            "id": p.id,
            "geometry": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [round(x, 6), round(y, 6)]
                        for x, y in geo.circle_polygon(p.latitude, p.longitude, p.radius_m)
                    ]
                ],
            },
            "properties": {"name": p.name},
        }
        for p in places
    ]
    return _dumps({"type": "FeatureCollection", "features": features})


class MapService:
    def __init__(self, db: Database, settings: SettingsService) -> None:
        self._db, self._settings = db, settings

    def _points(self, flt: SightingFilter) -> list[repo.MapPoint]:
        with self._db.connection() as conn:
            return repo.points(conn, flt, self._settings.current.count_probable_ids)

    def sightings(self, flt: SightingFilter) -> SightingLayer:
        points = self._points(flt)
        with self._db.connection() as conn:
            missing = repo.without_location(conn, flt)
        return SightingLayer(
            sightings_geojson(points),
            len(points),
            missing,
            _bounds([p.lon for p in points], [p.lat for p in points]),
            heat_geojson(points)[0],
        )

    def squares(self, flt: SightingFilter, size_m: int) -> SquareLayer:
        if size_m not in SQUARE_SIZES:
            raise ValueError(f"Unsupported square size {size_m}")
        counts, imprecise, outside = square_counts(self._points(flt), size_m)
        return SquareLayer(
            squares_geojson(counts, size_m),
            size_m,
            len(counts),
            max((len(s) for s, _ in counts.values()), default=0),
            imprecise,
            outside,
        )
