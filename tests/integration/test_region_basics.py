"""The rest of Thicket following where you record (docs/16-regions-plan.md, step 4):
the regions table, clocks for times in files, and spreadsheet date order."""

from datetime import UTC, date, datetime, timedelta

from helpers import inat_csv, inat_row
from wildlife.domain.csv_import import (
    describe_date_columns,
    guess_mapping,
    parse_date,
    read_table_text,
)
from wildlife.domain.dates import local_clock, pc_local, uk_local
from wildlife.domain.regions import POSTAL_CODES, REGIONS, region


def test_the_regions_wildlife_knows():
    assert len(POSTAL_CODES) == 51 and len(REGIONS) == 52  # 50 states, DC and the UK
    ohio = region("us-oh")
    assert (ohio.name, ohio.is_uk, ohio.month_first) == ("Ohio", False, True)
    assert region("uk").is_uk and not region("uk").month_first
    assert region("somewhere-unknown").code == "uk"
    for r in REGIONS.values():  # every start view is on the map, at a sensible zoom
        assert -90 < r.lat < 90 and -180 < r.lon < 180 and 3 <= r.zoom <= 11


def test_each_region_has_its_clock():
    assert local_clock("uk") is uk_local  # exact UK rules, whatever the PC is set to
    assert local_clock("us-oh") is pc_local  # the PC's own time zone
    moment = datetime(2026, 7, 4, 18, 30)  # UTC
    assert uk_local(moment) == datetime(2026, 7, 4, 19, 30)  # British summer time
    expected = moment.replace(tzinfo=UTC).astimezone().replace(tzinfo=None)
    assert pc_local(moment) == expected
    # Before 1970 Windows can't convert at all; an hour either way is still a sound answer
    old = datetime(1965, 6, 1, 12, 0)
    assert abs(pc_local(old) - (old + (expected - moment))) <= timedelta(hours=1)


def test_inaturalist_times_use_the_regions_clock(ctx, tmp_path):
    """Only when the time the observer typed can't be read: then iNaturalist's UTC time."""
    row = inat_row(1, observed_on_string="", time_observed_at="2026-07-04 18:30:00 UTC")
    path = tmp_path / "observations.csv"
    path.write_text(inat_csv([row]), encoding="utf-8")
    uk = ctx.inaturalist.preview(path).rows[0].record
    assert uk.observed_time == "19:30"  # UK summer time
    ctx.catalogue.set_region("us-oh")
    us = ctx.inaturalist.preview(path).rows[0].record
    assert us.observed_time == pc_local(datetime(2026, 7, 4, 18, 30)).strftime("%H:%M")


def test_spreadsheet_dates_follow_the_region(ctx):
    table = read_table_text("Species,Date\nRobin,03/05/2026\n")
    mapping = guess_mapping(table.header)
    in_uk = ctx.spreadsheet.preview(table, mapping).rows[0].record
    assert in_uk.observed_date == date(2026, 5, 3)  # 3 May
    ctx.catalogue.set_region("us-oh")
    in_us = ctx.spreadsheet.preview(table, mapping).rows[0].record
    assert in_us.observed_date == date(2026, 3, 5)  # March 5
    chosen = ctx.spreadsheet.preview(table, mapping, month_first=False).rows[0].record
    assert chosen.observed_date == date(2026, 5, 3)  # the import page's switch wins


def test_dates_that_only_make_sense_the_other_way_are_pointed_out():
    us_dates = read_table_text("Species,Date\nRobin,12/25/2026\n")
    uk_dates = read_table_text("Species,Date\nRobin,25/12/2026\n")
    mapping = guess_mapping(us_dates.header)
    assert "month/day/year" in describe_date_columns(us_dates, mapping, month_first=False)
    assert describe_date_columns(us_dates, mapping, month_first=True) is None
    assert "day/month/year" in describe_date_columns(uk_dates, mapping, month_first=True)
    assert describe_date_columns(uk_dates, mapping, month_first=False) is None
    assert parse_date("12/25/2026", month_first=True) == (date(2026, 12, 25), None)
    assert parse_date("12/25/2026") == (None, None)  # no 25th month
