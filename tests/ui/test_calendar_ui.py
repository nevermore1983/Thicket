"""UI tests for the calendar, the day panel and outings."""

from datetime import date

from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import QMessageBox

from helpers import TODAY, taxon_id
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import OutingDraft, SightingDraft
from wildlife.ui.components.rows import RowButton
from wildlife.ui.panels.day_panel import DayPanel
from wildlife.ui.panels.outing_detail import OutingDetail
from wildlife.ui.panels.outing_editor import OutingEditor
from wildlife.ui.panels.sighting_detail import SightingDetail
from wildlife.ui.panels.sighting_editor import SightingEditor

ROBIN, FOX = "Erithacus rubecula", "Vulpes vulpes"


def add(ctx, sci, day, **kw):
    return ctx.sightings.save(
        SightingDraft(taxon_id=taxon_id(ctx, sci), observed_date=day, **kw)
    ).sighting


def calendar(window, view="month", day=TODAY):
    window.go("calendar")
    page = window.calendar_page
    page.go_to(day, view)
    return page


def press(page, key) -> None:
    """Fire the page's shortcut for `key` (real key presses need an active window)."""
    for shortcut in page.findChildren(QShortcut):
        if shortcut.key() == QKeySequence(key):
            shortcut.activated.emit()
            return
    raise AssertionError(f"no shortcut for {key}")


def test_month_view_shows_this_month(window):
    page = calendar(window)
    assert page.title.text() == "October 2026"
    assert page.intro.isVisible()  # nothing recorded yet
    assert page.summary.text() == "No sightings this month"


def test_days_are_summarised_and_firsts_starred(window):
    add(window.ctx, ROBIN, date(2026, 10, 3))
    add(window.ctx, ROBIN, date(2026, 10, 3))
    add(window.ctx, FOX, date(2026, 10, 3))
    page = calendar(window)
    s = page.month_view.days[date(2026, 10, 3)]
    assert (s.sightings, s.species, s.lifers) == (3, 2, 2)
    assert not page.intro.isVisible()
    assert page.summary.text() == "3 sightings on 1 day this month"


def test_clicking_a_day_opens_its_list(window, qtbot):
    add(window.ctx, ROBIN, date(2026, 10, 3), observed_time="08:15")
    page = calendar(window)
    view = page.month_view
    cell = view._cell_rect((date(2026, 10, 3) - view.first_cell()).days).center().toPoint()
    assert view.day_at(cell) == date(2026, 10, 3)
    qtbot.mouseClick(view, Qt.MouseButton.LeftButton, pos=cell)
    panel = window.panel.current()
    assert isinstance(panel, DayPanel) and panel.day == date(2026, 10, 3)
    assert page.selected == date(2026, 10, 3)
    assert view.day_at(QPoint(5, 5)) is None  # the weekday header row


def test_day_panel_opens_a_sighting_and_comes_back(window):
    s = add(window.ctx, ROBIN, TODAY)
    window.open_day(TODAY, SightingFilter())
    panel = window.panel.current()
    panel.open_sighting.emit(s.id)
    assert isinstance(window.panel.current(), SightingDetail)
    window.panel.back()
    assert window.panel.current() is panel


def test_add_on_a_day_prefills_the_date(window):
    page = calendar(window)
    page.select(date(2026, 9, 20))
    press(page, Qt.Key.Key_N)
    editor = window.panel.current()
    assert isinstance(editor, SightingEditor)
    assert editor.date.date().toPython() == date(2026, 9, 20)


def test_keyboard_moves_and_switches_views(window):
    page = calendar(window)
    press(page, Qt.Key.Key_PageDown)
    assert page.title.text() == "November 2026"
    press(page, Qt.Key.Key_T)
    assert page.title.text() == "October 2026"
    press(page, Qt.Key.Key_Y)
    assert page.view == "year" and page.title.text() == "2026"
    press(page, Qt.Key.Key_PageUp)
    assert page.title.text() == "2025"
    press(page, Qt.Key.Key_W)
    assert page.view == "week"
    press(page, Qt.Key.Key_D)
    assert page.view == "day"
    press(page, Qt.Key.Key_M)
    assert page.view == "month"


