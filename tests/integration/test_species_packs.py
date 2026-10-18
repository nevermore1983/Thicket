"""Species packs (docs/16-regions-plan.md, step 1): adding a region's species to the list
without copying any species, and showing a region's own names and suggestion order.

The US pack here is invented: a few real species in GBIF's record format, some also in
the test UK list (helpers.MINI_CATALOGUE), some not."""

import sqlite3

import pytest

from helpers import MINI_CATALOGUE, TODAY, US_PACK, taxon_id
from wildlife.data.migrate import available_migrations, migrate
from wildlife.data.repositories import taxa as taxa_repo
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import SightingDraft

CA = dict(region="us-ca", name="California", version="2026-10")


def install(ctx, records=US_PACK, **pack):
    return ctx.catalogue.install_pack(list(records), **(CA | pack))


def taxa_named(ctx, scientific_name):
    with ctx.db.connection() as conn:
        return conn.execute(
            "SELECT id, common_name, category_id, catalogue_key FROM taxon WHERE scientific_name = ?",
            (scientific_name,),
        ).fetchall()


def test_a_species_in_both_lists_stays_one_species(ctx):
    fox_before = taxon_id(ctx, "Vulpes vulpes")
    sighting = ctx.sightings.save(SightingDraft(fox_before, TODAY)).sighting
    assert install(ctx) == 5
    (fox,) = taxa_named(ctx, "Vulpes vulpes")  # one, not two
    assert fox["id"] == fox_before and fox["catalogue_key"] == "M1"  # still the UK species
    with ctx.db.connection() as conn:
        keys = {
            k for (k,) in conn.execute("SELECT key FROM taxon_key WHERE taxon_id = ?", (fox["id"],))
        }
    assert keys == {"M1", "gbif:5219243"}  # known by both keys
    assert ctx.sightings.get(sighting.id).taxon_id == fox_before  # sightings untouched
    assert ctx.sightings.totals(SightingFilter())[1] == 1  # the life list counts it once


def test_new_species_are_added_and_sorted_into_categories(ctx):
    install(ctx)
    (cardinal,) = taxa_named(ctx, "Cardinalis cardinalis")
    (monarch,) = taxa_named(ctx, "Danaus plexippus")
    names = {c.id: c.name for c in ctx.catalogue.categories()}
    assert names[cardinal["category_id"]] == "Bird"
    assert names[monarch["category_id"]] == "Butterfly & Moth"
    assert cardinal["catalogue_key"] == "gbif:2490384"
    with ctx.db.connection() as conn:
        species_of = conn.execute(
            "SELECT species_id = id FROM taxon WHERE id = ?", (cardinal["id"],)
        ).fetchone()[0]
    assert species_of == 1  # a species counts as itself on a life list


def test_choosing_a_region_shows_its_names_and_order(ctx):
    install(ctx)
    ctx.catalogue.set_region("us-ca")
    found = [m.taxon.display_name for m in ctx.catalogue.search("robin")]
    assert found[0] == "American Robin"  # most recorded in California
    assert taxa_named(ctx, "Larus argentatus")[0]["common_name"] == "American Herring Gull"
    assert [m.taxon.display_name for m in ctx.catalogue.search("redbird")] == ["Northern Cardinal"]
    ctx.catalogue.set_region("uk")
    found = [m.taxon.display_name for m in ctx.catalogue.search("robin")]
    assert found[0] == "Robin"
    assert taxa_named(ctx, "Larus argentatus")[0]["common_name"] == "Herring Gull"
    # either name finds it, whichever region is shown
    assert "Herring Gull" in [
        m.taxon.display_name for m in ctx.catalogue.search("american herring")
    ]


def test_a_species_only_in_another_region_keeps_a_name(ctx):
    install(ctx)
    ctx.catalogue.set_region("uk")
    (cardinal,) = taxa_named(ctx, "Cardinalis cardinalis")
    assert cardinal["common_name"] == "Northern Cardinal"  # the UK has no name: the US one


