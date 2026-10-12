"""Statistics numbers, checked against small hand-made data."""

from datetime import date

from helpers import TODAY, taxon_id
from wildlife.domain.codes import Identification
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import OutingDraft, PlaceDraft, SightingDraft
from wildlife.services.statistics import Period, cumulative

ALL = SightingFilter()
ROBIN, FOX, DARTER = "Erithacus rubecula", "Vulpes vulpes", "Sympetrum striolatum"
WAGTAIL, YARRELLII = "Motacilla alba", "Motacilla alba yarrellii"


def add(ctx, sci, day, time=None, **kw):
    return ctx.sightings.save(
        SightingDraft(taxon_id=taxon_id(ctx, sci), observed_date=day, observed_time=time, **kw)
    ).sighting


def seed(ctx):
    rainham = ctx.places.save(PlaceDraft("Rainham", 51.4955, 0.1975))
    garden = ctx.places.save(PlaceDraft("Garden", 51.75, -0.34))
    outing, _ = ctx.outings.save(OutingDraft(outing_date=date(2026, 5, 3)))
    add(ctx, ROBIN, date(2025, 4, 1), "08:15", place_id=garden.id)  # Robin's lifer (last year)
    add(ctx, ROBIN, date(2026, 5, 3), "07:10", place_id=rainham.id, count=3, outing_id=outing.id)
    add(ctx, FOX, date(2026, 5, 3), "07:40", place_id=rainham.id, outing_id=outing.id)  # lifer
    add(ctx, DARTER, date(2026, 8, 20), "14:05", place_id=rainham.id)  # lifer
    add(
        ctx, YARRELLII, date(2026, 8, 20), "14:30", place_id=garden.id, count=12
    )  # lifer (as Pied Wagtail)
    add(ctx, WAGTAIL, date(2026, 8, 21), place_id=garden.id)
    add(ctx, FOX, date(2026, 9, 1), identification=Identification.POSSIBLE)  # not countable
    return rainham, garden


def test_summary_for_this_year(ctx):
    seed(ctx)
    s = ctx.statistics.statistics(ALL, Period.this_year(TODAY)).summary
    assert (s.sightings, s.species, s.days, s.outings, s.places) == (6, 4, 4, 1, 2)
    assert s.lifers == 3  # Fox, Darter, Pied Wagtail (Robin's lifer was in 2025)
    # 3 May and 20 Aug both have 2 sightings: a tie goes to the more recent day
    assert (s.busiest_day, s.busiest_count) == (date(2026, 8, 20), 2)


def test_all_time_and_last_year(ctx):
    seed(ctx)
    everything = ctx.statistics.statistics(ALL, Period.all_time())
    assert (everything.summary.sightings, everything.summary.lifers) == (7, 4)
    last = ctx.statistics.statistics(ALL, Period.last_year(TODAY))
    assert last.summary.sightings == 1 and last.period.label == "2025"


def test_categories_seasons_and_hours(ctx):
    seed(ctx)
    st = ctx.statistics.statistics(ALL, Period.this_year(TODAY))
    birds = next(c for c in st.categories if c.category_id == 1)
    assert (birds.sightings, birds.species) == (3, 2)  # Robin, wagtail x2 -> 2 species
    assert st.seasons[(1, 8)] == 2 and st.seasons[(2, 5)] == 1
    assert st.hours[7] == 2 and st.hours[14] == 2 and sum(st.hours) == 4  # untimed not counted


def test_top_species_by_sightings_and_individuals(ctx):
    seed(ctx)
    st = ctx.statistics.statistics(ALL, Period.this_year(TODAY))
    by_sightings = {r.name: r.sightings for r in st.top_by_sightings}
    assert by_sightings["Pied Wagtail"] == 2 and by_sightings["Red Fox"] == 2  # subspecies merged
    assert st.top_by_individuals[0].name == "Pied Wagtail"
    assert st.top_by_individuals[0].individuals == 13


def test_places_rank_by_species_with_visits(ctx):
    seed(ctx)
    st = ctx.statistics.statistics(ALL, Period.this_year(TODAY))
    rows = [(p.name, p.species, p.visits, p.sightings) for p in st.places]
    assert rows == [("Rainham", 3, 2, 3), ("Garden", 1, 2, 2)]


