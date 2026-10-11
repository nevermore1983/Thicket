import re
from datetime import date
from importlib import resources

import pytest

from wildlife.domain import codes
from wildlife.domain.codes import CountQualifier
from wildlife.domain.counting import CountError, format_count, parse_count
from wildlife.domain.models import Outing, OutingDraft, PlaceDraft, SightingDraft
from wildlife.domain.validation import validate_outing, validate_place, validate_sighting

TODAY = date(2026, 10, 11)


@pytest.mark.parametrize(
    ("text", "value", "qualifier"),
    [
        ("", None, CountQualifier.EXACT),
        ("1", 1, CountQualifier.EXACT),
        (" 12 ", 12, CountQualifier.EXACT),
        ("c. 200", 200, CountQualifier.APPROX),
        ("c200", 200, CountQualifier.APPROX),
        ("~40", 40, CountQualifier.APPROX),
        ("about 30", 30, CountQualifier.APPROX),
        ("50+", 50, CountQualifier.AT_LEAST),
        ("at least 6", 6, CountQualifier.AT_LEAST),
    ],
)
def test_parse_count(text, value, qualifier):
    count = parse_count(text)
    assert (count.value, count.qualifier) == (value, qualifier)


@pytest.mark.parametrize("bad", ["0", "-3", "lots", "1.5", "c. many"])
def test_parse_count_rejects(bad):
    with pytest.raises(CountError):
        parse_count(bad)


def test_format_count():
    assert format_count(None) == "Present"
    assert format_count(1200, CountQualifier.APPROX) == "c. 1,200"
    assert format_count(50, CountQualifier.AT_LEAST) == "50+"


def test_only_species_and_date_are_required():
    assert validate_sighting(SightingDraft(taxon_id=1, observed_date=TODAY), TODAY) == {}
    errors = validate_sighting(SightingDraft(taxon_id=None, observed_date=None), TODAY)
    assert set(errors) == {"species", "date"}


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"observed_date": date(2026, 10, 12)}, "date"),
        ({"observed_date": date(1850, 1, 1)}, "date"),
        ({"observed_time": "9:30"}, "time"),
        ({"observed_time": "24:00"}, "time"),
        ({"latitude": 51.5}, "location"),
        ({"latitude": 200.0, "longitude": 0.0}, "location"),
        ({"count": 0}, "count"),
        ({"notes": "x" * 10_001}, "notes"),
    ],
)
def test_sighting_rules(changes, field):
    draft = SightingDraft(**{"taxon_id": 1, "observed_date": TODAY, **changes})
    assert field in validate_sighting(draft, TODAY)


def test_place_rules():
    assert validate_place(PlaceDraft("Garden", 51.5, -0.1)) == {}
    assert set(validate_place(PlaceDraft("  ", 95, 0, radius_m=0))) == {
        "name",
        "location",
        "radius",
    }


def test_codes_match_database_constraints():
    """Every enum value must be allowed by the matching CHECK constraint in the schema."""
    sql = resources.files("wildlife.data.migrations").joinpath("0001_initial.sql").read_text()
    for column, enum in [
        ("evidence", codes.Evidence),
        ("identification", codes.Identification),
        ("sex", codes.Sex),
        ("life_stage", codes.LifeStage),
        ("habitat", codes.Habitat),
        ("count_qualifier", codes.CountQualifier),
        ("location_method", codes.LocationMethod),
        ("weather", codes.Weather),
        ("wind", codes.Wind),
        ("visibility", codes.Visibility),
    ]:
        allowed = set(re.findall(r"'([a-z_]+)'", re.search(rf"{column}\s+TEXT[^\n]*", sql)[0]))
        allowed |= set(
            re.findall(r"'([a-z_]+)'", re.search(rf"{column}\s+TEXT[^;]*?\)\)", sql, re.S)[0])
        )
        missing = {e.value for e in enum} - allowed
        assert not missing, f"{column}: {missing} not allowed by the database"


def test_labels_are_friendly():
    assert codes.Evidence.SEEN_HEARD.label == "Seen & heard"
    assert codes.Habitat.GARDEN_URBAN.label == "Garden & urban"
    assert codes.Identification.PROBABLE.label == "Probable"


def test_outing_needs_only_a_date():
    assert validate_outing(OutingDraft(outing_date=TODAY), TODAY) == {}
    assert set(validate_outing(OutingDraft(outing_date=None), TODAY)) == {"date"}


@pytest.mark.parametrize(
    ("changes", "field"),
    [
        ({"outing_date": date(2026, 10, 12)}, "date"),
        ({"start_time": "9:30"}, "start"),
        ({"end_time": "24:00"}, "end"),
        ({"start_time": "10:00", "end_time": "09:00"}, "end"),
        ({"temperature_c": 75.0}, "temperature"),
        ({"title": "x" * 121}, "title"),
    ],
)
def test_outing_rules(changes, field):
    draft = OutingDraft(**({"outing_date": TODAY} | changes))
    assert field in validate_outing(draft, TODAY)


def _outing(**changes):
    base = dict(
        id=1,
        uuid="u",
        outing_date=date(2026, 10, 11),
        start_time=None,
        end_time=None,
        place_id=None,
        place_name=None,
        title=None,
        weather=None,
        temperature_c=None,
        wind=None,
        visibility=None,
        is_complete_list=False,
        notes=None,
    )
    return Outing(**(base | changes))


def test_outing_title_and_times():
    assert _outing().display_title == "Outing · Sun 11 Oct 2026"
    assert _outing(place_name="Rainham").display_title == "Rainham · Sun 11 Oct 2026"
    assert _outing(title="Dawn chorus").display_title == "Dawn chorus"
    walk = _outing(start_time="08:00", end_time="10:30")
    assert not walk.in_progress
    assert walk.covers("09:15") and walk.covers(None)
    assert not walk.covers("07:59") and not walk.covers("10:31")
    assert _outing(start_time="08:00").in_progress
    assert _outing(start_time="08:00").to_draft().start_time == "08:00"
