"""Finding a region by typing (docs/27-find-your-region-plan.md, section 3)."""

import pytest

from wildlife.config.windows_region import windows_country
from wildlife.domain.regions import (
    OTHER_NAMES,
    REGIONS,
    fold,
    means_the_uk,
    region_matches,
    regions_of_country,
)


def finds(typed: str) -> set[str]:
    return {
        code for code, r in REGIONS.items() if code != "uk" and region_matches(typed, code, r.name)
    }


def test_folding():
    assert fold("  Côte d'Ivoire ") == "cote divoire"
    assert fold("St. Barthélemy") == "saint barthelemy"
    assert fold("Guinea-Bissau") == "guinea bissau"
    assert fold("Trinidad & Tobago") == "trinidad and tobago"
    assert fold("SÃO TOMÉ") == "sao tome"
    assert fold("st") == "st"  # on the way to "Sta...": not yet "Saint"


@pytest.mark.parametrize(
    ("typed", "code"),
    [
        ("Reunion", "re"),
        ("curacao", "cw"),
        ("Québec", "ca-qc"),
        ("quebec", "ca-qc"),
        ("Cote dIvoire", "ci"),
        ("cote d'ivoire", "ci"),
        ("St Kitts", "kn"),
        ("St. Lucia", "lc"),
        ("St Helena", "sh"),
        ("Tristan da Cunha", "sh"),
        ("Sao Tome", "st"),
        ("Guinea Bissau", "gw"),
        ("Trinidad & Tobago", "tt"),
        ("Ivory Coast", "ci"),
        ("Swaziland", "sz"),
        ("Cape Verde", "cv"),
        ("DR Congo", "cd"),
        ("DRC", "cd"),
        ("Congo-Kinshasa", "cd"),
        ("Zaire", "cd"),
        ("Congo-Brazzaville", "cg"),
        ("Czech Republic", "cz"),
        ("Holland", "nl"),
        ("Türkiye", "tr"),
        ("Turkiye", "tr"),
        ("Holy See", "va"),
        ("Bonaire", "bq"),
        ("Saba", "bq"),
        ("US Virgin Islands", "vi"),
        ("USVI", "vi"),
        ("BVI", "vg"),
        ("St Barts", "bl"),
        ("Washington DC", "us-dc"),
        ("ACT", "au-act"),
        ("NSW", "au-nsw"),
        ("PEI", "ca-pe"),
        ("Burma", "mm"),
        ("East Timor", "tl"),
        ("UAE", "ae"),
        ("Emirates", "ae"),
        ("Macau", "mo"),
        ("Viet Nam", "vn"),
        ("Republic of Korea", "kr"),
        ("DPRK", "kp"),
        ("West Bank", "ps"),
        ("Gaza", "ps"),
        ("Keeling", "cc"),
        ("Laos", "la"),
    ],
)
def test_finds(typed, code):
    assert code in finds(typed)


def test_finds_little_else():
    assert finds("Ivory Coast") == {"ci"}
    assert finds("Congo") == {"cd", "cg"}
    assert finds("Saint Martin") == {"mf"}
    assert "ee" in finds("st")  # Estonia, while "Saint..." is still being typed
    assert finds("") == set(REGIONS) - {"uk"}


def test_only_names_not_codes_or_the_rest_of_the_line():
    assert finds("za") == {"mz", "tz", "zm", "kz", "cd", "cg", "ps"}  # Zaire, Brazzaville, Gaza
    assert "za" not in finds("za")  # South Africa's code
    assert not finds("mb ") - {c for c, r in REGIONS.items() if "mb" in fold(r.name)}
    assert finds("species") == set()


def test_every_other_name_belongs_to_a_region():
    assert set(OTHER_NAMES) <= set(REGIONS)


@pytest.mark.parametrize(
    "typed",
    ["England", "scotland", "Wales", "UK", "uk", "Great Brit", "Northern Ireland", "Britain"],
)
def test_the_uk(typed):
    assert means_the_uk(typed)


@pytest.mark.parametrize("typed", ["", "en", "u", "France", "Ireland", "New South Wales"])
def test_not_the_uk(typed):
    assert not means_the_uk(typed)


def test_the_packs_of_a_country():
    assert regions_of_country("KE") == ["ke"]
    assert regions_of_country("ke") == ["ke"]
    assert regions_of_country("PR") == ["pr"]
    assert len(regions_of_country("US")) == 51 and "us-dc" in regions_of_country("US")
    assert len(regions_of_country("CA")) == 13 and "ca-on" in regions_of_country("CA")
    assert len(regions_of_country("AU")) == 8
    assert regions_of_country("RU") == ["ru-eu", "ru"]
    assert regions_of_country("NZ") == ["nz"]
    assert regions_of_country("JP") == ["jp"] and regions_of_country("TW") == ["tw"]
    for nothing in ("GB", "UK", "FJ", "AQ", "", None):  # Fiji, Antarctica: no pack
        assert regions_of_country(nothing) == []


def test_windows_country_is_a_two_letter_code_or_nothing():
    country = windows_country()  # whatever this computer is set to
    assert country is None or (len(country) == 2 and country.isupper())