def test_firsts_are_decided_from_all_records(ctx):
    seed(ctx)
    st = ctx.statistics.statistics(ALL, Period.this_year(TODAY))
    kinds = {(r.name, r.kind) for r in st.firsts}
    assert kinds == {
        ("Red Fox", "lifer"),
        ("Common Darter", "lifer"),
        ("Pied Wagtail", "lifer"),
        ("Robin", "year"),  # first of 2026, but seen in 2025
    }
    assert st.firsts[0].day == date(2026, 8, 20)  # newest first
    birds = ctx.statistics.statistics(
        SightingFilter(category_ids=frozenset({1})), Period.this_year(TODAY)
    )
    assert {r.name for r in birds.firsts} == {"Pied Wagtail", "Robin"}
    assert birds.summary.lifers == 1  # filtering doesn't make Robin a lifer


def test_growth_compares_with_last_year_on_a_shared_axis(ctx):
    seed(ctx)
    growth = ctx.statistics.statistics(ALL, Period.this_year(TODAY)).growth
    assert growth.by_day_of_year and growth.origin == date(2026, 1, 1)
    this, last = growth.curves
    assert (this.label, last.label) == ("2026", "2025")
    assert this.points == [(122, 2), (231, 4)]  # 3 May: Robin + Fox; 20 Aug: Darter + Wagtail
    assert last.points == [(90, 1)]  # 1 Apr 2025


def test_all_time_growth_starts_at_the_first_record(ctx):
    seed(ctx)
    growth = ctx.statistics.statistics(ALL, Period.all_time()).growth
    assert not growth.by_day_of_year and growth.origin == date(2025, 4, 1)
    assert growth.curves[0].points[-1][1] == 4


def test_species_per_month_for_two_years(ctx):
    seed(ctx)
    months = ctx.statistics.statistics(ALL, Period.this_year(TODAY)).months
    assert months[2026][4] == 2 and months[2026][7] == 2 and sum(months[2026]) == 4
    assert months[2025][3] == 1


def test_month_and_hour_filters(ctx):
    seed(ctx)
    may = ctx.sightings.totals(SightingFilter(months=frozenset({5})))[0]
    seven = ctx.sightings.totals(SightingFilter(hours=frozenset({7})))[0]
    assert (may, seven) == (2, 2)


def test_probable_ids_count_when_set(ctx):
    seed(ctx)
    add(ctx, "Turdus migratorius", date(2026, 9, 2), identification=Identification.PROBABLE)
    before = ctx.statistics.statistics(ALL, Period.this_year(TODAY)).summary.species
    ctx.settings.update(count_probable_ids=True)
    assert ctx.statistics.statistics(ALL, Period.this_year(TODAY)).summary.species == before + 1


def test_year_list_and_dashboard_helpers(ctx):
    seed(ctx)
    year = ctx.statistics.year_list(ALL, 2026)
    assert [r.name for r in year][:2] == ["Robin", "Red Fox"]  # in the order first seen
    assert [r.name for r in ctx.statistics.recent_firsts(2)] == ["Pied Wagtail", "Common Darter"]
    top = ctx.statistics.top_species(ALL, 3)  # three species tie on 2 sightings: A to Z
    assert [(r.name, r.sightings) for r in top] == [
        ("Pied Wagtail", 2),
        ("Red Fox", 2),
        ("Robin", 2),
    ]
    assert ctx.statistics.day_counts(date(2026, 5, 1), date(2026, 5, 31)) == {date(2026, 5, 3): 2}


def test_cumulative_steps():
    origin = date(2026, 1, 1)
    days = [date(2026, 1, 5), date(2026, 1, 5), date(2026, 3, 1)]
    assert cumulative(days, origin) == [(4, 2), (59, 3)]
    assert cumulative([], origin) == []


def test_periods():
    assert Period.this_year(TODAY).start == date(2026, 1, 1)
    assert Period.custom(date(2026, 5, 1), date(2026, 4, 1)).start == date(2026, 4, 1)
    assert Period.custom(date(2026, 4, 1), date(2026, 5, 1)).label == "1 Apr 2026 – 1 May 2026"
    assert Period.all_time().applied(SightingFilter(date_from=date(2020, 1, 1))).date_from is None


def test_statistics_of_an_empty_library(ctx):
    st = ctx.statistics.statistics(ALL, Period.this_year(TODAY))
    assert st.summary.sightings == 0 and st.summary.busiest_day is None
    assert st.growth.curves[0].points == [] and st.firsts == [] and st.places == []
