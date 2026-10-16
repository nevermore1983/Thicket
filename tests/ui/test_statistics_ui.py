"""UI tests for the Statistics page, the dashboard additions, year lists and species profiles."""

from datetime import date

from helpers import TODAY, taxon_id
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import PlaceDraft, SightingDraft
from wildlife.services.statistics import Period
from wildlife.ui.panels.species_profile import SpeciesProfile

ROBIN, FOX = "Erithacus rubecula", "Vulpes vulpes"


def add(ctx, sci, day, time=None, **kw):
    return ctx.sightings.save(
        SightingDraft(taxon_id=taxon_id(ctx, sci), observed_date=day, observed_time=time, **kw)
    ).sighting


def seed(ctx):
    place = ctx.places.save(PlaceDraft("Rainham", 51.4955, 0.1975))
    add(ctx, ROBIN, date(2025, 4, 1), "08:15", place_id=place.id)
    add(ctx, ROBIN, date(2026, 5, 3), "07:10", place_id=place.id, count=3)
    add(ctx, FOX, date(2026, 5, 3), "07:40", place_id=place.id)
    return place


def open_statistics(window, qtbot, period=None):
    window.go("statistics")
    page = window.statistics_page
    page.data = None
    page.set_period(period or Period.this_year(TODAY))
    qtbot.waitUntil(lambda: page.data is not None, timeout=10_000)
    return page


def test_statistics_page_shows_the_numbers(window, qtbot):
    seed(window.ctx)
    page = open_statistics(window, qtbot)
    assert page.content.isVisibleTo(page) and not page.empty.isVisibleTo(page)
    assert [b.label for b in page.top.bars] == ["Red Fox", "Robin"]
    assert page.hours.series[0].values[7] == 2
    assert page.seasons.rows[0].label == "Bird"
    assert page.growth.lines[0].label == "2026" and page.growth.lines[1].label == "2025"
    assert page.period_label.text() == "2026"


def test_empty_library_shows_an_explanation(window, qtbot):
    page = open_statistics(window, qtbot)
    assert page.empty.isVisibleTo(page) and not page.content.isVisibleTo(page)


def test_clicks_open_the_matching_sightings(window, qtbot):
    place = seed(window.ctx)
    page = open_statistics(window, qtbot)
    page.groups.clicked.emit(1)
    flt = window.sightings_page.model.filter
    assert window.current_page() == "sightings"
    assert flt.category_ids == frozenset({1}) and flt.date_from == date(2026, 1, 1)
    assert window.sightings_page.model.total == 1  # Robin in 2026
    window.go("statistics")
    page.seasons.clicked.emit((2, 5))
    assert window.sightings_page.model.filter.months == frozenset({5})
    window.go("statistics")
    page.hours.clicked.emit(7)
    assert window.sightings_page.model.total == 2
    window.go("statistics")
    page.months.clicked.emit((2026, 5))
    flt = window.sightings_page.model.filter
    assert (flt.date_from, flt.date_to) == (date(2026, 5, 1), date(2026, 5, 31))
    assert place.id  # places table is checked below


def test_month_and_hour_chips_show_on_the_sightings_page(window, qtbot):
    window.show_sightings(SightingFilter(months=frozenset({5}), hours=frozenset({7})))
    chips = [
        b.text() for b in window.sightings_page.filter_bar.findChildren(type(window.add_button))
    ]
    assert "In May  ✕" in chips and "07:00–08:00  ✕" in chips


def test_periods_and_top_measure(window, qtbot):
    seed(window.ctx)
    page = open_statistics(window, qtbot, Period.all_time())
    assert (
        page.data.summary.sightings == 3 and page.period_label.text() == "Since your first sighting"
    )
    page.top_switch.changed.emit("individuals")
    assert page.top.bars[0].label == "Robin" and page.top.bars[0].value == 4
    page.data = None
    page.set_period(Period.last_year(TODAY))
    qtbot.waitUntil(lambda: page.data is not None, timeout=10_000)
    assert page.data.summary.sightings == 1


def test_table_versions_of_charts(window, qtbot):
    seed(window.ctx)
    page = open_statistics(window, qtbot)
    page.top_card.flip()
    table = page.top_card.stack.currentWidget()
    assert table.rowCount() == 2 and table.item(0, 0).text() == "Red Fox"
    assert page.top_card.toggle.text() == "Show chart"
    page.top_card.flip()
    assert page.top_card.stack.currentWidget() is page.top


def test_firsts_list_opens_on_the_list_with_entries(window, qtbot):
    seed(window.ctx)
    page = open_statistics(window, qtbot)
    assert page.firsts_kind == "lifer"  # the Fox is a lifer in 2026
    page.firsts_switch.changed.emit("year")
    assert page.firsts_kind == "year"


