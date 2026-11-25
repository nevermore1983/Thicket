import time

import pytest

from helpers import MINI_CATALOGUE, taxon_id
from wildlife.data.repositories import taxa as taxa_repo
from wildlife.domain.models import SightingDraft


def test_tree_species_links_and_categories(ctx):
    with ctx.db.connection() as conn:
        rows = {
            r["scientific_name"]: r
            for r in conn.execute(
                "SELECT t.*, c.name AS category, s.scientific_name AS counts_as FROM taxon t "
                "JOIN category c ON c.id = t.category_id LEFT JOIN taxon s ON s.id = t.species_id"
            )
        }
    assert rows["Erithacus rubecula"]["category"] == "Bird"
    assert rows["Sympetrum striolatum"]["category"] == "Dragonfly & Damselfly"
    assert rows["Aglais io"]["category"] == "Butterfly & Moth"
    assert rows["Vulpes vulpes"]["category"] == "Mammal"
    assert rows["Beetlus obscurus"]["category"] == "Insect & other invertebrate"
    assert (
        rows["Motacilla alba yarrellii"]["counts_as"] == "Motacilla alba"
    )  # subspecies -> species
    assert rows["Larus"]["counts_as"] is None  # a genus doesn't count as a species
    assert rows["Larus argentatus"]["parent_id"] == rows["Larus"]["id"]


def test_reinstall_keeps_user_choices_and_custom_species(ctx):
    with ctx.db.transaction() as conn:
        conn.execute(
            "UPDATE taxon SET is_hidden = 1, category_id = 9, category_is_manual = 1 "
            "WHERE scientific_name = 'Vulpes vulpes'"
        )
        conn.execute(
            "INSERT INTO taxon (scientific_name, common_name, rank, category_id, is_custom) "
            "VALUES ('Mysteria', 'Mystery bird', 'species', 1, 1)"
        )
        before = conn.execute("SELECT COUNT(*) FROM taxon").fetchone()[0]
    with ctx.db.transaction() as conn:
        taxa_repo.install_catalogue(conn, MINI_CATALOGUE)
        after = conn.execute("SELECT COUNT(*) FROM taxon").fetchone()[0]
        fox = conn.execute(
            "SELECT is_hidden, category_id FROM taxon WHERE scientific_name='Vulpes vulpes'"
        ).fetchone()
    assert after == before
    assert tuple(fox) == (1, 9)


def test_picker_finds_common_scientific_and_alternative_names(ctx):
    names = lambda q: [m.taxon.display_name for m in ctx.catalogue.search(q)]  # noqa: E731
    assert names("robin")[:2] == ["Robin", "American Robin"]
    assert names("redbreast") == ["Robin"]
    assert names("Erith")[0] == "Robin"
    assert "Gull" in names("seagull")
    assert names("ro")[0] == "Robin"  # 1-2 letters use the prefix path


def test_picker_puts_species_you_record_first(ctx):
    american = taxon_id(ctx, "Turdus migratorius")
    ctx.sightings.save(SightingDraft(taxon_id=american, observed_date=ctx.sightings._today()))
    results = ctx.catalogue.search("robin")
    assert results[0].taxon.display_name == "American Robin" and results[0].uses == 1


@pytest.mark.slow
def test_full_bundled_catalogue_installs_quickly(db):
    from wildlife.services.events import EventHub
    from wildlife.services.species_catalogue import SpeciesCatalogue

    catalogue = SpeciesCatalogue(db, EventHub())
    started = time.perf_counter()
    count = catalogue.install()
    assert count > 60_000 and time.perf_counter() - started < 30
    assert not catalogue.needs_install()
    top = [m.taxon.display_name for m in catalogue.search("finch", 4)]
    assert {"Goldfinch", "Chaffinch"} <= set(top)


# ---- short searches in scripts without spaces (docs/28-asia-plan.md, step 3) ----------
_CROW = ["Animalia", "Chordata", "Aves", "Passeriformes", "Corvidae"]
ASIAN_PACK = [
    {
        "k": "gbif:2482492",
        "r": "species",
        "s": "Corvus macrorhynchos",
        "c": "Large-billed Crow",
        "ln": ["大嘴乌鸦", "ハシブトガラス"],
        "l": _CROW,
        "pr": 900,
    },
    {
        "k": "gbif:2482473",
        "r": "species",
        "s": "Corvus corone",
        "c": "Carrion Crow",
        "ln": ["小嘴乌鸦", "ハシボソガラス"],
        "l": _CROW,
        "pr": 800,
    },
    {
        "k": "gbif:9000001",
        "r": "species",
        "s": "Corvus inventus",
        "c": "Made-up Crow",
        "ln": ["乌鸦"],
        "l": _CROW,
        "pr": 10,
    },
    {
        "k": "gbif:2492321",
        "r": "species",
        "s": "Passer montanus",
        "c": "Eurasian Tree Sparrow",
        "ln": ["麻雀", "スズメ"],
        "l": [*_CROW[:4], "Passeridae"],
        "pr": 950,
    },
]


@pytest.fixture
def in_china(ctx):
    with ctx.db.transaction() as conn:
        taxa_repo.install_pack(conn, ASIAN_PACK, "cn", "China", "gbif", "test")
    return ctx


def test_a_short_chinese_search_finds_names_with_it_anywhere(in_china):
    found = [m.taxon.display_name for m in in_china.catalogue.search("乌鸦")]
    assert found[0] == "Made-up Crow"  # the name that starts with it comes first
    assert set(found) == {"Made-up Crow", "Large-billed Crow", "Carrion Crow"}
    # one character, inside every crow's name: all three
    assert {m.taxon.display_name for m in in_china.catalogue.search("鸦")} == set(found)
    assert [m.taxon.display_name for m in in_china.catalogue.search("麻雀")] == [
        "Eurasian Tree Sparrow"
    ]


def test_a_short_japanese_search_too(in_china):
    found = {m.taxon.display_name for m in in_china.catalogue.search("ガラ")}
    assert found == {"Large-billed Crow", "Carrion Crow"}  # ハシブトガラス, ハシボソガラス
    assert {m.taxon.display_name for m in in_china.catalogue.search("スズ")} == {
        "Eurasian Tree Sparrow"
    }


def test_short_searches_in_the_latin_alphabet_still_match_word_starts(in_china):
    # "cr" starts the word "Crow"; "ri" is only inside "Carrion", so it isn't found
    assert "Carrion Crow" in [m.taxon.display_name for m in in_china.catalogue.search("cr")]
    assert "Carrion Crow" not in [m.taxon.display_name for m in in_china.catalogue.search("ri")]
