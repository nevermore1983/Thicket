import json
from datetime import date

import pytest

from helpers import TODAY, taxon_id
from wildlife.domain import geo
from wildlife.domain.codes import Identification
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import PlaceDraft, SightingDraft
from wildlife.services.map import places_geojson

ALL = SightingFilter()
ROBIN, FOX, DARTER = "Erithacus rubecula", "Vulpes vulpes", "Sympetrum striolatum"
RAINHAM = (51.4955, 0.1975)  # in the TQ57 10 km square
BELFAST = (54.597, -5.930)  # Northern Ireland: Irish grid, not British


def add(ctx, sci, lat=None, lon=None, unc=10, **kw):
    return ctx.sightings.save(
        SightingDraft(
            taxon_id=taxon_id(ctx, sci),
            observed_date=kw.pop("day", TODAY),
            latitude=lat,
            longitude=lon,
            uncertainty_m=unc if lat is not None else None,
            **kw,
        )
    ).sighting


def test_sightings_layer_has_points_bounds_and_missing_count(ctx):
    add(ctx, ROBIN, *RAINHAM, count=3)
    add(ctx, FOX, 52.0, -1.0)
    add(ctx, FOX)  # no location
    layer = ctx.map.sightings(ALL)
    data = json.loads(layer.geojson)
    assert (layer.shown, layer.without_location) == (2, 1)
    robin = next(f for f in data["features"] if f["properties"]["n"] == "Robin")
    assert robin["geometry"]["coordinates"] == [0.1975, 51.4955]
    assert robin["properties"] == {"c": 1, "n": "Robin", "d": TODAY.isoformat(), "w": 3}
    assert (layer.bounds.west, layer.bounds.north) == (-1.0, 52.0)


def test_place_centre_is_used_when_sighting_has_no_position(ctx):
    place = ctx.places.save(PlaceDraft("Rainham", *RAINHAM, radius_m=800))
    add(ctx, ROBIN, place_id=place.id)
    layer = ctx.map.sightings(ALL)
    assert layer.shown == 1 and layer.without_location == 0


def test_filter_applies(ctx):
    add(ctx, ROBIN, *RAINHAM)
    add(ctx, FOX, *RAINHAM)
    birds = ctx.map.sightings(SightingFilter(category_ids=frozenset({1})))
    assert birds.shown == 1
    assert ctx.map.sightings(SightingFilter(text="zzz")).bounds is None


def test_species_per_square(ctx):
    add(ctx, ROBIN, *RAINHAM)
    add(ctx, ROBIN, *RAINHAM)
    add(ctx, FOX, *RAINHAM)
    add(ctx, DARTER, *RAINHAM, identification=Identification.POSSIBLE)  # not countable
    add(ctx, FOX, 52.0, -1.0)
    layer = ctx.map.squares(ALL, 10_000)
    data = json.loads(layer.geojson)
    assert (layer.squares, layer.most_species) == (2, 2)
    rainham = max(data["features"], key=lambda f: f["properties"]["k"])
    assert rainham["properties"]["s"] == 2 and rainham["properties"]["k"] == 4
    assert rainham["properties"]["ref"] == "TQ57"
    ring = rainham["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1] and len(ring) == 5
    lons, lats = [p[0] for p in ring], [p[1] for p in ring]
    assert min(lons) < RAINHAM[1] < max(lons) and min(lats) < RAINHAM[0] < max(lats)


def test_imprecise_and_out_of_grid_records_are_left_out_and_counted(ctx):
    add(ctx, ROBIN, *RAINHAM, unc=1_500)  # fits a 10 km square, not a 1 km one
    add(ctx, FOX, *BELFAST)
    one_km = ctx.map.squares(ALL, 1_000)
    assert (one_km.squares, one_km.too_imprecise, one_km.outside_grid) == (0, 1, 1)
    ten_km = ctx.map.squares(ALL, 10_000)
    assert (ten_km.squares, ten_km.too_imprecise) == (1, 0)


def test_unknown_square_size_is_refused(ctx):
    with pytest.raises(ValueError):
        ctx.map.squares(ALL, 5_000)


def test_places_become_circles():
    from wildlife.domain.models import Place

    data = json.loads(places_geojson([Place(1, "Garden", 51.5, -0.1, radius_m=100)]))
    ring = data["features"][0]["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1]
    for lon, lat in ring[:-1]:
        assert geo.distance_m(51.5, -0.1, lat, lon) == pytest.approx(100, rel=0.01)


def test_grid_square_geometry():
    assert geo.grid_square(530_850, 180_420, 1_000) == (530_000, 180_000)
    assert geo.grid_square(530_850, 180_420, 10_000) == (530_000, 180_000)
    assert geo.grid_square(539_999, 189_999, 2_000) == (538_000, 188_000)
    ring = geo.square_polygon(530_000, 180_000, 1_000)
    e, n = geo.wgs84_to_grid(ring[2][1], ring[2][0])  # north-east corner round-trips
    assert (round(e), round(n)) == (531_000, 181_000)


def test_old_dates_are_kept(ctx):
    add(ctx, ROBIN, *RAINHAM, day=date(1999, 5, 1))
    assert (
        json.loads(ctx.map.sightings(ALL).geojson)["features"][0]["properties"]["d"] == "1999-05-01"
    )


def test_heat_adds_up_nearby_sightings_and_scales_to_the_busiest_area(ctx):
    from wildlife.services.map import heat_geojson

    for _ in range(4):
        add(ctx, ROBIN, *RAINHAM)
    add(ctx, FOX, 51.49551, 0.19751, count=9)  # a few metres away: same ~200 m cell
    add(ctx, FOX, 52.0, -1.0)  # elsewhere
    points = ctx.map._points(ALL)
    data, cells = heat_geojson(points)
    features = json.loads(data)["features"]
    assert cells == 2
    busiest = max(features, key=lambda f: f["properties"]["s"])
    assert busiest["properties"]["s"] == 1.0  # the busiest area is the top of the scale
    quiet = min(features, key=lambda f: f["properties"]["s"])
    assert quiet["properties"]["s"] == pytest.approx(1 / 5, abs=1e-4)
    assert busiest["properties"]["a"] == 1.0
    assert quiet["properties"]["a"] == pytest.approx(1 / (4 + 3), abs=1e-4)  # sqrt(9) = 3
