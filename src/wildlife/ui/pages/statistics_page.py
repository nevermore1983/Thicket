"""Statistics: every chart answers one question; click a bar, cell or row to see those sightings."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QDate, QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDateEdit,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QGraphicsOpacityEffect,
    QGridLayout,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.domain.dates import MONTHS, MONTHS_LONG, add_months, fmt_date, month_end
from wildlife.domain.filters import SightingFilter
from wildlife.services.statistics import Period, Statistics
from wildlife.ui.components.charts import (
    Bar,
    BarChart,
    ColumnChart,
    HeatRow,
    HeatTable,
    Line,
    Series,
    StepLineChart,
)
from wildlife.ui.components.common import EmptyState, Segmented, button, clear_layout
from wildlife.ui.components.filter_bar import FilterBar
from wildlife.ui.components.rows import StatTile
from wildlife.ui.components.visuals import plural, swatch
from wildlife.ui.theme.manager import ThemeManager
from wildlife.ui.workers import run_in_background

PERIODS = (("year", "This year"), ("last", "Last year"), ("all", "All time"), ("custom", "Custom…"))
TWO_COLUMNS = 1000  # page width at which cards sit side by side
HOURS = [f"{h:02d}" for h in range(24)]
HOURS_LONG = [f"{h:02d}:00–{(h + 1) % 24:02d}:00" for h in range(24)]


def table_widget(
    headers: list[str], rows: list[list[str]], numeric_from: int = 1, name: str = ""
) -> QTableWidget:
    """A read-only table (the 'table version' of a chart, or a ranked list)."""
    table = QTableWidget(len(rows), len(headers))
    table.setAccessibleName(name or headers[0])  # what a screen reader calls the table
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().hide()
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setShowGrid(False)
    table.setFrameShape(QFrame.Shape.NoFrame)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    for c in range(1, len(headers)):
        table.horizontalHeader().setSectionResizeMode(c, QHeaderView.ResizeMode.ResizeToContents)
    for r, row in enumerate(rows):
        for c, text in enumerate(row):
            item = QTableWidgetItem(text)
            if c >= numeric_from:
                item.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            table.setItem(r, c, item)
    height = (
        table.horizontalHeader().height() + sum(table.rowHeight(r) for r in range(len(rows))) + 4
    )
    table.setFixedHeight(min(height, 420))
    return table


class StatsCard(QFrame):
    """A card: the question as its title, a caption, the chart, and a 'Show table' switch."""

    def __init__(self, title: str, caption: str, body: QWidget, chart=None) -> None:
        super().__init__()
        self.setObjectName("Card")
        self.chart, self.title = chart, title
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 16)
        v.setSpacing(4)
        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        heading = QLabel(title)
        heading.setProperty("role", "sectionTitle")
        heading.setWordWrap(True)
        self.caption = QLabel(caption)
        self.caption.setProperty("role", "caption")
        self.caption.setWordWrap(True)
        titles.addWidget(heading)
        titles.addWidget(self.caption)
        head.addLayout(titles, 1)
        self.controls = QHBoxLayout()
        head.addLayout(self.controls)
        self.toggle = QPushButton("Show table")
        self.toggle.setProperty("variant", "link")
        self.toggle.setToolTip("See the same numbers as a table")
        self.toggle.clicked.connect(self.flip)
        self.toggle.setVisible(chart is not None)
        head.addWidget(self.toggle, 0, Qt.AlignmentFlag.AlignTop)
        v.addLayout(head)
        v.addSpacing(8)
        self.stack = QStackedWidget()
        self.stack.addWidget(body)
        v.addWidget(self.stack)

    def flip(self) -> None:
        if self.stack.currentIndex() == 0 and self.chart is not None:
            while self.stack.count() > 1:
                old = self.stack.widget(1)
                self.stack.removeWidget(old)
                old.deleteLater()
            self.stack.addWidget(table_widget(*self.chart.table(), name=self.title))
            self.stack.setCurrentIndex(1)
            self.toggle.setText("Show chart")
        else:
            self.stack.setCurrentIndex(0)
            self.toggle.setText("Show table")
        self.stack.setFixedHeight(self.stack.currentWidget().sizeHint().height())

    def refresh_table(self) -> None:
        if self.stack.currentIndex() == 1:
            self.flip()
            self.flip()


class StatisticsPage(QWidget):
    show_sightings = Signal(object)  # SightingFilter
    open_sighting = Signal(int)
    add_requested = Signal()
    import_requested = Signal(str)

    def __init__(self, ctx: AppContext, theme: ThemeManager) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.ctx, self.theme = ctx, theme
        self.filter = SightingFilter()
        self.period = Period.this_year(self._today())
        self.data: Statistics | None = None
        self._generation = 0
        self._two_columns: bool | None = None
        self.top_measure = QSettings().value("statistics/top", "sightings")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("PageScroll")
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        outer.addWidget(scroll)
        body = QWidget()
        body.setObjectName("PageBody")
        scroll.setWidget(body)
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(28, 24, 28, 32)
        self.body.setSpacing(14)

        head = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title = QLabel("Statistics")
        title.setObjectName("PageTitle")
        subtitle = QLabel(
            "Every chart answers one question. Click a bar or cell to see those sightings."
        )
        subtitle.setObjectName("PageSubtitle")
        subtitle.setWordWrap(True)
        titles.addWidget(title)
        titles.addWidget(subtitle)
        head.addLayout(titles, 1)
        self.periods = Segmented(PERIODS, "year")
        self.periods.changed.connect(self._period_chosen)
        head.addWidget(self.periods, 0, Qt.AlignmentFlag.AlignBottom)
        self.body.addLayout(head)
        row = QHBoxLayout()
        self.filter_bar = FilterBar(ctx, theme, show_date=False)
        self.filter_bar.changed.connect(self._filter_changed)
        row.addWidget(self.filter_bar, 1)
        self.period_label = QLabel()
        self.period_label.setProperty("role", "muted")
        row.addWidget(self.period_label)
        self.body.addLayout(row)

        self.content = QWidget()
        self.content_layout = QVBoxLayout(self.content)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(14)
        self._fade = QGraphicsOpacityEffect(self.content)
        self._fade.setOpacity(1.0)
        self.content.setGraphicsEffect(self._fade)
        self.body.addWidget(self.content)
        self.body.addStretch(1)
        self._build_cards()
        self.empty = EmptyState(
            theme,
            "chart",
            "Statistics appear once you have sightings",
            "Your species list, busiest months and best places will show here.",
            [
                button("Add sighting", "primary", "plus", theme, lambda: self.add_requested.emit()),
                button(
                    "Import…",
                    "secondary",
                    "upload",
                    theme,
                    lambda: self.import_requested.emit("inaturalist"),
                ),
            ],
        )
        self.empty.hide()
        self.body.insertWidget(2, self.empty)
        self.refresh()

    def _today(self) -> date:
        return self.ctx.statistics.today()

    # ---- building ------------------------------------------------------------------
    def _build_cards(self) -> None:
        t = self.theme
        self.tiles = QGridLayout()
        self.tiles.setSpacing(10)
        self.content_layout.addLayout(self.tiles)

        self.growth = StepLineChart(t, "Species list growth")
        self.growth_card = StatsCard(
            "How is my species list growing?", "", self.growth, self.growth
        )

        self.top = BarChart(t, "Top species")
        self.top.clicked.connect(lambda taxon: self._open(taxon_ids=frozenset({taxon})))
        self.top_card = StatsCard("What do I see most?", "", self.top, self.top)
        self.top_switch = Segmented(
            [("sightings", "Sightings"), ("individuals", "Individuals counted")], self.top_measure
        )
        self.top_switch.changed.connect(self._top_measure_changed)
        self.top_card.controls.addWidget(self.top_switch)

        self.groups = BarChart(t, "Sightings per category")
        self.groups.clicked.connect(lambda cid: self._open(category_ids=frozenset({cid})))
        self.groups_card = StatsCard(
            "Which groups do I record?",
            "Sightings per category (the table also shows species)",
            self.groups,
            self.groups,
        )

        self.seasons = HeatTable(t, "Seasons", list("JFMAMJJASOND"), list(MONTHS_LONG))
        self.seasons.clicked.connect(
            lambda key: self._open(category_ids=frozenset({key[0]}), months=frozenset({key[1]}))
        )
        self.seasons_card = StatsCard(
            "When in the year is each group about?", "", self.seasons, self.seasons
        )

        self.hours = ColumnChart(t, "Time of day", HOURS, "sightings", 3, HOURS_LONG)
        self.hours.clicked.connect(lambda h: self._open(hours=frozenset({h})))
        self.hours_card = StatsCard(
            "What time of day are my sightings?",
            "Sightings with a recorded time, by hour (clock time)",
            self.hours,
            self.hours,
        )

        self.months = ColumnChart(
            t, "Species per month", [m[0] for m in MONTHS], "species", 1, list(MONTHS_LONG)
        )
        self.months.clicked.connect(self._open_month)
        self.months_card = StatsCard(
            "Am I seeing more than last year?", "", self.months, self.months
        )

        self.places_box = QWidget()
        self._places_layout = QVBoxLayout(self.places_box)
        self._places_layout.setContentsMargins(0, 0, 0, 0)
        self.places_card = StatsCard(
            "Where are my best places?",
            "Ranked by species; visits are days you recorded something there",
            self.places_box,
        )

        self.firsts_box = QWidget()
        self._firsts_layout = QVBoxLayout(self.firsts_box)
        self._firsts_layout.setContentsMargins(0, 0, 0, 0)
        self.firsts_card = StatsCard("What's new on my lists?", "", self.firsts_box)
        self.firsts_kind = "lifer"
        self._firsts_kind_picked = False  # until you choose, show the list that has entries
        self.firsts_switch = Segmented(
            [("lifer", "Lifers"), ("year", "Firsts of the year")], "lifer"
        )
        self.firsts_switch.changed.connect(self._firsts_kind_changed)
        self.firsts_card.controls.addWidget(self.firsts_switch)

        self.grid = QGridLayout()
        self.grid.setSpacing(14)
        self.content_layout.addLayout(self.grid)
        self._layout_cards(True)

    def _layout_cards(self, two: bool) -> None:
        if two == self._two_columns:
            return
        self._two_columns = two
        for card in self._cards():
            self.grid.removeWidget(card)
        wide = [self.growth_card, self.seasons_card]
        r = c = 0
        for card in self._cards():
            if card in wide or not two:
                if c:
                    r, c = r + 1, 0
                self.grid.addWidget(card, r, 0, 1, 2 if two else 1)
                r += 1
            else:
                self.grid.addWidget(card, r, c)
                c += 1
                if c == 2:
                    r, c = r + 1, 0
        self.grid.setColumnStretch(0, 1)
        self.grid.setColumnStretch(1, 1 if two else 0)

    def _cards(self) -> list[StatsCard]:
        return [
            self.growth_card,
            self.top_card,
            self.groups_card,
            self.seasons_card,
            self.hours_card,
            self.months_card,
            self.places_card,
            self.firsts_card,
        ]

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._layout_cards(self.width() >= TWO_COLUMNS)

    # ---- data ------------------------------------------------------------------------
    def refresh(self) -> None:
        """Recalculate in the background; the old numbers stay (faded) until the new arrive."""
        self._generation += 1
        generation, flt, period = self._generation, self.filter, self.period
        self.period_label.setText(
            period.label if period.key != "all" else "Since your first sighting"
        )
        self._fade.setOpacity(0.45 if self.data else 1.0)
        run_in_background(
            lambda: self.ctx.statistics.statistics(flt, period),
            on_done=lambda st: self._show(generation, st),
        )

    def _show(self, generation: int, st: Statistics) -> None:
        if generation != self._generation:
            return  # a newer period or filter is on its way
        self.data = st
        self._fade.setOpacity(1.0)
        nothing = self.ctx.sightings.totals(SightingFilter())[0] == 0
        self.empty.setVisible(nothing)
        self.content.setVisible(not nothing)
        if nothing:
            return
        self._fill_tiles(st)
        self._fill_growth(st)
        self._fill_top(st)
        self._fill_groups(st)
        self._fill_seasons(st)
        self.hours.set_series([Series("Sightings", st.hours)], keys=list(range(24)))
        self._fill_months(st)
        self._fill_places(st)
        self._fill_firsts(st)
        for card in self._cards():
            card.refresh_table()

    def _fill_tiles(self, st: Statistics) -> None:
        clear_layout(self.tiles)
        s = st.summary
        busiest = (
            (f"{s.busiest_count:,}", fmt_date(s.busiest_day, "medium"))
            if s.busiest_day
            else ("–", "")
        )
        tiles = [
            ("Sightings", f"{s.sightings:,}", f"on {plural(s.days, 'day')}"),
            ("Species", f"{s.species:,}", "Counted by the list rules"),
            ("Lifers", f"{s.lifers:,}", "New to your life list"),
            ("Outings", f"{s.outings:,}", ""),
            ("Places", f"{s.places:,}", "Saved places with sightings"),
            ("Busiest day", busiest[0], busiest[1]),
        ]
        columns = 6 if self.width() >= 1100 else 3
        for i, (label, value, delta) in enumerate(tiles):
            self.tiles.addWidget(StatTile(label, value, delta), i // columns, i % columns)

    def _fill_growth(self, st: Statistics) -> None:
        g = st.growth
        today = self._today()
        if g.by_day_of_year:
            lines = [
                Line(
                    c.label,
                    c.points,
                    emphasis=(i == 0),
                    end=(today - g.origin).days if i == 0 and g.origin.year == today.year else None,
                )
                for i, c in enumerate(g.curves)
            ]
            ticks = [
                ((date(g.origin.year, m, 1) - g.origin).days, MONTHS[m - 1]) for m in range(1, 13)
            ]

            def label(x: int) -> str:
                return fmt_date(g.origin + timedelta(days=x), "day")

            caption = f"Different species seen, {g.curves[0].label} against {g.curves[1].label}"
        else:
            lines = [Line(c.label, c.points) for c in g.curves]
            end = g.origin + timedelta(days=g.days)
            years = list(range(g.origin.year + 1, end.year + 1))
            step = max(1, len(years) // 8)
            ticks = [((date(y, 1, 1) - g.origin).days, str(y)) for y in years[::step]]
            if not ticks:  # a short custom range: label months
                month = add_months(g.origin.replace(day=1), 1)
                while month <= end:
                    ticks.append(((month - g.origin).days, MONTHS[month.month - 1]))
                    month = add_months(month, 1)

            def label(x: int) -> str:
                return fmt_date(g.origin + timedelta(days=x), "medium")

            caption = "Running total of different species seen"
        self.growth.set_lines(lines, g.days, ticks, label)
        self.growth_card.caption.setText(caption)

    def _fill_top(self, st: Statistics) -> None:
        by_animals = self.top_measure == "individuals"
        rows = st.top_by_individuals if by_animals else st.top_by_sightings
        self.top.set_bars(
            [Bar(r.name, r.individuals if by_animals else r.sightings, r.taxon_id) for r in rows],
            "individuals counted" if by_animals else "sightings",
        )
        self.top_card.caption.setText(
            "Top 10 by individuals counted (a sighting with no count is 1)"
            if by_animals
            else "Top 10 species by number of sightings"
        )

    def _fill_groups(self, st: Statistics) -> None:
        t = self.theme.tokens
        cats = {c.id: c for c in self.ctx.catalogue.categories()}
        shown = [r for r in st.categories if r.category_id in cats]
        self.groups.set_bars(
            [
                Bar(
                    cats[r.category_id].name,
                    r.sightings,
                    r.category_id,
                    swatch(cats[r.category_id], t, 16),
                )
                for r in shown
            ],
            extra=("Species", [r.species for r in shown]),  # in the table version
        )

    def _fill_seasons(self, st: Statistics) -> None:
        t = self.theme.tokens
        present = sorted({cid for cid, _ in st.seasons})
        cats = {c.id: c for c in self.ctx.catalogue.categories()}
        self.seasons.set_rows(
            [
                HeatRow(
                    cats[cid].name,
                    [st.seasons.get((cid, m), 0) for m in range(1, 13)],
                    swatch(cats[cid], t, 16),
                    cid,
                )
                for cid in sorted(present, key=lambda c: cats[c].sort_order if c in cats else 999)
                if cid in cats
            ]
        )
        years = "all years combined" if not st.period.is_year else st.period.label
        self.seasons_card.caption.setText(f"Sightings per month and category, {years}")

    def _fill_months(self, st: Statistics) -> None:
        years = sorted(st.months, reverse=True)
        self.months.set_series(
            [Series(str(y), st.months[y], emphasis=(i == 0)) for i, y in enumerate(years)],
            keys=[(years[0], m) for m in range(1, 13)],
        )
        self.months_card.caption.setText(
            f"Different species seen each month, {years[0]} against {years[1]}"
        )

    def _fill_places(self, st: Statistics) -> None:
        clear_layout(self._places_layout)
        if not st.places:
            note = QLabel("No sightings at saved places in this period.")
            note.setProperty("role", "muted")
            self._places_layout.addWidget(note)
            return
        rows = [
            [
                p.name,
                f"{p.species:,}",
                f"{p.visits:,}",
                f"{p.sightings:,}",
                f"{p.species / p.visits:.1f}",
            ]
            for p in st.places[:12]
        ]
        table = table_widget(
            ["Place", "Species", "Visits", "Sightings", "Species per visit"],
            rows,
            name="Best places",
        )
        table.setToolTip("Double-click a place to see its sightings")
        ids = [p.place_id for p in st.places[:12]]
        table.cellDoubleClicked.connect(lambda r, _c: self._open(place_ids=frozenset({ids[r]})))
        self._places_layout.addWidget(table)

    def _fill_firsts(self, st: Statistics) -> None:
        clear_layout(self._firsts_layout)
        lifers = [r for r in st.firsts if r.kind == "lifer"]
        years = [r for r in st.firsts if r.kind == "year"]
        self.firsts_card.caption.setText(
            f"{plural(len(lifers), 'lifer')} (new to your life list) and "
            f"{plural(len(years), 'first of the year', 'firsts of the year')} · double-click to open"
        )
        if not self._firsts_kind_picked:  # open on whichever list has something in it
            self.firsts_kind = "lifer" if lifers or not years else "year"
            self.firsts_switch.set_current(self.firsts_kind)
        chosen = lifers if self.firsts_kind == "lifer" else years
        if not chosen:
            note = QLabel(
                "No lifers in this period."
                if self.firsts_kind == "lifer"
                else "No firsts of the year here."
            )
            note.setProperty("role", "muted")
            self._firsts_layout.addWidget(note)
            self._firsts_layout.addStretch(1)
            return
        shown = chosen[:200]
        rows = [[r.name, fmt_date(r.day, "medium"), r.place or "–"] for r in shown]
        table = table_widget(["Species", "Date", "Place"], rows, numeric_from=9, name="New species")
        table.cellDoubleClicked.connect(lambda r, _c: self.open_sighting.emit(shown[r].sighting_id))
        self._firsts_layout.addWidget(table)

    def _firsts_kind_changed(self, kind: str) -> None:
        self.firsts_kind = kind
        self._firsts_kind_picked = True
        if self.data:
            self._fill_firsts(self.data)

    # ---- choices ---------------------------------------------------------------------
    def _period_chosen(self, key: str) -> None:
        today = self._today()
        if key == "custom":
            chosen = self._ask_dates()
            if chosen is None:
                self.periods.set_current(self.period.key)
                return
            self.period = Period.custom(*chosen)
        else:
            self.period = {
                "year": Period.this_year(today),
                "last": Period.last_year(today),
                "all": Period.all_time(),
            }[key]
        self.refresh()

    def _ask_dates(self) -> tuple[date, date] | None:
        today = self._today()
        dialog = QDialog(self)
        dialog.setWindowTitle("Choose a period")
        form = QFormLayout(dialog)
        start, end = QDateEdit(), QDateEdit()
        for w, value in (
            (start, self.period.start or date(today.year, 1, 1)),
            (end, self.period.end or today),
        ):
            w.setCalendarPopup(True)
            w.setDisplayFormat("d MMM yyyy")
            w.setDate(QDate(value.year, value.month, value.day))
        form.addRow("From", start)
        form.addRow("To", end)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        form.addRow(buttons)
        if dialog.exec():
            return start.date().toPython(), end.date().toPython()
        return None

    def set_period(self, period: Period) -> None:
        self.period = period
        self.periods.set_current(period.key)
        self.refresh()

    def _filter_changed(self, flt: SightingFilter) -> None:
        self.filter = flt
        self.refresh()

    def _top_measure_changed(self, measure: str) -> None:
        self.top_measure = measure
        QSettings().setValue("statistics/top", measure)
        if self.data:
            self._fill_top(self.data)
            self.top_card.refresh_table()

    def _open(self, **changes) -> None:
        """Show the sightings behind a bar, cell or row (with this period and filter)."""
        self.show_sightings.emit(self.period.applied(self.filter).with_(**changes))

    def _open_month(self, key: tuple[int, int]) -> None:
        year, month = key
        first = date(year, month, 1)
        self.show_sightings.emit(self.filter.with_(date_from=first, date_to=month_end(first)))
