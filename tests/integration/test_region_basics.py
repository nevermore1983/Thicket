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
from wildlife.domain.regions import COUNTRY_CODES, POSTAL_CODES, REGIONS, group_of, region


def test_the_regions_wildlife_knows():
    assert len(POSTAL_CODES) == 51 and len(COUNTRY_CODES) == 52
    # 50 states, DC, 52 European regions, the UK, and (1.7.0) 13 Canadian provinces and
    # territories, 8 Australian states and territories, and New Zealand, and (1.8.0) 52
    # countries and territories of Latin America and the Caribbean, and (1.9.0) 60 of Africa
    assert len(REGIONS) == 286
    # Russia twice (west of the Urals, and all of it), Turkey and the Caucasus (1.6.1)
    assert {region(c).name for c in ("ru-eu", "ru", "tr", "ge", "am", "az")} == {
        "European Russia",
        "Russia (all)",
        "Turkey",
        "Georgia",
        "Armenia",
        "Azerbaijan",
    }
    assert region("ru").languages == ("ru",) and region("ru-eu").group == "Europe"
    ohio = region("us-oh")
    assert (ohio.name, ohio.is_uk, ohio.month_first) == ("Ohio", False, True)
    assert region("uk").is_uk and not region("uk").month_first
    assert region("somewhere-unknown").code == "uk"
    france = region("fr")
    assert (france.name, france.group, france.month_first) == ("France", "Europe", False)
    assert region("be").languages == ("fr", "nl", "de") and not region("fr").is_uk
    assert group_of("us-oh") == "United States" and group_of("zz") == "Elsewhere"
    for r in REGIONS.values():  # every start view is on the map, at a sensible zoom
        assert -90 < r.lat < 90 and -180 < r.lon < 180 and 3 <= r.zoom <= 15


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


def test_canada_australia_and_new_zealand():
    """docs/24-canada-australia-nz-plan.md: each under its own heading; Canada writes
    dates month-first like the US, Australia and New Zealand day-first like the UK."""
    ontario, quebec, nsw, nz = (region(c) for c in ("ca-on", "ca-qc", "au-nsw", "nz"))
    assert (ontario.name, ontario.group, ontario.month_first) == ("Ontario", "Canada", True)
    assert quebec.languages == ("fr",) and region("ca-nb").languages == ("fr",)
    assert ontario.languages == ()  # French is searchable where it's official
    assert (nsw.name, nsw.group, nsw.month_first) == ("New South Wales", "Australia", False)
    assert (nz.name, nz.group, nz.month_first, nz.languages) == (
        "New Zealand",
        "New Zealand",
        False,
        ("mi",),
    )
    assert group_of("ca-on") == "Canada" and group_of("au-tas") == "Australia"
    assert region("ca-on").lat > 41 and region("au-tas").lat < -39  # in the right hemisphere
    assert sum(r.group == "Canada" for r in REGIONS.values()) == 13
    assert sum(r.group == "Australia" for r in REGIONS.values()) == 8


def test_latin_america_and_the_caribbean():
    """docs/25-latin-america-caribbean-plan.md: one heading; dates day-first, except in
    Puerto Rico and the US Virgin Islands, which follow the US."""
    from wildlife.domain.regions import LATIN_AMERICA_CODES

    assert len(LATIN_AMERICA_CODES) == 52
    brazil, costa_rica, puerto_rico = (region(c) for c in ("br", "cr", "pr"))
    assert (brazil.name, brazil.group, brazil.languages) == (
        "Brazil",
        "Latin America and the Caribbean",
        ("pt",),
    )
    assert costa_rica.languages == ("es",) and not costa_rica.month_first
    assert puerto_rico.month_first and region("vi").month_first
    assert region("mq").languages == ("fr",) and region("cw").languages == ("nl",)
    assert region("jm").languages == ()  # English-speaking
    assert brazil.lat < 0 < region("mx").lat and region("fk").lat < -50
    assert group_of("gf") == "Latin America and the Caribbean"
    assert region("fr").group == "Europe"  # France's pack leaves French Guiana out


def test_africa():
    """docs/26-africa-plan.md: 60 countries and territories under one heading, dates
    day-first, and the languages GBIF has names in."""
    from wildlife.domain.regions import AFRICA_CODES

    assert len(AFRICA_CODES) == 60 and "BV" not in AFRICA_CODES.values()  # no Bouvet
    south_africa, kenya, morocco, reunion = (region(c) for c in ("za", "ke", "ma", "re"))
    assert (south_africa.name, south_africa.group, south_africa.languages) == (
        "South Africa",
        "Africa",
        ("af",),
    )
    assert kenya.languages == ("sw",) and not kenya.month_first
    assert morocco.languages == ("ar", "fr") and reunion.languages == ("fr",)
    assert region("gh").languages == ()  # English-speaking
    assert south_africa.lat < 0 < morocco.lat and region("tf").lat < -45
    assert group_of("mg") == "Africa"
    assert region("re").group == "Africa"  # France's pack leaves Réunion out, as GBIF does


def test_the_middle_east_and_asia():
    """docs/28-asia-plan.md: 48 places under two headings, after Africa; the Philippines
    writes dates month first; the languages GBIF has names in."""
    from wildlife.domain.regions import ASIA_CODES, GROUPS, MIDDLE_EAST_CODES

    assert (len(MIDDLE_EAST_CODES), len(ASIA_CODES)) == (14, 34)
    assert GROUPS[-3:] == ("Africa", "Middle East", "Asia")
    china, japan, israel, philippines = (region(c) for c in ("cn", "jp", "il", "ph"))
    assert (china.name, china.group, china.languages) == ("China", "Asia", ("zh",))
    assert japan.languages == ("ja",) and not japan.month_first
    assert (israel.group, israel.languages) == ("Middle East", ("he", "ar"))
    assert philippines.month_first and not region("id").month_first
    assert group_of("kz") == "Asia" and group_of("tr") == "Europe"  # Turkey stays in Europe
    assert region("ae").name == "United Arab Emirates" and region("ps").name == "Palestine"
    assert region("cc").lat < 0 < region("cn").lat
    for code in list(MIDDLE_EAST_CODES.values()) + list(ASIA_CODES.values()):
        r = region(code.lower())
        assert r.code == code.lower() and -15 < r.lat < 56 and 34 < r.lon < 146, code
