"""Adding a species of your own (SpeciesCatalogue.add_species), and the feedback links."""

from urllib.parse import parse_qs, urlsplit

import pytest

from helpers import US_PACK, taxon_id
from wildlife import __version__
from wildlife.data.repositories import taxa as taxa_repo
from wildlife.domain.errors import ValidationError
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import SightingDraft
from wildlife.feedback import form_url, windows_version


def test_your_own_species_is_found_counted_and_grouped(ctx):
    robin = ctx.catalogue.get(taxon_id(ctx, "Erithacus rubecula"))
    own = ctx.catalogue.add_species("erithacus  akahige", "Japanese Robin")
    assert own.scientific_name == "Erithacus akahige" and own.is_custom
    assert own.category_id == robin.category_id  # a bird, like its genus
    assert own.species_id == own.id  # counts as a species in your lists
    for text in ("Japanese Robin", "akahige"):
        assert [m.taxon.id for m in ctx.catalogue.search(text)] == [own.id]
    ctx.sightings.save(SightingDraft(taxon_id=own.id, observed_date=ctx.sightings._today()))
    assert ctx.sightings.totals(SightingFilter(text="Japanese"))[0] == 1
    with ctx.db.connection() as conn:
        tree = conn.execute("SELECT tax_class FROM taxon WHERE id = ?", (own.id,)).fetchone()[0]
    assert tree == "Aves"


@pytest.mark.parametrize(
    ("scientific", "problem"),
    [
        ("", "needed"),
        ("Robin", "genus and species"),
        ("Larus sp.", "genus and species"),  # a genus, not a species
        ("Erithacus rubecula", "in the list already"),  # say so, don't make a second one
        # An older name of a species in the list: the same species, not a new one
        ("Argentina anserina", "as Silverweed (Potentilla anserina)"),
    ],
)
def test_a_species_needs_a_new_scientific_name(ctx, scientific, problem):
    with pytest.raises(ValidationError) as refused:
        ctx.catalogue.add_species(scientific, None)
    assert problem in refused.value.fields["scientific_name"]


@pytest.mark.parametrize(
    "scientific",
    ["Larus michahellis atlantis", "Dactylorhiza x grandis", "Anas platyrhynchos × Anas acuta"],
)
def test_subspecies_and_hybrids_are_accepted(ctx, scientific):
    assert ctx.catalogue.add_species(scientific, None).scientific_name == scientific


def test_a_group_with_no_relative_goes_in_other(ctx):
    own = ctx.catalogue.add_species("Novagenus inventus", None)
    assert ctx.catalogue.category(own.category_id).is_fallback


def test_a_pack_that_adds_it_later_becomes_the_same_species(ctx):
    own = ctx.catalogue.add_species("Cardinalis cardinalis", "Redbird")
    with ctx.db.transaction() as conn:
        taxa_repo.install_pack(conn, US_PACK, "us-ca", "California", "gbif", "test")
    found = {m.taxon.id for m in ctx.catalogue.search("Northern Cardinal")}
    assert found == {own.id}  # linked, never a second cardinal


def test_feedback_forms_carry_the_versions_and_nothing_else():
    problem = parse_qs(urlsplit(form_url("problem")).query)
    assert problem["template"] == ["problem.yml"] and problem["version"] == [__version__]
    assert problem["windows"] == [windows_version()]
    idea = parse_qs(urlsplit(form_url("idea")).query)
    assert set(idea) == {"template", "version"}
    assert form_url("idea").startswith("https://github.com/nevermore1983/Thicket/issues/new?")


def test_your_own_species_can_be_corrected(ctx):
    """B1: a typo in a species you added isn't permanent."""
    own = ctx.catalogue.add_species("Erithacus akahigi", "Japanese Robn")
    fixed = ctx.catalogue.rename_species(
        own.id, "Erithacus akahige", "Japanese Robin", own.category_id
    )
    assert (fixed.scientific_name, fixed.common_name) == ("Erithacus akahige", "Japanese Robin")
    assert [m.taxon.id for m in ctx.catalogue.search("Japanese Robin")] == [own.id]
    assert ctx.catalogue.search("Robn") == []  # the old names are gone from search
    with pytest.raises(ValidationError) as clash:
        ctx.catalogue.rename_species(own.id, "Erithacus rubecula", None, own.category_id)
    assert "in the list already" in clash.value.fields["scientific_name"]


def test_your_own_species_can_be_removed_only_when_unused(ctx):
    from wildlife.domain.errors import ConflictError

    unused = ctx.catalogue.add_species("Novagenus inventus", None)
    used = ctx.catalogue.add_species("Erithacus akahige", "Japanese Robin")
    sighting = ctx.sightings.save(
        SightingDraft(taxon_id=used.id, observed_date=ctx.sightings._today())
    ).sighting
    ctx.sightings.delete([sighting.id])  # in the recycle bin: still uses it
    with pytest.raises(ConflictError, match="1 sighting uses"):
        ctx.catalogue.remove_species(used.id)
    ctx.catalogue.remove_species(unused.id)
    assert [t.id for t, _ in ctx.catalogue.own_species()] == [used.id]
    with pytest.raises(ConflictError):  # never a species from a list
        ctx.catalogue.remove_species(taxon_id(ctx, "Erithacus rubecula"))


def test_one_a_pack_took_over_isnt_listed_as_yours(ctx):
    ctx.catalogue.add_species("Cardinalis cardinalis", "Redbird")
    with ctx.db.transaction() as conn:
        taxa_repo.install_pack(conn, US_PACK, "us-ca", "California", "gbif", "test")
    assert ctx.catalogue.own_species() == []