def test_reinstalling_a_pack_updates_it_without_copies(ctx):
    install(ctx)
    count = len(ctx.catalogue.search("cardinal"))
    renamed = [r | {"c": "Cardinal"} if r["s"] == "Cardinalis cardinalis" else r for r in US_PACK]
    install(ctx, renamed, version="2026-11")
    ctx.catalogue.set_region("us-ca")
    assert len(taxa_named(ctx, "Cardinalis cardinalis")) == 1
    assert taxa_named(ctx, "Cardinalis cardinalis")[0]["common_name"] == "Cardinal"
    assert len(ctx.catalogue.search("cardinal")) == count
    assert {p["region"]: p["version"] for p in ctx.catalogue.packs()}["us-ca"] == "2026-11"


def test_updating_the_uk_list_keeps_a_packs_species_and_names(ctx):
    install(ctx)
    with ctx.db.transaction() as conn:
        taxa_repo.install_catalogue(conn, MINI_CATALOGUE, version="next")
    assert len(taxa_named(ctx, "Turdus migratorius")) == 1
    assert len(taxa_named(ctx, "Cardinalis cardinalis")) == 1
    assert "Herring Gull" in [
        m.taxon.display_name for m in ctx.catalogue.search("american herring")
    ]


def test_the_same_name_in_another_kingdom_is_a_different_species(ctx):
    plant = {
        "k": "gbif:1",
        "r": "species",
        "s": "Larus argentatus",
        "c": "A made-up plant",
        "l": ["Plantae", "Tracheophyta"],
        "pr": 1,
    }
    install(ctx, [plant])
    assert len(taxa_named(ctx, "Larus argentatus")) == 2  # the gull and the plant


def test_packs_installed_are_listed(ctx):
    install(ctx)
    packs = {p["region"]: p for p in ctx.catalogue.packs()}
    assert set(packs) == {"uk", "us-ca"}
    assert packs["us-ca"]["name"] == "California" and packs["us-ca"]["taxa"] == 5
    assert packs["us-ca"]["source"] == "gbif" and packs["uk"]["source"] == "uksi"


def test_existing_uk_data_moves_to_the_new_tables(paths):
    """Upgrading a version 6 library (all of yours today)."""
    conn = sqlite3.connect(paths.database)
    try:
        migrate(conn, migrations=available_migrations()[:6])
        conn.execute(
            "INSERT INTO taxon (id, uksi_key, scientific_name, common_name, rank, category_id, priority) "
            "VALUES (1, 'R1', 'Erithacus rubecula', 'Robin', 'species', 1, 10)"
        )
        conn.execute("INSERT INTO taxon_name (taxon_id, name, kind) VALUES (1, 'Robin', 'common')")
        conn.execute("INSERT INTO app_meta (key, value) VALUES ('catalogue_version', '20260811a')")
        conn.commit()
        migrate(conn)
        assert conn.execute("SELECT catalogue_key FROM taxon").fetchone()[0] == "R1"
        assert conn.execute("SELECT key, taxon_id FROM taxon_key").fetchall() == [("R1", 1)]
        assert conn.execute(
            "SELECT region, priority, common_name FROM taxon_region"
        ).fetchall() == [("uk", 10, "Robin")]
        assert conn.execute("SELECT region, version, taxa FROM species_pack").fetchall() == [
            ("uk", "20260811a", 1)
        ]
        assert conn.execute("SELECT pack FROM taxon_name").fetchone()[0] == "uk"
        assert conn.execute("SELECT value FROM app_meta WHERE key = 'region'").fetchone()[0] == "uk"
    finally:
        conn.close()


def test_a_species_without_a_catalogue_key_is_still_refused(ctx):
    """The rule from version 1 still holds after the rename: a catalogue species has a key."""
    with pytest.raises(sqlite3.IntegrityError), ctx.db.transaction() as conn:
        conn.execute(
            "INSERT INTO taxon (scientific_name, rank, category_id, is_custom) VALUES ('x', 'species', 1, 0)"
        )