def test_custom_period(window, qtbot, monkeypatch):
    seed(window.ctx)
    page = open_statistics(window, qtbot)
    monkeypatch.setattr(page, "_ask_dates", lambda: (date(2026, 5, 1), date(2026, 5, 31)))
    page.data = None
    page._period_chosen("custom")
    qtbot.waitUntil(lambda: page.data is not None, timeout=10_000)
    assert (
        page.data.summary.sightings == 2 and page.period_label.text() == "1 May 2026 – 31 May 2026"
    )


def test_dashboard_has_activity_new_and_top(window, qtbot):
    seed(window.ctx)
    window.dashboard.refresh()
    from wildlife.ui.components.activity import ActivityStrip
    from wildlife.ui.components.charts import BarChart

    strip = window.dashboard.findChildren(ActivityStrip)[-1]  # newest; older ones await deletion
    assert strip.counts == {date(2026, 5, 3): 2}
    days = []
    window.dashboard.open_day.connect(days.append)
    strip.day_clicked.emit(date(2026, 5, 3))
    assert window.current_page() == "calendar" and window.calendar_page.view == "day"
    top = window.dashboard.findChildren(BarChart)[-1]
    assert {b.label for b in top.bars} == {"Robin", "Red Fox"}


def test_year_lists_and_species_profile(window, qtbot):
    seed(window.ctx)
    window.go("species")
    page = window.species_page
    page.refresh()
    assert [page.which.itemText(i) for i in range(page.which.count())] == [
        "Life list",
        "2026 list",
        "2025 list",
    ]
    page._choose(2026)
    names = [page.table.item(r, 0).text() for r in range(page.table.rowCount())]
    assert names == [
        "Red Fox  ★",
        "Robin",
    ]  # the Fox is a lifer in 2026; Robin was first seen in 2025
    page.table.selectRow(0)
    profile = window.panel.current()
    assert isinstance(profile, SpeciesProfile) and profile.taxon_id == taxon_id(window.ctx, FOX)
    page._open(page.table.model().index(1, 0))
    assert window.sightings_page.model.filter.date_from == date(2026, 1, 1)


def test_species_profile_buttons(window, qtbot):
    seed(window.ctx)
    robin = taxon_id(window.ctx, ROBIN)
    window.open_species(robin)
    profile = window.panel.current()
    p = window.ctx.stats.species_profile(robin)
    assert (p.sightings, p.best_count, p.by_month[4], p.by_year) == (2, 3, 1, {2025: 1, 2026: 1})
    profile.show_sightings.emit(SightingFilter(taxon_ids=frozenset({robin})))
    assert window.current_page() == "sightings" and window.sightings_page.model.total == 2


def test_lists_are_a_to_z(window, qtbot):
    seed(window.ctx)
    add(window.ctx, "Larus argentatus", date(2026, 6, 1))
    window.go("species")
    page = window.species_page
    page.refresh()
    names = [page.table.item(r, 0).text() for r in range(page.table.rowCount())]
    assert names == sorted(names, key=str.lower)


def test_species_notes_in_the_profile(window, qtbot):
    seed(window.ctx)
    robin = taxon_id(window.ctx, ROBIN)
    window.open_species(robin)
    profile = window.panel.current()
    profile.notes.setPlainText("Nests in the ivy")
    qtbot.waitUntil(lambda: window.ctx.species_notes.get(robin) == "Nests in the ivy", timeout=3000)
    profile.notes.setPlainText("Nests in the ivy by the shed")
    window.panel.close_panel()  # closing saves straight away
    assert window.ctx.species_notes.get(robin) == "Nests in the ivy by the shed"


def test_big_lists_fill_quickly(qtbot):
    """Refilling a visible 1,500-row table once took over 100 seconds: sorting and
    size-to-contents columns redid their work after every cell."""
    import time as _time

    from PySide6.QtWidgets import QHeaderView, QTableWidgetItem

    from wildlife.ui.pages.list_pages import _filling, _table

    table = _table(["Species", "Category", "Sightings", "First seen", "Last seen"])
    for col in (1, 2, 3, 4):
        table.horizontalHeader().setSectionResizeMode(col, QHeaderView.ResizeMode.ResizeToContents)
    qtbot.addWidget(table)
    table.resize(900, 600)
    table.show()
    started = _time.perf_counter()
    with _filling(table):
        table.setRowCount(1500)
        for r in range(1500):
            for c in range(5):
                table.setItem(r, c, QTableWidgetItem(f"species {1500 - r:04d} / {c}"))
    assert _time.perf_counter() - started < 5
    assert table.item(0, 0).text().startswith("species 0001")  # still sorted A to Z
    assert table.horizontalHeader().sectionResizeMode(1) == QHeaderView.ResizeMode.ResizeToContents
