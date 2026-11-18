"""One species under two names (1.6.1): GBIF's Backbone and the UK list don't always
agree on the genus. GBIF's Sylvia curruca is the UK list's Curruca curruca, so a pack
must link to the UK species, not add a second one. Invented records, real names."""

from helpers import MINI_CATALOGUE, TODAY
from wildlife.data.repositories import taxa as taxa_repo
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import SightingDraft

_WARBLER = ["Animalia", "Chordata", "Aves", "Passeriformes", "Sylviidae"]
_PLANT = ["Plantae", "Tracheophyta", "Magnoliopsida", "Lamiales", "Oleaceae"]

# What the UK list has (its own keys), added to the test UK list
UK_EXTRA = [
    {"k": "UKW1", "r": "species", "s": "Curruca curruca", "c": "Lesser Whitethroat", "l": _WARBLER},
    {
        "k": "UKW2",
        "r": "species",
        "s": "Curruca communis",
        "c": "Whitethroat",
        "sy": ["Sylvia communis"],  # the UK list knows the old name
        "l": _WARBLER,
    },
    {"k": "UKJ1", "r": "species", "s": "Jasminum humile", "c": "Italian Jasmine", "l": _PLANT},
]


def pack_record(key, scientific, common, synonyms=(), lineage=_WARBLER):
    return {
        "k": key,
        "r": "species",
        "s": scientific,
        "c": common,
        "sy": list(synonyms),
        "l": lineage,
    }


# GBIF's names: the old genus
LESSER = pack_record("gbif:1", "Sylvia curruca", "Grey Whitethroat", ["Curruca curruca curruca"])
COMMON = pack_record("gbif:2", "Sylvia communis", "Common Whitethroat")
# A synonym that changes the species' own word: once misapplied, not the same plant
JASMINE = pack_record("gbif:3", "Chrysojasminum fruticans", None, ["Jasminum humile"], _PLANT)
FRANCE = [LESSER, COMMON, JASMINE]


def with_uk_extra(ctx):
    with ctx.db.transaction() as conn:
        taxa_repo.install_catalogue(conn, MINI_CATALOGUE + UK_EXTRA)


def install_france(ctx, records=FRANCE):
    ctx.catalogue.install_pack(list(records), region="fr", name="France", version="test")


def ids_named(ctx, *names):
    with ctx.db.connection() as conn:
        marks = ",".join("?" * len(names))
        return [
            r[0]
            for r in conn.execute(f"SELECT id FROM taxon WHERE scientific_name IN ({marks})", names)
        ]


def keys_of(ctx, taxon_id):
    with ctx.db.connection() as conn:
        return {
            k for (k,) in conn.execute("SELECT key FROM taxon_key WHERE taxon_id = ?", (taxon_id,))
        }


def test_a_pack_links_to_the_uk_species_by_its_synonyms(ctx):
    with_uk_extra(ctx)
    install_france(ctx)
    (lesser,) = ids_named(ctx, "Curruca curruca", "Sylvia curruca")  # one, not two
    assert keys_of(ctx, lesser) == {"UKW1", "gbif:1"}  # via the pack's 'Curruca curruca curruca'
    (common,) = ids_named(ctx, "Curruca communis", "Sylvia communis")
    assert keys_of(ctx, common) == {"UKW2", "gbif:2"}  # via the UK list's 'Sylvia communis'
    # and the old name still finds it
    ctx.catalogue.set_region("uk")
    assert [m.taxon.display_name for m in ctx.catalogue.search("Sylvia curruca")] == [
        "Lesser Whitethroat"
    ]


def test_a_synonym_that_changes_the_species_word_isnt_trusted(ctx):
    with_uk_extra(ctx)
    install_france(ctx)
    assert len(ids_named(ctx, "Jasminum humile", "Chrysojasminum fruticans")) == 2


def test_two_pack_species_wanting_one_uk_species_are_both_left_alone(ctx):
    with_uk_extra(ctx)
    twin = pack_record("gbif:9", "Sylvia currucoides", "A twin", ["Curruca curruca"])
    install_france(ctx, [LESSER, twin])
    assert len(ids_named(ctx, "Curruca curruca", "Sylvia curruca", "Sylvia currucoides")) == 3


def test_copies_1_6_0_added_are_merged_once(ctx, monkeypatch):
    """1.6.0 linked by name only: its packs could add a second Lesser Whitethroat, with
    your sightings, notes and saved filters on it. 1.6.1 merges them on its first start."""
    with_uk_extra(ctx)
    with monkeypatch.context() as m:
        m.setattr(taxa_repo, "link_renamed", lambda conn: 0)  # as 1.6.0 did
        install_france(ctx)
    uk_id, copy_id = sorted(ids_named(ctx, "Curruca curruca", "Sylvia curruca"))
    sighting = ctx.sightings.save(SightingDraft(copy_id, TODAY)).sighting
    ctx.sightings.save(SightingDraft(uk_id, TODAY))
    ctx.species_notes.set(uk_id, "Rattling song")
    ctx.species_notes.set(copy_id, "In the hedge")
    ctx.saved_filters.save("Whitethroats", SightingFilter(taxon_ids=frozenset({copy_id})))

    assert ctx.catalogue.link_renamed_once() == 2  # both whitethroats
    assert ids_named(ctx, "Curruca curruca", "Sylvia curruca") == [uk_id]
    assert ctx.sightings.get(sighting.id).taxon_id == uk_id
    assert ctx.species_notes.get(uk_id) == "Rattling song\n\nIn the hedge"
    (saved,) = ctx.saved_filters.all()
    assert saved.filter.taxon_ids == {uk_id}
    assert keys_of(ctx, uk_id) == {"UKW1", "gbif:1"}  # updating the pack finds it again
    assert len(ids_named(ctx, "Jasminum humile", "Chrysojasminum fruticans")) == 2
    assert ctx.catalogue.link_renamed_once() == 0  # only once
    install_france(ctx)  # reinstalling adds no copy back
    assert ids_named(ctx, "Curruca curruca", "Sylvia curruca") == [uk_id]
