"""The species pack builder's rules (scripts/build_species_packs.py), on made-up data:
no internet and no GBIF file needed."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from build_species_packs import (
    Candidate,
    choose_names,
    is_hybrid_cross,
    lineage,
    record,
    tidy,
    wants_a_name,
)


def test_lists_and_combinations_are_not_names():
    for bad in ("House/Italian Sparrow", "Fox, Red Fox", "Northern Cardinal (Common)", "", "  "):
        assert tidy(bad) is None
    assert tidy("house sparrow") == "House Sparrow"  # all lower case: capitalised
    assert tidy("Black-capped Chickadee") == "Black-capped Chickadee"  # left as written
    assert tidy("  European   Starling ") == "European Starling"


def test_birds_use_the_names_us_birders_use():
    starling = [
        Candidate("Common Starling", "Multilingual IOC World Bird List, v11.2"),
        Candidate("Starling", "Martha's Vineyard species checklist"),
        Candidate("European/Spotless Starling", "The Clements Checklist"),
        Candidate("European Starling", "The Clements Checklist"),
    ]
    name, others = choose_names(starling, is_bird=True)
    assert name == "European Starling"  # Clements (eBird) first, the combination skipped
    assert others == ["Common Starling", "Starling"]  # still found by search


def test_other_groups_prefer_general_lists_and_us_names():
    beech = [
        Candidate("beech", "Brazilian Flora 2020 project"),
        Candidate("European Beech", "Checklist of Vermont Species", "US"),
        Candidate("Beech", "Dyntaxa. Svensk taxonomisk databas", "GB"),
    ]
    assert choose_names(beech, is_bird=False)[0] == "European Beech"
    assert choose_names([], is_bird=False) == (None, [])


def test_a_record_is_in_the_uk_lists_format():
    taxon = {
        "canonicalName": "Cardinalis cardinalis",
        "scientificName": "Cardinalis cardinalis (Linnaeus, 1758)",
        "scientificNameAuthorship": "(Linnaeus, 1758)",
        "kingdom": "Animalia",
        "phylum": "Chordata",
        "class": "Aves",
        "order": "Passeriformes",
        "family": "Cardinalidae",
    }
    rec = record(
        2490384,
        812_345,
        taxon,
        ["Richmondena cardinalis"],
        [Candidate("Northern Cardinal", "The Clements Checklist")],
    )
    assert rec == {
        "k": "gbif:2490384",
        "r": "species",
        "s": "Cardinalis cardinalis",
        "a": "(Linnaeus, 1758)",
        "c": "Northern Cardinal",
        "l": ["Animalia", "Chordata", "Aves", "Passeriformes", "Cardinalidae"],
        "pr": 812_345,
        "sy": ["Richmondena cardinalis"],
    }


def test_fish_without_a_class_are_filed_as_fish():
    """GBIF gives ray-finned fish no class; Thicket sorts by class, so it's filled in."""
    perch = {
        "kingdom": "Animalia",
        "phylum": "Chordata",
        "order": "Perciformes",
        "family": "Percidae",
    }
    assert lineage(perch) == ["Animalia", "Chordata", "Actinopterygii", "Perciformes", "Percidae"]
    lizard = {
        "kingdom": "Animalia",
        "phylum": "Chordata",
        "class": "Squamata",
        "family": "Iguanidae",
    }
    assert lineage(lizard)[2] == "Squamata"  # left alone (sorted by its own rule)


def test_a_bracketed_name_is_used_only_when_there_is_nothing_better():
    muscovy = [Candidate("Muscovy Duck (Domestic type)", "The Clements Checklist")]
    assert choose_names(muscovy, is_bird=True) == ("Muscovy Duck", [])
    cardinal = [
        Candidate("Northern Cardinal (Common)", "The Clements Checklist"),
        Candidate("Northern Cardinal", "Taxonomy in Flux Checklist"),
    ]
    assert choose_names(cardinal, is_bird=True)[0] == "Northern Cardinal"


def test_crosses_between_species_are_left_out_but_named_hybrids_kept():
    assert is_hybrid_cross("Anas rubripes x platyrhynchos")
    assert is_hybrid_cross("Quercus alba × macrocarpa")
    assert not is_hybrid_cross("Mentha × piperita")  # peppermint: a hybrid species
    assert not is_hybrid_cross("Cardinalis cardinalis")


def test_only_vertebrates_and_dragonflies_get_a_name_looked_up():
    bird = {"kingdom": "Animalia", "phylum": "Chordata", "class": "Aves", "order": "Anseriformes"}
    darter = {"kingdom": "Animalia", "phylum": "Arthropoda", "class": "Insecta", "order": "Odonata"}
    beetle = {
        "kingdom": "Animalia",
        "phylum": "Arthropoda",
        "class": "Insecta",
        "order": "Coleoptera",
    }
    assert wants_a_name(bird) and wants_a_name(darter) and not wants_a_name(beetle)


