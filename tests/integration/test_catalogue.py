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
    assert rows["Beetlus obscurus"]["category"] == "Other insect"
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
