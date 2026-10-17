from datetime import date

import pytest

from helpers import TODAY, taxon_id
from wildlife.domain.codes import Evidence, Identification
from wildlife.domain.errors import ConflictError, NotFoundError, ValidationError
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import PlaceDraft, SightingDraft


def add(ctx, sci="Erithacus rubecula", day=TODAY, **kw):
    return ctx.sightings.save(
        SightingDraft(taxon_id=taxon_id(ctx, sci), observed_date=day, **kw)
    ).sighting


def test_minimal_sighting_is_saved_with_defaults(ctx):
    s = add(ctx)
    assert s.display_name == "Robin" and s.count == 1 and s.evidence is Evidence.SEEN
    assert s.observed_time is None and not s.has_location and len(s.uuid) == 36


def test_invalid_sighting_reports_fields(ctx):
    with pytest.raises(ValidationError) as err:
        ctx.sightings.save(SightingDraft(taxon_id=None, observed_date=date(2027, 1, 1)))
    assert set(err.value.fields) == {"species", "date"}


def test_unknown_species_or_place_is_rejected(ctx):
    with pytest.raises(ValidationError) as err:
        ctx.sightings.save(SightingDraft(taxon_id=999_999, observed_date=TODAY, place_id=42))
    assert set(err.value.fields) == {"species", "place"}


def test_first_sighting_is_a_lifer_and_later_ones_are_not(ctx):
    first = ctx.sightings.save(
        SightingDraft(taxon_id=taxon_id(ctx, "Erithacus rubecula"), observed_date=TODAY)
    )
    second = ctx.sightings.save(
        SightingDraft(taxon_id=taxon_id(ctx, "Erithacus rubecula"), observed_date=TODAY)
    )
    assert first.is_lifer and not second.is_lifer
    gull = ctx.sightings.save(SightingDraft(taxon_id=taxon_id(ctx, "Larus"), observed_date=TODAY))
    assert not gull.is_lifer  # "Gull" (a genus) never counts as a species


def test_undo_new_sighting_removes_it(ctx):
    result = ctx.sightings.save(
        SightingDraft(taxon_id=taxon_id(ctx, "Vulpes vulpes"), observed_date=TODAY)
    )
    result.undo.run()
    with pytest.raises(NotFoundError):
        ctx.sightings.get(result.sighting.id)


def test_edit_and_undo_edit(ctx):
    s = add(ctx, count=2)
    edited = ctx.sightings.save(
        SightingDraft(**{**_fields(s.to_draft()), "count": 5, "notes": "Feeding"})
    )
    assert (edited.sighting.count, edited.sighting.notes) == (5, "Feeding") and not edited.created
    edited.undo.run()
    assert (ctx.sightings.get(s.id).count, ctx.sightings.get(s.id).notes) == (2, None)


def test_delete_goes_to_recycle_bin_and_can_be_undone(ctx):
    a, b = add(ctx), add(ctx, "Vulpes vulpes")
    undo = ctx.sightings.delete([a.id, b.id])
    assert ctx.sightings.totals(SightingFilter())[0] == 0
    assert len(ctx.sightings.recycle_bin()) == 2
    undo.run()
    assert ctx.sightings.totals(SightingFilter())[0] == 2


def test_purge_only_removes_old_deleted_sightings(ctx):
    a = add(ctx)
    ctx.sightings.delete([a.id])
    assert ctx.sightings.purge_recycle_bin(30) == 0  # deleted just now: kept
    assert ctx.sightings.purge_recycle_bin(0) == 1  # "empty the bin"
    assert ctx.sightings.recycle_bin() == []


def test_change_species_in_bulk_with_undo(ctx):
    ids = [add(ctx, "Sympetrum striolatum").id for _ in range(3)]
    undo = ctx.sightings.change_species(ids, taxon_id(ctx, "Aglais io"))
    assert {ctx.sightings.get(i).display_name for i in ids} == {"Peacock"}
    undo.run()
    assert {ctx.sightings.get(i).display_name for i in ids} == {"Common Darter"}


