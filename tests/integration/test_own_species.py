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
        ("Erithacus rubecula", "in the list already"),  # say so, don't make a second one
    ],
)
def test_a_species_needs_a_new_scientific_name(ctx, scientific, problem):
    with pytest.raises(ValidationError) as refused:
        ctx.catalogue.add_species(scientific, None)
    assert problem in refused.value.fields["scientific_name"]


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
