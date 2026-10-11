from datetime import date

import pytest

from wildlife.domain.dates import (
    add_months,
    add_years,
    fmt_date,
    month_end,
    parse_date_query,
    week_label,
    week_start,
)

TODAY = date(2026, 10, 11)


def test_formats():
    d = date(2026, 10, 11)
    assert fmt_date(d) == "Sun 11 Oct 2026"
    assert fmt_date(d, "medium") == "11 Oct 2026"
    assert fmt_date(d, "day") == "11 Oct"
    assert fmt_date(d, "full") == "Sunday 11 October 2026"


def test_month_arithmetic():
    assert add_months(date(2026, 1, 31), 1) == date(2026, 2, 28)
    assert add_months(date(2024, 1, 31), 1) == date(2024, 2, 29)
    assert add_months(date(2026, 1, 15), -1) == date(2025, 12, 15)
    assert add_months(date(2026, 11, 5), 14) == date(2028, 1, 5)
    assert add_years(date(2024, 2, 29), 1) == date(2025, 2, 28)
    assert month_end(date(2026, 2, 3)) == date(2026, 2, 28)


@pytest.mark.parametrize(
    ("text", "kind", "day", "label"),
    [
        ("May 2025", "month", date(2025, 5, 1), "May 2025"),
        ("  sept   2024 ", "month", date(2024, 9, 1), "September 2024"),
        ("may", "month", date(2026, 5, 1), "May 2026"),  # most recent May
        ("Dec", "month", date(2025, 12, 1), "December 2025"),  # December hasn't come yet
        ("2025", "year", date(2025, 1, 1), "2025"),
        ("12 May 2025", "day", date(2025, 5, 12), "Monday 12 May 2025"),
        ("12th March 2024", "day", date(2024, 3, 12), "Tuesday 12 March 2024"),
        ("12/5/2025", "day", date(2025, 5, 12), "Monday 12 May 2025"),  # UK order
        ("2025-05-12", "day", date(2025, 5, 12), "Monday 12 May 2025"),
    ],
)
def test_parse_date_query(text, kind, day, label):
    q = parse_date_query(text, TODAY)
    assert (q.kind, q.day, q.label) == (kind, day, label)


@pytest.mark.parametrize("text", ["", "robin", "31 Feb 2025", "13/13/2025", "1850", "mayfly", "20"])
def test_not_a_date(text):
    assert parse_date_query(text, TODAY) is None


def test_weeks_start_on_monday_and_label_nicely():
    assert week_start(date(2026, 10, 11)) == date(2026, 10, 5)  # a Sunday
    assert week_start(date(2026, 10, 5)) == date(2026, 10, 5)
    assert week_label(date(2026, 10, 11)) == "5 – 11 Oct 2026"
    assert week_label(date(2026, 10, 1)) == "28 Sep – 4 Oct 2026"
    assert week_label(date(2026, 1, 1)) == "29 Dec 2025 – 4 Jan 2026"