def test_totals_follow_list_rules(ctx):
    add(ctx)
    add(ctx)  # same species twice
    add(ctx, "Motacilla alba yarrellii")  # subspecies counts as Motacilla alba
    add(ctx, "Motacilla alba")
    add(ctx, "Larus")  # genus: not counted
    add(ctx, "Vulpes vulpes", is_not_wild=True)  # captive: not counted
    add(ctx, "Aglais io", identification=Identification.POSSIBLE)  # not confident: not counted
    sightings, species = ctx.sightings.totals(SightingFilter())
    assert (sightings, species) == (7, 2)


def test_filters(ctx):
    garden = ctx.places.save(PlaceDraft("Garden", 51.75, -0.34, radius_m=50))
    add(ctx, place_id=garden.id, notes="On the bird table")
    add(ctx, "Sympetrum striolatum", day=date(2025, 8, 1), latitude=52.0, longitude=0.5)
    add(ctx, "Vulpes vulpes", day=date(2024, 1, 5))
    count = lambda **kw: ctx.sightings.totals(SightingFilter(**kw))[0]  # noqa: E731
    assert count() == 3
    assert count(category_ids=frozenset({1})) == 1  # birds
    assert count(date_from=date(2025, 1, 1)) == 2
    assert count(date_from=date(2025, 1, 1), date_to=date(2025, 12, 31)) == 1
    assert count(place_ids=frozenset({garden.id})) == 1
    assert count(needs_location=True) == 1  # the fox
    assert count(text="darter") == 1  # species name
    assert count(text="redbreast") == 1  # alternative name
    assert count(text="bird table") == 1  # notes
    assert count(text="gard") == 1  # place name
    assert count(taxon_ids=frozenset({taxon_id(ctx, "Motacilla alba")})) == 0


def test_species_filter_includes_subspecies(ctx):
    add(ctx, "Motacilla alba yarrellii")
    flt = SightingFilter(taxon_ids=frozenset({taxon_id(ctx, "Motacilla alba")}))
    assert ctx.sightings.totals(flt)[0] == 1


def test_place_location_is_used_when_sighting_has_none(ctx):
    garden = ctx.places.save(PlaceDraft("Garden", 51.75, -0.34, radius_m=50))
    s = add(ctx, place_id=garden.id)
    assert (s.eff_latitude, s.eff_longitude, s.eff_uncertainty_m) == (51.75, -0.34, 50)


def test_paging_and_sorting(ctx):
    for day in (date(2026, 1, 1), date(2026, 3, 1), date(2026, 2, 1)):
        add(ctx, day=day)
    newest_first = [s.observed_date.month for s in ctx.sightings.page(SightingFilter())]
    assert newest_first == [3, 2, 1]
    oldest_first = [
        s.observed_date.month for s in ctx.sightings.page(SightingFilter(), descending=False)
    ]
    assert oldest_first == [1, 2, 3]
    assert len(ctx.sightings.page(SightingFilter(), offset=1, limit=1)) == 1


def test_default_place_remembers_the_last_one(ctx):
    assert ctx.sightings.default_place() is None
    hide = ctx.places.save(PlaceDraft("Hide", 52.0, 0.5))
    add(ctx, place_id=hide.id)
    assert ctx.sightings.default_place() == hide.id


def test_places_in_use_cannot_be_deleted_but_can_be_archived(ctx):
    garden = ctx.places.save(PlaceDraft("Garden", 51.75, -0.34))
    add(ctx, place_id=garden.id)
    with pytest.raises(ConflictError):
        ctx.places.delete(garden.id)
    ctx.places.archive(garden.id)
    assert ctx.places.all() == [] and len(ctx.places.all(include_archived=True)) == 1


def test_a_place_an_outing_uses_cannot_be_deleted_and_says_why(ctx):
    """It used to fail with a raw database error ("Something went wrong")."""
    from wildlife.domain.models import OutingDraft

    garden = ctx.places.save(PlaceDraft("Garden", 51.75, -0.34))
    ctx.outings.save(OutingDraft(date(2026, 5, 3), place_id=garden.id))
    with pytest.raises(ConflictError) as refused:
        ctx.places.delete(garden.id)
    assert "1 outing" in refused.value.user_message