def test_zooming_keeps_the_chosen_day(window):
    page = calendar(window)
    page.select(date(2026, 10, 20))
    page.set_view("week")
    assert page.title.text() == "19 – 25 Oct 2026"
    page.set_view("day")
    assert page.title.text() == "Tuesday 20 October 2026"


def test_year_view_opens_a_month(window):
    add(window.ctx, ROBIN, date(2026, 3, 14))
    page = calendar(window, "year")
    assert page.year_view.month_totals()[2] == 1
    page.year_view.month_clicked.emit(date(2026, 3, 1))
    assert page.view == "month" and page.title.text() == "March 2026"


def test_empty_year_offers_a_jump_to_the_first_sighting(window):
    add(window.ctx, ROBIN, date(2024, 6, 1))
    page = calendar(window, "year", date(2020, 1, 1))
    assert page.year_empty.isVisible()
    assert page.summary.text() == "No sightings in 2020"


def test_filter_applies_to_the_calendar(window):
    add(window.ctx, ROBIN, date(2026, 10, 3))
    add(window.ctx, FOX, date(2026, 10, 4))
    page = calendar(window)
    page.set_filter(SightingFilter(category_ids=frozenset({2}), date_from=date(2000, 1, 1)))
    assert page.filter.date_from is None  # the calendar's own period is the date filter
    assert list(page.month_view.days) == [date(2026, 10, 4)]


def test_week_and_day_views_list_sightings(window):
    add(window.ctx, ROBIN, TODAY, observed_time="09:00")
    add(window.ctx, FOX, TODAY)
    page = calendar(window, "week")
    assert page.summary.text() == "2 sightings on 1 day this week"
    page.set_view("day")
    assert page.summary.text() == "2 sightings · 2 species"


def test_new_sightings_appear_without_reopening(window, qtbot):
    page = calendar(window)
    add(window.ctx, ROBIN, TODAY)
    qtbot.waitUntil(lambda: TODAY in page.month_view.days, timeout=2000)  # straight after


def test_typing_a_month_in_search_opens_the_calendar(window, qtbot):
    window.focus_search()
    qtbot.keyClicks(window.search, "May 2025")
    qtbot.waitUntil(lambda: window.search_popup.list.count() > 0, timeout=2000)
    assert window.search_popup.list.currentItem().text().startswith("Open May 2025")
    window.search_popup._choose()
    assert window.current_page() == "calendar"
    assert window.calendar_page.title.text() == "May 2025"


# ---- outings -------------------------------------------------------------------
def test_start_add_and_end_an_outing(window):
    ctx = window.ctx
    ctx.outings._clock = lambda: "08:00"
    window.start_outing()
    live = ctx.outings.in_progress()
    assert live and isinstance(window.panel.current(), OutingDetail)
    assert window.outing_chip.isVisible() and "since 08:00" in window.outing_chip.text()

    window.panel.current().add_requested.emit(live)
    editor = window.panel.current()
    assert editor.f_outing.isVisibleTo(editor) and editor.outing.currentData() == live.id
    editor.picker.set_taxon(ctx.catalogue.get(taxon_id(ctx, ROBIN)))
    result = editor.save()
    assert result.sighting.outing_id == live.id
    assert "1 seen" in window.outing_chip.text()

    window.open_outing(live.id)
    ctx.outings._clock = lambda: "10:30"
    window.panel.current().end_requested.emit(live.id)
    assert ctx.outings.get(live.id).end_time == "10:30"
    assert not window.outing_chip.isVisible()


def test_new_sighting_joins_the_outing_that_covers_its_time(window):
    ctx = window.ctx
    morning, _ = ctx.outings.save(
        OutingDraft(outing_date=TODAY, start_time="07:00", end_time="10:00")
    )
    window.add_sighting(SightingDraft(taxon_id=None, observed_date=TODAY, observed_time="08:30"))
    editor = window.panel.current()
    assert editor.outing.currentData() == morning.id
    editor.time.setText("12:00")
    editor.time.editingFinished.emit()
    assert editor.outing.currentData() is None  # 12:00 is after the outing
    editor.outing.setCurrentIndex(editor.outing.findData(morning.id))
    editor.outing.activated.emit(editor.outing.currentIndex())  # chosen by hand: now it sticks
    editor.time.setText("13:00")
    editor.time.editingFinished.emit()
    assert editor.outing.currentData() == morning.id


