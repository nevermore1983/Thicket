"""Reading eBird's exports (domain.ebird), from invented rows: Download My Data and a life list."""

import zipfile
from datetime import date

import pytest

from helpers import EBIRD_FULL as FULL
from helpers import EBIRD_LIFE as LIFE
from helpers import ebird_full_row as full_row
from helpers import ebird_life_row as life_row
from helpers import ebird_table as table
from wildlife.domain.ebird import clean_name, is_ebird, read_file, read_text
from wildlife.domain.errors import ImportFileError


def test_both_kinds_of_export_are_recognised():
    assert is_ebird(FULL) and is_ebird(LIFE)
    assert not is_ebird(["id", "observed_on", "scientific_name"])
    with pytest.raises(ImportFileError, match="doesn't look like an eBird export"):
        read_text("Species,Date\nRobin,03/05/2026\n")


def test_a_checklist_row_from_download_my_data():
    (rec,) = read_text(table(FULL, [full_row(**{"Observation Details": "Singing"})]))
    assert rec.observed_date == date(2026, 5, 3) and rec.observed_time == "07:45"
    assert (rec.latitude, rec.longitude, rec.uncertainty_m) == (52.123457, -1.765432, 100)
    assert rec.scientific_name == "Erithacus rubecula" and rec.common_name == "European Robin"
    assert rec.count == 2 and rec.notes == "Singing" and rec.kingdom == "Animalia"
    assert rec.source_id == "S100/Erithacus rubecula"
    assert rec.url == "https://ebird.org/checklist/S100"
    assert rec.place_name == rec.location_text == "Invented Park"
    assert not rec.is_not_wild and rec.problem is None


def test_times_counts_and_spread():
    rows = [
        full_row(Time="1:05 PM", Count="X"),  # present, not counted
        full_row(Time="", **{"Distance Traveled (km)": "2.5"}),  # a 2.5 km walk
        full_row(**{"Area Covered (ha)": "400"}),  # a 2 km square
        full_row(**{"Breeding Code": "NY", "Observation Details": ""}),
    ]
    pm, walk, area, breeding = read_text(table(FULL, rows))
    assert pm.observed_time == "13:05" and pm.count is None
    assert walk.observed_time is None and walk.uncertainty_m == 1_250
    assert area.uncertainty_m == 1_000
    assert breeding.notes == "Breeding code: NY"


def test_a_life_list_row_with_its_position_in_the_name():
    hotspot = life_row(Location="Invented Reserve", SubID="S200", Exotic="N")
    first, second = read_text(table(LIFE, [life_row(), hotspot]))
    assert first.observed_date == date(2026, 5, 3) and first.observed_time is None
    assert (first.latitude, first.longitude) == (52.123, -1.765)
    assert first.location_text == "Somewhere, England, GB"  # without the numbers
    assert first.source_id == "S100/Erithacus rubecula"  # the same as the full export's
    assert second.latitude is None and second.place_name == "Invented Reserve"
    assert not second.is_not_wild  # naturalised birds are wild


def test_escapes_and_domestic_birds_are_not_wild():
    rows = [
        life_row(Exotic="X"),
        life_row(Category="domestic", **{"Scientific Name": "Anser anser (Domestic type)"}),
    ]
    escapee, farmyard = read_text(table(LIFE, rows))
    assert escapee.is_not_wild and farmyard.is_not_wild
    assert farmyard.scientific_name == "Anser anser"


def test_names_are_tidied_for_the_species_list():
    assert clean_name("Branta canadensis [canadensis Group]") == "Branta canadensis"
    assert clean_name("Larus sp.") == "Larus"
    assert clean_name("Corvus corone/cornix") == "Corvus corone/cornix"  # yours to match
    assert clean_name("") is None


def test_rows_that_cant_be_sightings_say_why():
    rows = [full_row(Date=""), full_row(**{"Scientific Name": "", "Common Name": ""})]
    no_date, no_name = read_text(table(FULL, rows))
    assert no_date.problem == "No date" and no_name.problem == "No species name"


def test_the_zip_from_download_my_data(tmp_path):
    path = tmp_path / "ebird_1234567890.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("MyEBirdData.csv", "﻿" + table(FULL, [full_row()]))
    (rec,) = read_file(path)
    assert rec.scientific_name == "Erithacus rubecula"