# ---- Europe (docs/23-europe-packs-plan.md) --------------------------------------------
def test_europe_uses_the_uk_name_first_then_british_and_irish_ones():
    from build_species_packs import EUROPE_NAMES

    robin = [
        Candidate("European Robin", "IOC World Bird List"),
        Candidate("Robin Redbreast", "Some list", "GB"),
    ]
    name, others = choose_names(robin, True, EUROPE_NAMES, uk_name="Robin")
    assert name == "Robin" and others == ["Robin Redbreast", "European Robin"]
    redstart = [
        Candidate("Black Redstart", "The Clements Checklist"),
        Candidate("Black redstart", "Catalogue of Life Checklist", "GB"),
    ]
    assert choose_names(redstart, True, EUROPE_NAMES)[0] == "Black redstart"  # used in GB
    wren = [
        Candidate("Eurasian Wren", "The Clements Checklist"),
        Candidate("Northern Wren", "IOC World Bird List"),
    ]
    assert choose_names(wren, True, EUROPE_NAMES)[0] == "Northern Wren"  # IOC before Clements
    assert choose_names(wren, True)[0] == "Eurasian Wren"  # the US keeps Clements first


def test_local_names_for_search():
    from build_species_packs import local_names

    by_language = {
        "fr": ["rougequeue noir", "Rougequeue noir", "Rougequeue Noir / Titys", "Rossignol"],
        "nl": ["Zwarte Roodstaart"],
        "de": ["Hausrotschwanz"],
    }
    assert local_names(by_language, ("fr", "nl"), {"Black Redstart"}) == [
        "Rougequeue noir",  # only the first letter capitalised, and only once
        "Rossignol",
        "Zwarte Roodstaart",
    ]
    assert local_names(by_language, (), set()) == []  # Gibraltar: English only


def test_a_european_record_carries_its_local_names(tmp_path):
    from build_species_packs import EUROPE_NAMES, write_manifests

    taxon = {
        "canonicalName": "Phoenicurus ochruros",
        "scientificName": "Phoenicurus ochruros (S.G.Gmelin, 1774)",
        "kingdom": "Animalia",
        "class": "Aves",
    }
    rec = record(2492546, 50, taxon, [], [], EUROPE_NAMES, "Black Redstart", ["Rougequeue noir"])
    assert rec["c"] == "Black Redstart" and rec["ln"] == ["Rougequeue noir"]
    # Three lists, each with only the regions its versions know
    packs = [{"region": r} for r in ("fr", "tr", "us-oh", "ca-on", "au-tas", "nz")]
    write_manifests(tmp_path, {"format": 1, "packs": packs})
    import json

    def regions(name: str) -> list[str]:
        listed = json.loads((tmp_path / name).read_text(encoding="utf-8"))["packs"]
        return [p["region"] for p in listed]

    assert regions("manifest-3.json") == ["fr", "tr", "us-oh", "ca-on", "au-tas", "nz"]
    assert regions("manifest-2.json") == ["fr", "us-oh"]  # 1.6.0: no Turkey, no Canada...
    assert regions("manifest.json") == ["us-oh"]  # 1.1 to 1.5


def test_european_russia_is_west_of_the_urals():
    from build_species_packs import european_countries

    areas = {a.region: a for a in european_countries()}
    assert areas["ru-eu"].filters == (("country", "RU"), ("decimalLongitude", "19,60"))
    assert areas["ru"].filters == (("country", "RU"),)  # all of Russia
    assert areas["tr"].filters == (("country", "TR"),) and areas["tr"].languages == ("tr",)


def test_the_uk_lists_names_are_read_by_species_and_kingdom():
    from build_species_packs import uk_names

    names = uk_names()  # the UK list built into Thicket
    assert names[("erithacus rubecula", "animalia")] == "Robin"
    assert len(names) > 10_000


def test_the_uk_name_is_found_when_the_genus_differs():
    """GBIF's Sylvia curruca is the UK list's Curruca curruca: Lesser Whitethroat, not
    GBIF's Grey Whitethroat (the rule Thicket links them by, taxa.link_renamed)."""
    from build_species_packs import uk_name_for, uk_names

    uk = uk_names()
    assert uk_name_for(uk, "Sylvia curruca", "Animalia", ["Curruca curruca curruca"]) == (
        "Lesser Whitethroat"
    )
    assert uk_name_for(uk, "Erithacus rubecula", "Animalia", []) == "Robin"
    invented = {
        ("curruca communis", "animalia"): "Whitethroat",
        ("synonym", "sylvia communis", "animalia"): {"Whitethroat"},
        ("jasminum humile", "plantae"): "Italian Jasmine",
    }
    assert uk_name_for(invented, "Sylvia communis", "Animalia", []) == "Whitethroat"
    # a synonym that changes the species' own word isn't trusted
    assert uk_name_for(invented, "Chrysojasminum fruticans", "Plantae", ["Jasminum humile"]) is None