def test_outing_field_hidden_when_the_day_has_none(window):
    window.add_sighting()
    editor = window.panel.current()
    assert not editor.f_outing.isVisibleTo(editor)


def test_outing_editor_reports_problems(window):
    window.new_outing(TODAY)
    editor = window.panel.current()
    assert isinstance(editor, OutingEditor)
    editor.start.setText("10:00")
    editor.end.setText("9:00")
    editor.temperature.setText("warm")
    editor.save()
    assert editor.f_end.note.property("role") == "error"
    assert editor.f_temperature.note.property("role") == "error"
    assert window.ctx.outings.count() == 0
    editor.temperature.setText("12")
    editor.end.setText("11:15")
    editor.save()
    saved = window.ctx.outings.page()[0]
    assert (saved.end_time, saved.temperature_c) == ("11:15", 12.0)
    assert isinstance(window.panel.current(), OutingDetail)


def test_outing_editor_asks_before_discarding(window, monkeypatch):
    window.new_outing(TODAY)
    editor = window.panel.current()
    editor.title_edit.setText("Dawn walk")
    editor.title_edit.textEdited.emit("Dawn walk")
    asked = []
    monkeypatch.setattr(
        QMessageBox,
        "question",
        lambda *a, **k: asked.append(True) or QMessageBox.StandardButton.Cancel,
    )
    window.panel.close_panel()
    assert asked and window.panel.isVisible()


def test_delete_outing_keeps_sightings_and_undo_restores(window):
    ctx = window.ctx
    outing, _ = ctx.outings.save(OutingDraft(outing_date=TODAY))
    s = add(ctx, ROBIN, TODAY, outing_id=outing.id)
    window.open_outing(outing.id)
    window.panel.current().delete_requested.emit(outing.id)
    assert ctx.outings.count() == 0 and ctx.sightings.get(s.id).outing_id is None
    window._undo()
    assert ctx.outings.count() == 1 and ctx.sightings.get(s.id).outing_id == outing.id


def test_outings_tab_lists_outings(window):
    window.ctx.outings.save(OutingDraft(outing_date=TODAY, title="Dawn walk"))
    window.go("sightings")
    window.sightings_page.show_tab("outings")
    rows = window.sightings_page.outings._rows
    titles = [rows.itemAt(i).widget().accessibleName() for i in range(rows.count() - 1)]
    assert titles and titles[0].startswith("Dawn walk")
    window.sightings_page.set_filter(SightingFilter())  # going back to the list switches tab
    assert window.sightings_page.tab_stack.currentIndex() == 0


def test_day_view_shows_the_days_outings(window):
    window.ctx.outings.save(OutingDraft(outing_date=TODAY, title="Dawn walk", weather="sunny"))
    page = calendar(window, "day")
    rows = [r.accessibleName() for r in page.day_view.findChildren(RowButton)]
    assert any(name.startswith("Dawn walk") and "Sunny" in name for name in rows)


def test_outings_tab_shows_more_on_request(window):
    from datetime import timedelta

    for i in range(105):
        window.ctx.outings.save(OutingDraft(outing_date=TODAY - timedelta(days=i)))
    window.go("sightings")
    window.sightings_page.show_tab("outings")
    tab = window.sightings_page.outings
    assert len(tab.findChildren(RowButton)) == 100 and tab._more.isVisibleTo(tab)
    assert tab.footer.text() == "105 outings · showing the latest 100"
    tab._more.click()
    assert tab._shown == 105 and not tab._more.isVisibleTo(tab)


def test_arrow_keys_choose_a_day_and_enter_opens_it(window):
    page = calendar(window)  # October 2026, today the 11th
    press(page, Qt.Key.Key_Right)
    assert page.selected == date(2026, 10, 12)
    press(page, Qt.Key.Key_Down)
    press(page, Qt.Key.Key_Down)
    press(page, Qt.Key.Key_Down)
    assert page.selected == date(2026, 11, 2) and page.title.text() == "November 2026"
    press(page, Qt.Key.Key_Return)
    assert window.panel.current() is not None  # the day's list opened
