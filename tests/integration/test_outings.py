from dataclasses import replace
from datetime import date

import pytest

from helpers import TODAY, taxon_id
from wildlife.domain.codes import Weather, Wind
from wildlife.domain.errors import NotFoundError, ValidationError
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import OutingDraft, PlaceDraft, SightingDraft

SAT = date(2026, 10, 10)


def add_sighting(ctx, sci="Erithacus rubecula", day=SAT, **kw):
    return ctx.sightings.save(
        SightingDraft(taxon_id=taxon_id(ctx, sci), observed_date=day, **kw)
    ).sighting


def add_outing(ctx, day=SAT, **kw):
    outing, _ = ctx.outings.save(OutingDraft(outing_date=day, **kw))
    return outing


def test_outing_is_saved_with_weather_and_place(ctx):
    place = ctx.places.save(PlaceDraft("Rainham Marshes", 51.5, 0.2))
    o = add_outing(
        ctx,
        place_id=place.id,
        start_time="07:30",
        end_time="11:00",
        weather=Weather.SUNNY,
        wind=Wind.LIGHT,
        temperature_c=12.5,
        is_complete_list=True,
    )
    assert o.display_title == "Rainham Marshes · Sat 10 Oct 2026"
    assert (o.weather, o.wind, o.temperature_c, o.is_complete_list) == (
        Weather.SUNNY,
        Wind.LIGHT,
        12.5,
        True,
    )
    assert len(o.uuid) == 36 and ctx.outings.count() == 1


def test_weather_given_as_plain_strings_is_stored(ctx):
    """Combo boxes hand back plain strings, not enums."""
    o = add_outing(ctx, weather="overcast", wind="calm", visibility="poor")
    assert o.weather is Weather.OVERCAST and o.visibility.label == "Poor"


def test_invalid_outing_reports_fields(ctx):
    with pytest.raises(ValidationError) as err:
        ctx.outings.save(OutingDraft(outing_date=date(2027, 1, 1), start_time="10:00", place_id=99))
    assert set(err.value.fields) == {"date", "place"}


def test_counts_only_live_sightings(ctx):
    o = add_outing(ctx)
    a = add_sighting(ctx, outing_id=o.id)
    add_sighting(ctx, outing_id=o.id)
    add_sighting(ctx, "Vulpes vulpes", outing_id=o.id)
    ctx.sightings.delete([a.id])
    o = ctx.outings.get(o.id)
    assert (o.sightings, o.species) == (2, 2)
    assert ctx.sightings.totals(SightingFilter(outing_id=o.id))[0] == 2


def test_sighting_with_missing_outing_is_rejected(ctx):
    with pytest.raises(ValidationError) as err:
        add_sighting(ctx, outing_id=123)
    assert set(err.value.fields) == {"outing"}


def test_edit_and_undo_edit(ctx):
    o = add_outing(ctx, title="Dawn walk")
    edited, undo = ctx.outings.save(replace(o.to_draft(), title="Dusk walk"))
    assert edited.title == "Dusk walk"
    undo.run()
    assert ctx.outings.get(o.id).title == "Dawn walk"


def test_undo_add_removes_outing_and_ungroups(ctx):
    o, undo = ctx.outings.save(OutingDraft(outing_date=SAT))
    s = add_sighting(ctx, outing_id=o.id)
    undo.run()
    assert ctx.outings.count() == 0
    assert ctx.sightings.get(s.id).outing_id is None


def test_delete_keeps_sightings_and_undo_regroups(ctx):
    o = add_outing(ctx)
    s1 = add_sighting(ctx, outing_id=o.id)
    s2 = add_sighting(ctx, outing_id=o.id)
    other = add_sighting(ctx)
    undo = ctx.outings.delete(o.id)
    assert ctx.outings.count() == 0
    with pytest.raises(NotFoundError):
        ctx.outings.get(o.id)
    assert ctx.sightings.get(s1.id).outing_id is None
    undo.run()
    assert {ctx.sightings.get(i).outing_id for i in (s1.id, s2.id)} == {o.id}
    assert ctx.sightings.get(other.id).outing_id is None
    assert ctx.outings.get(o.id).sightings == 2


def test_purge_removes_old_deleted_outings(ctx):
    o = add_outing(ctx)
    ctx.outings.delete(o.id)
    assert ctx.outings.purge_deleted(older_than_days=1) == 0
    assert ctx.outings.purge_deleted(older_than_days=0) == 1


def test_start_and_end_outing(ctx):
    ctx.outings._clock = lambda: "08:15"
    o = ctx.outings.start(title="Morning")
    assert o.outing_date == TODAY and o.start_time == "08:15" and o.in_progress
    assert ctx.outings.in_progress().id == o.id
    ctx.outings._clock = lambda: "10:40"
    ended = ctx.outings.end(o.id)
    assert ended.end_time == "10:40" and not ended.in_progress
    assert ctx.outings.in_progress() is None


def test_outing_left_running_from_yesterday_ends_at_midnight(ctx):
    o = add_outing(ctx, start_time="18:00")
    assert ctx.outings.in_progress() is None  # only today's count as "in progress"
    assert ctx.outings.end(o.id).end_time == "23:59"


def test_default_outing_only_when_unambiguous(ctx):
    morning = add_outing(ctx, start_time="07:00", end_time="10:00")
    assert ctx.outings.default_for(SAT, "08:30").id == morning.id
    assert ctx.outings.default_for(SAT, None).id == morning.id
    assert ctx.outings.default_for(SAT, "12:00") is None
    assert ctx.outings.default_for(TODAY, "08:30") is None
    add_outing(ctx, start_time="08:00")  # overlaps the first one
    assert ctx.outings.default_for(SAT, "08:30") is None
    assert ctx.outings.default_for(SAT, "07:30").id == morning.id


def test_listing_and_moving_sightings(ctx):
    a = add_outing(ctx, day=date(2026, 9, 1))
    b = add_outing(ctx, day=SAT, start_time="06:00")
    c = add_outing(ctx, day=SAT, start_time="14:00")
    assert [o.id for o in ctx.outings.page()] == [c.id, b.id, a.id]
    assert [o.id for o in ctx.outings.on_date(SAT)] == [b.id, c.id]
    assert [o.id for o in ctx.outings.between(date(2026, 9, 1), date(2026, 9, 30))] == [a.id]
    s = add_sighting(ctx)
    ctx.outings.add_sightings([s.id], b.id)
    assert ctx.sightings.get(s.id).outing_id == b.id
    ctx.outings.add_sightings([s.id], None)
    assert ctx.sightings.get(s.id).outing_id is None


def test_events_are_published(ctx):
    seen = []
    ctx.events.subscribe(lambda e: seen.append(e.topic))
    o = add_outing(ctx)
    ctx.outings.delete(o.id)
    assert seen == ["outings", "outings", "sightings"]
