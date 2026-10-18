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
