"""Calendar: your sightings by date, in year, month, week and day views."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtGui import QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.domain.dates import (
    MONTHS_LONG,
    DateQuery,
    add_months,
    add_years,
    fmt_date,
    week_label,
    week_start,
)
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import Sighting
from wildlife.ui.calendar.day_view import DayView, species_count
from wildlife.ui.calendar.month_view import MonthView
from wildlife.ui.calendar.week_view import WeekView
from wildlife.ui.calendar.year_view import RampLegend, YearView
from wildlife.ui.components.common import Callout, EmptyState, Segmented, button, clear_layout
from wildlife.ui.components.filter_bar import FilterBar
from wildlife.ui.components.visuals import plural
from wildlife.ui.theme.icons import icon
from wildlife.ui.theme.manager import ThemeManager

VIEWS = ("year", "month", "week", "day")
MAX_LISTED = 3000  # sightings loaded for one week or day
NARROW = 820  # page width below which the title moves onto its own line


def _scroll(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setObjectName("PageScroll")
    area.setWidget(widget)
    return area


class CalendarPage(QWidget):
    open_sighting = Signal(int)
    add_on = Signal(object)  # date
    open_day = Signal(object, object)  # date, SightingFilter
    open_outing = Signal(int)
    new_outing = Signal(object)  # date
    show_map = Signal(object)  # SightingFilter: the day on the map

    def __init__(self, ctx: AppContext, theme: ThemeManager) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.setFocusPolicy(Qt.FocusPolicy.ClickFocus)  # so the calendar keys work in every view
        self.ctx, self.theme = ctx, theme
        stored = QSettings().value("calendar/view", "month")
        self.view = stored if stored in VIEWS else "month"
        self.anchor = ctx.sightings._today()
        self.selected: date | None = None
        self.filter = SightingFilter()

        v = QVBoxLayout(self)
        v.setContentsMargins(28, 22, 28, 12)
        v.setSpacing(12)
        self._title_row = QHBoxLayout()  # holds the title when the page is narrow
        v.addLayout(self._title_row)
        self._bar = self._toolbar()
        v.addLayout(self._bar)
        row = QHBoxLayout()
        self.filter_bar = FilterBar(ctx, theme, show_date=False)
        self.filter_bar.changed.connect(self._filter_changed)
        row.addWidget(self.filter_bar, 1)
        self.summary = QLabel()
        self.summary.setProperty("role", "muted")
        row.addWidget(self.summary)
        v.addLayout(row)
        self.intro = Callout(
            theme,
            "info",
            "Your sightings will appear here by date. Click any day to see it, "
            "or press <b>N</b> to add a sighting on the selected day.",
        )
        v.addWidget(self.intro)

        self.stack = QStackedWidget()
        self.month_view = MonthView(ctx, theme)
        self.month_view.day_clicked.connect(self.select)
        self.month_view.day_activated.connect(lambda d: self.go_to(d, "day"))
        self.year_view = YearView(theme)
        self.year_view.day_clicked.connect(self.select)
        self.year_view.day_activated.connect(lambda d: self.go_to(d, "day"))
        self.year_view.month_clicked.connect(lambda d: self.go_to(d, "month"))
        self.week_view = WeekView(ctx, theme)
        self.week_view.open_sighting.connect(self.open_sighting)
        self.week_view.day_clicked.connect(self.select)
        self.week_view.add_on.connect(self.add_on)
        self.day_view = DayView(ctx, theme)
        self.day_view.open_sighting.connect(self.open_sighting)
        self.day_view.add_on.connect(self.add_on)
        self.day_view.open_outing.connect(self.open_outing)
        self.day_view.new_outing.connect(self.new_outing)
        self.day_view.show_map.connect(
            lambda d: self.show_map.emit(self.filter.with_(date_from=d, date_to=d))
        )

        year_box = QWidget()
        yb = QVBoxLayout(year_box)
        yb.setContentsMargins(0, 0, 0, 0)
        yb.setSpacing(12)
        self.year_empty = QWidget()
        self._year_empty_layout = QVBoxLayout(self.year_empty)
        self._year_empty_layout.setContentsMargins(0, 0, 0, 0)
        yb.addWidget(self.year_empty)
        yb.addWidget(self.year_view)
        self.legend = RampLegend(theme)
        yb.addWidget(self.legend)
        yb.addStretch(1)
        week_box = QWidget()
        wb = QVBoxLayout(week_box)
        wb.setContentsMargins(0, 0, 0, 0)
        wb.addWidget(self.week_view)
        wb.addStretch(1)
        self._pages = {
            "month": self.stack.addWidget(_scroll(self.month_view)),
            "year": self.stack.addWidget(_scroll(year_box)),
            "week": self.stack.addWidget(_scroll(week_box)),
            "day": self.stack.addWidget(_scroll(self.day_view)),
        }
        v.addWidget(self.stack, 1)
        hint = QLabel(
            "Keyboard: ← → previous / next · T today · Y M W D change view · "
            "N add a sighting on the selected day"
        )
        hint.setProperty("role", "caption")
        hint.setWordWrap(True)
        v.addWidget(hint)
        self._install_shortcuts()
        self.refresh()

    # ---- building -----------------------------------------------------------------
    def _toolbar(self) -> QHBoxLayout:
        h = QHBoxLayout()
        h.setSpacing(6)
        self.prev_button = QPushButton()
        self.next_button = QPushButton()
        for b, tip, step in (
            (self.prev_button, "Previous (←)", -1),
            (self.next_button, "Next (→)", 1),
        ):
            b.setFixedWidth(36)
            b.setToolTip(tip)
            b.setAccessibleName(tip.split(" ")[0])
            b.setCursor(Qt.CursorShape.PointingHandCursor)
            b.clicked.connect(lambda _=False, s=step: self.move(s))
            h.addWidget(b)
        today = button("Today", "secondary", None, self.theme, self.go_today)
        today.setToolTip("Go to today (T)")
        h.addWidget(today)
        self.title = QLabel()
        self.title.setObjectName("CalTitle")
        h.addWidget(self.title)
        h.addStretch(1)
        self.switcher = Segmented([(k, k.capitalize()) for k in VIEWS], self.view)
        for k in VIEWS:
            self.switcher.button_for(k).setToolTip(f"{k.capitalize()} view ({k[0].upper()})")
        self.switcher.changed.connect(self.set_view)
        h.addWidget(self.switcher)
        self._paint_icons()
        self.theme.changed.connect(self._paint_icons)
        return h

    def _paint_icons(self) -> None:
        t = self.theme.tokens
        self.prev_button.setIcon(icon("chevron-left", t.text_2, 18))
        self.next_button.setIcon(icon("chevron-right", t.text_2, 18))

    def _install_shortcuts(self) -> None:
        keys = {
            Qt.Key.Key_Left: lambda: self.move(-1),
            Qt.Key.Key_Right: lambda: self.move(1),
            Qt.Key.Key_T: self.go_today,
            Qt.Key.Key_Y: lambda: self.set_view("year"),
            Qt.Key.Key_M: lambda: self.set_view("month"),
            Qt.Key.Key_W: lambda: self.set_view("week"),
            Qt.Key.Key_D: lambda: self.set_view("day"),
            Qt.Key.Key_N: lambda: self.add_on.emit(self.selected or self._default_day()),
        }
        for key, action in keys.items():
            QShortcut(
                QKeySequence(key),
                self,
                activated=action,
                context=Qt.ShortcutContext.WidgetWithChildrenShortcut,
            )

    # ---- navigation -----------------------------------------------------------------
    def set_view(self, view: str) -> None:
        if view not in VIEWS:
            return
        if self.selected and view != self.view:
            self.anchor = self.selected  # zoom in or out around the chosen day
        self.view = view
        QSettings().setValue("calendar/view", view)
        self.refresh()

    def go_to(self, day: date, view: str | None = None) -> None:
        self.anchor = day
        self.selected = day
        if view:
            self.view = view
            QSettings().setValue("calendar/view", view)
        self.refresh()

    def go_today(self) -> None:
        self.go_to(self.ctx.sightings._today())

    def move(self, step: int) -> None:
        a = self.anchor
        self.anchor = {
            "year": lambda: add_years(a, step),
            "month": lambda: add_months(a, step),
            "week": lambda: a + timedelta(days=7 * step),
            "day": lambda: a + timedelta(days=step),
        }[self.view]()
        if self.view == "day":
            self.selected = self.anchor
        self.refresh()

    def jump(self, q: DateQuery) -> None:
        """Open a date typed into search in the matching view: a day, a month or a year."""
        self.anchor, self.view = q.day, q.kind
        self.selected = q.day if q.kind == "day" else None
        QSettings().setValue("calendar/view", q.kind)
        self.refresh()

    def select(self, day: date) -> None:
        """Highlight a day and ask for its list in the side panel."""
        self.selected = day
        self.month_view.selected = self.year_view.selected = day
        self.month_view.update()
        self.year_view.update()
        if self.view == "week":
            self.refresh()
        self.open_day.emit(day, self.filter)

    def _default_day(self) -> date:
        today = self.ctx.sightings._today()
        return today if self.view != "day" else self.anchor

    def _filter_changed(self, flt: SightingFilter) -> None:
        self.filter = flt
        self.refresh()

    def set_filter(self, flt: SightingFilter) -> None:
        self.filter_bar.set_filter(flt.with_(date_from=None, date_to=None))

    # ---- drawing -------------------------------------------------------------------------
    def refresh(self) -> None:
        today = self.ctx.sightings._today()
        self.intro.setVisible(self.ctx.sightings.totals(SightingFilter())[0] == 0)
        self.switcher.set_current(self.view)
        self.stack.setCurrentIndex(self._pages[self.view])
        getattr(self, f"_show_{self.view}")(today)

    def _set_summary(self, sightings: int, days: int, period: str) -> None:
        if sightings:
            text = f"{plural(sightings, 'sighting')} on {plural(days, 'day')} {period}"
        else:
            text = f"No sightings {period}" + (
                " match the filters" if not self.filter.is_empty else ""
            )
        self.summary.setText(text)

    def _show_month(self, today: date) -> None:
        a = self.anchor
        self.title.setText(f"{MONTHS_LONG[a.month - 1]} {a.year}")
        self.month_view.month = a.replace(day=1)
        start, end = self.month_view.range()
        days = self.ctx.calendar.days(self.filter, start, end)
        self.month_view.set_data(a, days, today, self.selected)
        in_month = [s for d, s in days.items() if d.month == a.month]
        self._set_summary(sum(s.sightings for s in in_month), len(in_month), "this month")

    def _show_year(self, today: date) -> None:
        year = self.anchor.year
        self.title.setText(str(year))
        days = self.ctx.calendar.days(self.filter, date(year, 1, 1), date(year, 12, 31))
        self.year_view.set_data(year, days, today, self.selected)
        self._set_summary(sum(s.sightings for s in days.values()), len(days), f"in {year}")
        # An empty year gets an explanation (and a way to find your records) above the grid
        clear_layout(self._year_empty_layout)
        self.year_empty.setVisible(not days)
        if not days:
            first = self.ctx.stats.dashboard().first_date
            actions = []
            if first and self.filter.is_empty:
                actions.append(
                    button(
                        f"Jump to your first sighting ({fmt_date(first, 'medium')})",
                        "secondary",
                        None,
                        self.theme,
                        lambda: self.go_to(first, "month"),
                    )
                )
            self._year_empty_layout.addWidget(
                EmptyState(
                    self.theme,
                    "calendar",
                    f"No sightings in {year}",
                    "Nothing matches the current filters in this year."
                    if not self.filter.is_empty
                    else "Nothing was recorded this year.",
                    actions,
                )
            )

    def _listed(self, start: date, end: date) -> list[Sighting]:
        flt = self.filter.with_(date_from=start, date_to=end)
        return self.ctx.sightings.page(flt, "date", False, 0, MAX_LISTED)

    def _show_week(self, today: date) -> None:
        start = week_start(self.anchor)
        end = start + timedelta(days=6)
        self.title.setText(week_label(self.anchor))
        items = self._listed(start, end)
        by_day: dict[date, list[Sighting]] = {}
        for s in items:
            by_day.setdefault(s.observed_date, []).append(s)
        firsts = self.ctx.calendar.firsts(self.filter, start, end)
        self.week_view.set_data(start, by_day, firsts, today, self.selected)
        self._set_summary(len(items), len(by_day), "this week")

    def _show_day(self, today: date) -> None:
        day = self.anchor
        self.title.setText(fmt_date(day, "full"))
        items = self._listed(day, day)
        firsts = self.ctx.calendar.firsts(self.filter, day, day)
        self.day_view.set_data(
            day, items, firsts, self.ctx.outings.on_date(day), not self.filter.is_empty
        )
        if items:
            self.summary.setText(
                f"{plural(len(items), 'sighting')} · "
                f"{plural(species_count(items), 'species', 'species')}"
            )
        else:
            self.summary.setText("")

    def resizeEvent(self, event) -> None:
        # With the side panel open there isn't room for title and buttons on one line
        narrow = self.width() < NARROW
        in_bar = self._bar.indexOf(self.title) >= 0
        if narrow and in_bar:
            self._bar.removeWidget(self.title)
            self._title_row.addWidget(self.title)
        elif not narrow and not in_bar:
            self._title_row.removeWidget(self.title)
            self._bar.insertWidget(3, self.title)  # after ‹ › Today
        super().resizeEvent(event)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        # Give the calendar keyboard focus so ← → T Y M W D N work straight away
        target = {"month": self.month_view, "year": self.year_view}.get(self.view, self)
        target.setFocus(Qt.FocusReason.OtherFocusReason)
