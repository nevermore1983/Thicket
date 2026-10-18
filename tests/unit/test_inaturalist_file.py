"""Reading iNaturalist exports (invented rows in iNaturalist's format)."""

from datetime import date, datetime

import pytest

from helpers import inat_csv, inat_row
from wildlife.domain.codes import Evidence, Identification
from wildlife.domain.dates import uk_local
from wildlife.domain.errors import ImportFileError
from wildlife.domain.inaturalist import read_text


def one(**kw):
    return read_text(inat_csv([inat_row(1, **kw)]))[0]


def test_a_typical_row():
    rec = one()
    assert (rec.source_id, rec.line) == ("1001", 2)
    assert (rec.observed_date, rec.observed_time) == (date(2026, 5, 3), "07:40")
    assert (rec.latitude, rec.longitude, rec.uncertainty_m) == (51.5, -0.12, 12)
    assert rec.location_text == "Test Park, Testshire, UK"
    assert rec.identification is Identification.CERTAIN and rec.evidence is Evidence.SEEN
    assert rec.kingdom == "Animalia" and rec.problem is None and not rec.is_not_wild


@pytest.mark.parametrize(
    ("entered", "utc", "expected"),
    [
        ("2026-05-03 07:40:12", "2026-05-03 06:40:12 UTC", (date(2026, 5, 3), "07:40")),
        ("2020-06-22T08:39:05+01:00", "2020-06-22 07:39:05 UTC", (date(2020, 6, 22), "08:39")),
        ("2021/09/18 2:05 PM", "2021-09-18 13:05:00 UTC", (date(2021, 9, 18), "14:05")),
        ("2021/09/18 12:05 AM", "", (date(2021, 9, 18), "00:05")),
        ("2026-05-03", "", (date(2026, 5, 3), None)),
        # Not readable: iNaturalist's UTC time becomes UK time (BST in summer, GMT in winter)
        ("Sun May 3 2026", "2026-05-03 23:30:00 UTC", (date(2026, 5, 4), "00:30")),
        ("", "2026-01-10 08:00:00 UTC", (date(2026, 1, 10), "08:00")),
    ],
)
def test_dates_and_uk_times(entered, utc, expected):
    rec = one(observed_on_string=entered, time_observed_at=utc, observed_on="2026-05-03")
    assert (rec.observed_date, rec.observed_time) == expected


def test_uk_summer_time_changes_at_one_in_the_morning_utc():
    def at(text):
        return uk_local(datetime.fromisoformat(text)).strftime("%m-%d %H:%M")

    assert at("2026-03-29 00:59") == "03-29 00:59" and at("2026-03-29 01:00") == "03-29 02:00"
    assert at("2026-10-25 00:59") == "10-25 01:59" and at("2026-10-25 01:00") == "10-25 01:00"


def test_rows_that_cant_be_imported_say_why():
    assert one(observed_on_string="", observed_on="", time_observed_at="").problem == "No date"
    assert one(scientific="", common_name="").problem == "Not identified yet"
    guess = one(scientific="", species_guess="Dandelion")
    assert guess.problem is None and guess.common_name == "Dandelion"


def test_quality_wild_status_and_notes():
    rec = one(
        quality_grade="needs_id",
        captive_cultivated="true",
        description="By the gate",
        tag_list="garden",
    )
    assert rec.identification is Identification.PROBABLE and rec.is_not_wild
    assert rec.notes == "By the gate\n\nTags: garden"
    assert one(quality_grade="casual").identification is Identification.PROBABLE


def test_positions():
    assert one(positional_accuracy="").uncertainty_m is None
    assert one(positional_accuracy="250000").uncertainty_m == 100_000  # Thicket's limit
    hidden = one(coordinates_obscured="true", public_positional_accuracy="28000")
    assert hidden.uncertainty_m == 28000  # the extra uncertainty from obscuring
    exact = one(private_latitude="51.4", private_longitude="0.2", coordinates_obscured="true")
    assert (exact.latitude, exact.longitude, exact.uncertainty_m) == (51.4, 0.2, 12)
    assert one(latitude="", longitude="").latitude is None


def test_kingdoms_and_sound_only_records():
    assert one(iconic_taxon_name="Plantae").kingdom == "Plantae"
    assert one(iconic_taxon_name="Fungi").kingdom == "Fungi"
    assert one(iconic_taxon_name="Insecta").kingdom == "Animalia"
    assert one(iconic_taxon_name="").kingdom is None
    heard = one(image_url="", sound_url="https://example.invalid/sound.m4a")
    assert heard.evidence is Evidence.HEARD


def test_other_files_are_refused_with_advice():
    with pytest.raises(ImportFileError, match="iNaturalist"):
        read_text("species,date\nRobin,2026-05-03\n")


def test_excel_resaved_file_reads(tmp_path):
    from wildlife.domain.inaturalist import read_file

    path = tmp_path / "export.csv"
    path.write_bytes(inat_csv([inat_row(1, description="Café garden")]).encode("cp1252"))
    assert read_file(path)[0].notes == "Café garden"


def test_the_zip_from_inaturalist_reads(tmp_path):
    import zipfile

    from wildlife.domain.inaturalist import read_file

    path = tmp_path / "observations-1.csv.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("README.txt", "Columns: ...")
        archive.writestr("observations-1.csv", inat_csv([inat_row(1), inat_row(2)]))
    assert [r.source_id for r in read_file(path)] == ["1001", "1002"]
    empty = tmp_path / "empty.zip"
    with zipfile.ZipFile(empty, "w") as archive:
        archive.writestr("README.txt", "nothing")
    with pytest.raises(ImportFileError, match=r"no \.csv"):
        read_file(empty)
