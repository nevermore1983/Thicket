import math

import pytest

from wildlife.domain import geo


def dms(d: int, m: int, s: float) -> float:
    return d + m / 60 + s / 3600


def test_projection_matches_ordnance_survey_worked_example():
    # OS "A guide to coordinate systems in Great Britain", Annex C (OSGB36 datum)
    e, n = geo.osgb36_latlon_to_grid(dms(52, 39, 27.2531), dms(1, 43, 4.5177))
    assert e == pytest.approx(651_409.903, abs=0.001)
    assert n == pytest.approx(313_177.270, abs=0.001)


def test_inverse_projection_matches_worked_example():
    lat, lon = geo.grid_to_osgb36_latlon(651_409.903, 313_177.270)
    assert lat == pytest.approx(dms(52, 39, 27.2531), abs=1e-7)
    assert lon == pytest.approx(dms(1, 43, 4.5177), abs=1e-7)


@pytest.mark.parametrize(
    ("lat", "lon", "expected"),
    [
        (51.50073, -0.12463, "TQ 3026 7964"),  # Big Ben (within ~5 m of OSTN15)
        (56.79685, -5.00360, "NN 1667 7128"),  # Ben Nevis summit
        (50.06600, -5.71470, "SW 3426 2504"),  # Land's End
    ],
)
def test_grid_ref_for_known_places(lat, lon, expected):
    assert geo.grid_ref_for(lat, lon, uncertainty_m=10) == expected


def test_grid_ref_digits_follow_uncertainty():
    lat, lon = 51.50073, -0.12463
    assert geo.grid_ref_for(lat, lon, 10) == "TQ 3026 7964"
    assert geo.grid_ref_for(lat, lon, 100) == "TQ 302 796"
    assert geo.grid_ref_for(lat, lon, 1000) == "TQ 30 79"
    assert geo.grid_ref_for(lat, lon, 5000) == "TQ 3 7"


def test_no_grid_ref_outside_gb_or_in_northern_ireland():
    assert geo.grid_ref_for(48.8566, 2.3522) is None  # Paris
    assert geo.grid_ref_for(54.597, -5.930) is None  # Belfast uses the Irish Grid


def test_round_trip_is_millimetre_accurate():
    for lat, lon in [(50.1, -5.5), (52.2, 1.6), (55.9, -3.2), (58.6, -3.1)]:
        lat2, lon2 = geo.grid_to_wgs84(*geo.wgs84_to_grid(lat, lon))
        assert geo.distance_m(lat, lon, lat2, lon2) < 0.01


@pytest.mark.parametrize(
    ("text", "size"),
    [("TQ 308 808", 100), ("tq308808", 100), ("TQ 30 80", 1000), ("TQ3080080800", 1), ("SU", None)],
)
def test_parse_grid_ref(text, size):
    square = geo.parse_grid_ref(text)
    if size is None:
        assert square is None  # letters alone aren't enough
    else:
        assert square is not None and square.size_m == size


def test_parse_grid_ref_returns_square_centre():
    square = geo.parse_grid_ref("TQ 308 808")
    assert (square.easting, square.northing) == (530_850, 180_850)


@pytest.mark.parametrize("bad", ["TQ 308 80", "II 123 456", "hello", "", "TQ 30a 808"])
def test_parse_grid_ref_rejects_bad_input(bad):
    assert geo.parse_grid_ref(bad) is None


def test_format_and_parse_agree():
    for e, n in [(530_268, 179_644), (216_672, 771_282), (651_409, 313_177)]:
        ref = geo.format_grid_ref(e, n, 10)
        square = geo.parse_grid_ref(ref)
        assert math.isclose(square.easting, e + 0.5) and math.isclose(square.northing, n + 0.5)


class TestParseLocation:
    def test_grid_reference(self):
        loc = geo.parse_location("TQ 308 808")
        assert loc.method == "grid_ref" and loc.uncertainty_m == 100
        assert loc.latitude == pytest.approx(51.508, abs=0.01)

    def test_decimal_pair_and_uncertainty_from_decimals(self):
        loc = geo.parse_location("51.5007, -0.1246")
        assert (loc.latitude, loc.longitude, loc.uncertainty_m) == (51.5007, -0.1246, 10)
        assert not loc.looks_swapped

    def test_swapped_pair_is_flagged(self):
        assert geo.parse_location("-0.1246, 51.5007").looks_swapped

    def test_google_maps_link(self):
        loc = geo.parse_location("https://www.google.com/maps/place/x/@51.49550,0.19750,15z")
        assert loc.method == "link" and loc.latitude == pytest.approx(51.4955)

    def test_openstreetmap_link(self):
        loc = geo.parse_location("https://www.openstreetmap.org/#map=16/51.4955/0.1975")
        assert loc.longitude == pytest.approx(0.1975)

    def test_degrees_minutes_seconds(self):
        loc = geo.parse_location("51°29'43.8\"N 0°11'51.0\"E")
        assert loc.latitude == pytest.approx(51.4955, abs=1e-4)
        assert loc.longitude == pytest.approx(0.1975, abs=1e-4)

    @pytest.mark.parametrize("bad", ["", "   ", "somewhere near the bridge", "200, 10"])
    def test_unrecognised(self, bad):
        assert geo.parse_location(bad) is None


def test_distance():
    # London to Edinburgh is about 534 km as the crow flies
    assert geo.distance_m(51.5074, -0.1278, 55.9533, -3.1883) == pytest.approx(534_000, rel=0.01)
