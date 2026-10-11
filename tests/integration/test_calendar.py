from datetime import date

from helpers import taxon_id
from wildlife.domain.codes import Identification
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import SightingDraft

ALL = SightingFilter()
ROBIN, FOX, DARTER = "Erithacus rubecula", "Vulpes vulpes", "Sympetrum striolatum"


def add(ctx, sci, day, time=None, **kw):
    return ctx.sightings.save(
        SightingDraft(taxon_id=taxon_id(ctx, sci), observed_date=day, observed_time=time, **kw)
    ).sighting


def test_days_without_sightings_are_missing(ctx):
    add(ctx, ROBIN, date(2026, 5, 3))
    days = ctx.calendar.days(ALL, date(2026, 5, 1), date(2026, 5, 31))
    assert list(days) == [date(2026, 5, 3)]
    assert ctx.calendar.days(ALL, date(2026, 6, 1), date(2026, 6, 30)) == {}


def test_day_summary_counts_and_categories(ctx):
    day = date(2026, 5, 3)
    add(ctx, ROBIN, day)
    add(ctx, ROBIN, day)
    add(ctx, "Motacilla alba yarrellii", day)  # subspecies of Pied Wagtail
    add(ctx, "Motacilla alba", day)
    add(ctx, DARTER, day)
    add(ctx, "Larus", day)  # genus only
    add(ctx, "Larus", day)
    s = ctx.calendar.days(ALL, day, day)[day]
    assert s.sightings == 7
    assert s.species == 4  # Robin, Pied Wagtail, Common Darter, Gull
    bird, dragonfly = 1, 5
    assert s.category_ids == (bird, dragonfly)  # most-seen first


def test_firsts_are_marked_once_and_ignore_the_filter(ctx):
    add(ctx, ROBIN, date(2025, 4, 1))  # Robin's lifer day
    first_fox = add(ctx, FOX, date(2026, 3, 2), "09:00")
    add(ctx, FOX, date(2026, 3, 2), "07:00")  # earlier that day: this is the real first
    robin_2026 = add(ctx, ROBIN, date(2026, 3, 2))  # first Robin of 2026, not a lifer
    add(ctx, ROBIN, date(2026, 3, 9))
    march = ctx.calendar.days(ALL, date(2026, 3, 1), date(2026, 3, 31))
    assert (march[date(2026, 3, 2)].lifers, march[date(2026, 3, 2)].year_firsts) == (1, 2)
    assert march[date(2026, 3, 2)].headline == "Red Fox"  # a lifer wins the headline
    assert (march[date(2026, 3, 9)].lifers, march[date(2026, 3, 9)].year_firsts) == (0, 0)

    firsts = ctx.calendar.firsts(ALL, date(2026, 3, 2), date(2026, 3, 2))
    assert len(firsts.lifers) == 1 and first_fox.id not in firsts.lifers
    assert firsts.mark(robin_2026.id) == "year"

    # Filtering to birds doesn't make the 2026 Robin a lifer
    birds = SightingFilter(category_ids=frozenset({1}))
    day = ctx.calendar.days(birds, date(2026, 3, 2), date(2026, 3, 2))[date(2026, 3, 2)]
    assert (day.sightings, day.lifers, day.year_firsts) == (1, 0, 1)


def test_uncountable_records_are_never_firsts(ctx):
    day = date(2026, 6, 1)
    add(ctx, FOX, day, identification=Identification.POSSIBLE)
    add(ctx, ROBIN, day, is_not_wild=True)
    add(ctx, "Larus", day)
    s = ctx.calendar.days(ALL, day, day)[day]
    assert (s.lifers, s.year_firsts) == (0, 0)
    assert s.headline == "Red Fox"  # all tied on one sighting: the earliest added wins


def test_headline_is_most_seen_when_nothing_is_new(ctx):
    add(ctx, ROBIN, date(2026, 1, 1))
    add(ctx, FOX, date(2026, 1, 1))
    day = date(2026, 2, 1)
    add(ctx, ROBIN, day)
    add(ctx, FOX, day)
    add(ctx, FOX, day)
    assert ctx.calendar.days(ALL, day, day)[day].headline == "Red Fox"


def test_filter_and_its_dates_are_respected(ctx):
    add(ctx, ROBIN, date(2026, 5, 3))
    add(ctx, FOX, date(2026, 5, 3))
    add(ctx, FOX, date(2026, 5, 20))
    foxes = SightingFilter(taxon_ids=frozenset({taxon_id(ctx, FOX)}))
    days = ctx.calendar.days(foxes, date(2026, 5, 1), date(2026, 5, 31))
    assert {d: s.sightings for d, s in days.items()} == {date(2026, 5, 3): 1, date(2026, 5, 20): 1}
    late_may = SightingFilter(date_from=date(2026, 5, 10))
    assert list(ctx.calendar.days(late_may, date(2026, 5, 1), date(2026, 5, 31))) == [
        date(2026, 5, 20)
    ]
    assert ctx.calendar.days(late_may, date(2026, 4, 1), date(2026, 4, 30)) == {}


def test_deleted_sightings_disappear(ctx):
    s = add(ctx, ROBIN, date(2026, 5, 3))
    ctx.sightings.delete([s.id])
    assert ctx.calendar.days(ALL, date(2026, 5, 1), date(2026, 5, 31)) == {}


def test_probable_ids_count_when_the_setting_says_so(ctx):
    day = date(2026, 6, 1)
    add(ctx, FOX, day, identification=Identification.PROBABLE)
    assert ctx.calendar.days(ALL, day, day)[day].lifers == 0
    ctx.settings.update(count_probable_ids=True)
    assert ctx.calendar.days(ALL, day, day)[day].lifers == 1