def test_why_a_place_is_in_use_mentions_the_recycle_bin(ctx):
    garden = ctx.places.save(PlaceDraft("Garden", 51.75, -0.34))
    kept, binned = add(ctx, place_id=garden.id), add(ctx, place_id=garden.id)
    ctx.sightings.delete([binned.id])
    with pytest.raises(ConflictError) as refused:
        ctx.places.delete(garden.id)
    assert "2 sightings (1 in the recycle bin)" in refused.value.user_message
    ctx.sightings.delete([kept.id])
    with pytest.raises(ConflictError) as refused:
        ctx.places.delete(garden.id)
    assert "2 sightings in the recycle bin" in refused.value.user_message


def test_an_unused_place_can_be_deleted(ctx):
    pond = ctx.places.save(PlaceDraft("Pond", 51.75, -0.34))
    ctx.places.delete(pond.id)
    assert ctx.places.all() == []


def test_nearest_place_within_radius(ctx):
    garden = ctx.places.save(PlaceDraft("Garden", 51.75, -0.34, radius_m=100))
    assert ctx.places.nearest(51.7502, -0.3401).id == garden.id
    assert ctx.places.nearest(51.80, -0.34) is None


def test_events_announce_changes(ctx):
    seen = []
    ctx.events.subscribe(lambda e: seen.append(e.topic))
    s = add(ctx)
    ctx.sightings.delete([s.id])
    assert seen == ["sightings", "sightings"]


def _fields(draft):
    return {f: getattr(draft, f) for f in draft.__dataclass_fields__}


def test_bulk_place_date_and_outing_with_undo(ctx):
    from wildlife.domain.models import OutingDraft

    garden = ctx.places.save(PlaceDraft("Garden", 51.4, 0.1))
    a = add(ctx, latitude=51.5, longitude=-0.1, uncertainty_m=10)
    b = add(ctx, "Vulpes vulpes")
    ids = [a.id, b.id]
    undo = ctx.sightings.change_place(ids, garden.id)
    assert {ctx.sightings.get(i).place_id for i in ids} == {garden.id}
    assert ctx.sightings.get(a.id).latitude == 51.5  # its own spot is kept unless asked
    undo.run()
    assert ctx.sightings.get(a.id).place_id is None
    ctx.sightings.change_place(ids, garden.id, clear_positions=True)
    assert ctx.sightings.get(a.id).latitude is None
    assert ctx.sightings.get(a.id).eff_latitude == 51.4  # now the place's centre

    undo = ctx.sightings.change_date(ids, date(2026, 5, 1))
    assert {ctx.sightings.get(i).observed_date for i in ids} == {date(2026, 5, 1)}
    undo.run()
    assert ctx.sightings.get(b.id).observed_date == TODAY
    with pytest.raises(ValidationError):
        ctx.sightings.change_date(ids, date(2030, 1, 1))

    outing, _ = ctx.outings.save(OutingDraft(TODAY))
    undo = ctx.sightings.set_outing(ids, outing.id)
    assert ctx.sightings.get(a.id).outing_id == outing.id
    undo.run()
    assert ctx.sightings.get(a.id).outing_id is None


def test_search_treats_wildcard_characters_as_plain_text(ctx):
    """In SQL, _ and % match anything. Searching for them must find only themselves."""
    add(ctx, notes="50% sure")
    add(ctx, notes="seen near the old_bridge")
    add(ctx, notes="nothing special")
    assert ctx.sightings.totals(SightingFilter(text="_"))[0] == 1
    assert ctx.sightings.totals(SightingFilter(text="%"))[0] == 1
    wood = ctx.places.save(PlaceDraft("Abc Wood", 51.75, -0.34))
    add(ctx, place_id=wood.id)
    assert ctx.sightings.totals(SightingFilter(text="A_c"))[0] == 0  # not "Abc Wood"
    assert ctx.sightings.totals(SightingFilter(text="Abc"))[0] == 1


def test_bulk_changes_to_tens_of_thousands_of_sightings(ctx):
    """SQLite takes at most 32,766 values in one query; bigger selections go in parts."""
    robin = add(ctx)
    ids = [robin.id, *range(1_000_000, 1_040_000)]  # one real sighting among 40,000 ids
    ctx.sightings.change_date(ids, date(2026, 5, 1)).run()
    ctx.sightings.change_species(ids, taxon_id(ctx, "Motacilla alba")).run()
    ctx.sightings.delete(ids).run()
    assert ctx.sightings.get(robin.id).taxon_id == taxon_id(ctx, "Erithacus rubecula")
