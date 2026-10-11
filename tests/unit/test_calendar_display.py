from datetime import date

import pytest

from wildlife.services.calendar import DaySummary
from wildlife.ui.calendar.month_view import cell_lines
from wildlife.ui.calendar.year_view import ramp_level, ramp_thresholds
from wildlife.ui.panels.outing_editor import parse_temperature


def summary(names, species=None, new=0) -> DaySummary:
    return DaySummary(
        day=date(2026, 5, 1),
        sightings=10,
        species=len(names) if species is None else species,
        category_ids=(1,),
        names=tuple(names),
        new_names=new,
        lifers=0,
        year_firsts=new,
    )


def test_everything_fits():
    assert cell_lines(summary(["Robin", "Wren"], new=1), 3) == [("Robin", True), ("Wren", False)]


def test_last_line_counts_the_rest():
    s = summary(["Robin", "Wren", "Jay", "Rook", "Coot", "Teal"], species=20, new=2)
    assert cell_lines(s, 3) == [("Robin", True), ("Wren", True), ("+18 more", False)]
    assert cell_lines(s, 10)[-1] == ("+14 more", False)  # only six names are kept


def test_one_line_squeezes_the_count_onto_it():
    assert cell_lines(summary(["Robin", "Wren", "Jay"]), 1) == [("Robin +2", False)]
    assert cell_lines(summary(["Robin"]), 0) == []


def test_ramp_splits_busy_days_into_equal_groups():
    counts = [1] * 50 + [2] * 30 + [5] * 15 + [40] * 5
    thresholds = ramp_thresholds(counts)
    assert len(thresholds) == 6
    assert ramp_level(0, thresholds) == 0
    assert ramp_level(1, thresholds) == 1
    assert ramp_level(40, thresholds) == 6
    assert ramp_level(5, thresholds) < 6  # one huge day doesn't flatten the rest
    assert ramp_thresholds([]) == [] and ramp_level(3, []) == 0


@pytest.mark.parametrize(
    ("text", "value"), [("", None), ("12", 12.0), ("-2.5", -2.5), ("12 °C", 12.0), ("−3", -3.0)]
)
def test_parse_temperature(text, value):
    assert parse_temperature(text) == value


def test_parse_temperature_rejects_words():
    with pytest.raises(ValueError):
        parse_temperature("warm")
