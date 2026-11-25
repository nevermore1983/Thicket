"""Finding a region by typing (docs/27-find-your-region-plan.md, section 3)."""

import pytest

from wildlife.domain.regions import OTHER_NAMES, REGIONS, fold, means_the_uk, region_matches


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
    assert finds("za") == {"mz", "tz", "zm", "cd", "cg"}  # Zaire, Brazzaville
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
