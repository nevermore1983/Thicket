"""Reading sightings from spreadsheets (CSV): column guessing and values."""

from datetime import date

import pytest

from wildlife.domain.codes import CountQualifier, Evidence, Identification, Sex
from wildlife.domain.csv_import import (
    describe_date_columns,
    guess_mapping,
    parse_count,
    parse_date,
    read_table_text,
    to_records,
)
from wildlife.domain.errors import ImportFileError


def records(text):
    table = read_table_text(text)
    return to_records(table, guess_mapping(table.header))


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("2026-05-03", (date(2026, 5, 3), None)),
        ("2026-05-03T07:40", (date(2026, 5, 3), "07:40")),
        ("03/05/2026", (date(2026, 5, 3), None)),  # UK order: 3 May
        ("3.5.26 7:05 pm", (date(2026, 5, 3), "19:05")),
        ("3rd May 2026", (date(2026, 5, 3), None)),
        ("12 Sept 2025 14:30", (date(2025, 9, 12), "14:30")),
        ("31/02/2026", (None, None)),
        ("yesterday", (None, None)),
    ],
)
def test_dates(text, expected):
    assert parse_date(text) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("12", (12, CountQualifier.EXACT)),
        ("c. 20", (20, CountQualifier.APPROX)),
        ("~1,200", (1200, CountQualifier.APPROX)),
        ("20+", (20, CountQualifier.AT_LEAST)),
        ("present", (None, CountQualifier.EXACT)),
        ("", (None, CountQualifier.EXACT)),
    ],
)
def test_counts(text, expected):
    assert parse_count(text) == expected


def test_columns_are_recognised_whatever_they_are_called():
    header = ["Common name", "Latin name", "Date seen", "Grid ref", "Site", "Number", "Comments"]
    assert guess_mapping(header) == {
        "species": 0,
        "scientific": 1,
        "date": 2,
        "grid_ref": 3,
        "place": 4,
        "count": 5,
        "notes": 6,
    }
    dwc = ["occurrenceID", "eventDate", "scientificName", "decimalLatitude", "decimalLongitude"]
    assert guess_mapping(dwc) == {"date": 1, "scientific": 2, "latitude": 3, "longitude": 4}


def test_rows_become_records():
    rec, bad, nameless = records(
        "Species;Date;Time;Grid reference;Count;Sex;Evidence;Identification;Wild\n"
        "Robin;03/05/2026;7.40;TQ 29 79;c. 4;Male;Heard;Probable;No\n"
        "Wren;someday;;;;;;;\n"
        ";04/05/2026;;;;;;;\n"
    )
    assert (rec.common_name, rec.observed_date, rec.observed_time) == (
        "Robin",
        date(2026, 5, 3),
        "07:40",
    )
    assert rec.latitude == pytest.approx(51.5, abs=0.01) and rec.uncertainty_m == 710
    assert (rec.count, rec.count_qualifier, rec.sex) == (4, CountQualifier.APPROX, Sex.MALE)
    assert rec.evidence is Evidence.HEARD and rec.identification is Identification.PROBABLE
    assert rec.is_not_wild
    assert bad.problem == "Date not understood: “someday”" and bad.line == 3
    assert nameless.problem == "No species"


def test_american_dates_are_flagged():
    table = read_table_text("Species,Date\nRobin,05/23/2026\n")
    assert "American" in describe_date_columns(table, guess_mapping(table.header))


def test_excel_workbooks_are_explained(tmp_path):
    from wildlife.domain.csv_import import read_table

    book = tmp_path / "records.xlsx"
    book.write_bytes(b"PK\x03\x04 not really a workbook")
    with pytest.raises(ImportFileError, match="CSV UTF-8"):
        read_table(book)