# ---- Canada, Australia and New Zealand (docs/24-canada-australia-nz-plan.md) ---------
def pretend_gbif(monkeypatch, areas: dict[str, str]):
    """GBIF's GADM areas: id -> name (a made-up answer, never the internet)."""
    import build_species_packs

    def get_json(path, params=None):
        if path == "occurrence/search":
            counts = [{"name": gid, "count": 1} for gid in [*areas, "USA.27_1"]]
            return {"facets": [{"counts": counts}]}
        return {"name": areas[path.removeprefix("geocode/gadm/")]}

    monkeypatch.setattr(build_species_packs, "get_json", get_json)


def test_australias_states_with_jervis_bay_in_new_south_wales(monkeypatch):
    from build_species_packs import australian_states

    names = [
        "Ashmore and Cartier Islands",
        "Australian Capital Territory",
        "Coral Sea Islands Territory",
        "Jervis Bay Territory",
        "New South Wales",
        "Northern Territory",
        "Queensland",
        "South Australia",
        "Tasmania",
        "Victoria",
        "Western Australia",
    ]
    pretend_gbif(monkeypatch, {f"AUS.{i + 1}_1": n for i, n in enumerate(names)})
    areas = {a.region: a for a in australian_states()}
    assert len(areas) == 8  # the remote reefs are left out
    assert areas["au-nsw"].filters == (
        ("country", "AU"),
        ("gadmLevel1Gid", "AUS.4_1"),  # Jervis Bay Territory
        ("gadmLevel1Gid", "AUS.5_1"),
    )
    assert areas["au-tas"].name == "Tasmania" and areas["au-tas"].group == "Australia"


def test_canadas_provinces_match_gadms_accented_names(monkeypatch):
    from build_species_packs import canadian_provinces

    from wildlife.domain.regions import PROVINCE_CODES

    names = [n if n != "Quebec" else "Québec" for n in PROVINCE_CODES]  # as GADM has it
    pretend_gbif(monkeypatch, {f"CAN.{i + 1}_1": n for i, n in enumerate(names)})
    areas = {a.region: a for a in canadian_provinces()}
    assert len(areas) == 13
    assert areas["ca-qc"].name == "Quebec" and areas["ca-qc"].languages == ("fr",)
    assert areas["ca-on"].languages == () and areas["ca-on"].style.home == ("CA", "US")


def test_an_area_gbif_has_but_thicket_doesnt_stops_the_build(monkeypatch):
    import pytest
    from build_species_packs import canadian_provinces

    pretend_gbif(monkeypatch, {"CAN.1_1": "Alberta", "CAN.99_1": "Somewhere New"})
    with pytest.raises(SystemExit, match="Somewhere New"):
        canadian_provinces()


def test_regions_are_chosen_by_code_or_group(monkeypatch):
    import build_species_packs as b

    def made_up(prefix, group, codes):
        return lambda: [b.Area(f"{prefix}{c}", c, (), group) for c in codes]

    monkeypatch.setattr(
        b,
        "SOURCES_OF_AREAS",
        (
            ("us", "us-", made_up("us-", "United States", ["oh", "ca"])),
            ("canada", "ca-", made_up("ca-", "Canada", ["on", "qc"])),
            ("australia", "au-", made_up("au-", "Australia", ["tas"])),
            ("nz", "nz", made_up("", "New Zealand", ["nz"])),
            ("europe", "", made_up("", "Europe", ["fr", "ie"])),
        ),
    )
    regions = lambda asked: [a.region for a in b.chosen_areas(asked)]  # noqa: E731
    assert regions("ca-on,nz,fr") == ["ca-on", "nz", "fr"]
    assert regions("canada") == ["ca-on", "ca-qc"]
    assert regions("australia,us-oh") == ["us-oh", "au-tas"]
    assert len(regions(None)) == 8
    import pytest

    with pytest.raises(SystemExit, match="ca-zz"):
        regions("ca-zz")


def test_australian_birds_get_ioc_and_australian_names():
    from build_species_packs import AUSTRALIA_NAMES, CANADA_NAMES

    magpie = [
        Candidate("Australian Magpie", "IOC World Bird List"),
        Candidate("Magpie", "Some other list", "AU"),
        Candidate("Australasian Magpie", "The Clements Checklist"),
    ]
    assert choose_names(magpie, True, AUSTRALIA_NAMES)[0] == "Magpie"  # Australians' own
    jay = [
        Candidate("Canada Jay", "The Clements Checklist"),
        Candidate("Grey Jay", "IOC World Bird List"),
    ]
    assert choose_names(jay, True, CANADA_NAMES)[0] == "Canada Jay"  # as eBird has it


def test_australia_and_new_zealand_spell_grey_the_british_way():
    from build_species_packs import AUSTRALIA_NAMES, US_NAMES

    fox = [Candidate("Gray-headed Flying Fox", "Catalogue of Life")]
    assert choose_names(fox, False, AUSTRALIA_NAMES)[0] == "Grey-headed Flying Fox"
    assert choose_names(fox, False, US_NAMES)[0] == "Gray-headed Flying Fox"
    whale = [Candidate("Gray's Beaked Whale", "Catalogue of Life")]  # named after Mr Gray
    assert choose_names(whale, False, AUSTRALIA_NAMES)[0] == "Gray's Beaked Whale"
