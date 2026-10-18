"""Dashboard: what's been happening, and what needs doing."""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QGridLayout, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from wildlife.context import AppContext
from wildlife.domain.filters import SightingFilter
from wildlife.ui.components.activity import ActivityStrip
from wildlife.ui.components.charts import Bar, BarChart
from wildlife.ui.components.common import EmptyState, Page, button
from wildlife.ui.components.rows import RowButton, StatTile, attention_row, sighting_row
from wildlife.ui.components.visuals import MONTHS_LONG, fmt_date, plural, swatch
from wildlife.ui.theme.manager import ThemeManager


def _card(title: str) -> tuple[QFrame, QVBoxLayout]:
    card = QFrame()
    card.setObjectName("Card")
    v = QVBoxLayout(card)
    v.setContentsMargins(16, 14, 16, 12)
    v.setSpacing(2)
    heading = QLabel(title)
    heading.setProperty("role", "sectionTitle")
    v.addWidget(heading)
    v.addSpacing(6)
    return card, v


class DashboardPage(QWidget):
    open_sighting = Signal(int)
    add_requested = Signal()
    import_requested = Signal(str)  # 'inaturalist' or 'csv'
    show_sightings = Signal(object)  # SightingFilter
    backup_requested = Signal()
    open_inbox = Signal()
    open_day = Signal(object)  # date: open it in the calendar
    toast = Signal(str, object)

    def __init__(self, ctx: AppContext, theme: ThemeManager) -> None:
        super().__init__()
        self.ctx, self.theme = ctx, theme
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._page: QWidget | None = None
        self.refresh()

    def refresh(self) -> None:
        if self._page is not None:
            self._layout.removeWidget(self._page)
            self._page.deleteLater()
        numbers = self.ctx.stats.dashboard()
        self._page = self._welcome() if numbers.total_sightings == 0 else self._full(numbers)
        self._layout.addWidget(self._page)

    def _welcome(self) -> Page:
        t = self.theme
        page = Page("Welcome to Thicket")
        page.add(
            EmptyState(
                t,
                "leaf",
                "Start your wildlife journal",
                "Record what you see in a few seconds, or bring in what you've already "
                "recorded, then explore it on the calendar, map and charts. Everything stays "
                "on this PC.",
                [
                    button(
                        "Add your first sighting", "primary", "plus", t, self.add_requested.emit
                    ),
                    button(
                        "Import from iNaturalist…",
                        "secondary",
                        "upload",
                        t,
                        lambda: self.import_requested.emit("inaturalist"),
                    ),
                    button(
                        "Import a spreadsheet…",
                        "secondary",
                        "upload",
                        t,
                        lambda: self.import_requested.emit("csv"),
                    ),
                ],
            )
        )
        page.finish()
        return page

    def _full(self, n) -> Page:
        today = self.ctx.stats.today()
        hour = datetime.now().hour
        greeting = (
            "Good morning" if hour < 12 else "Good afternoon" if hour < 18 else "Good evening"
        )
        sub = f"{fmt_date(today, 'full')} · " + (
            f"{plural(n.today_sightings, 'sighting')} so far today"
            if n.today_sightings
            else "No sightings yet today"
        )
        page = Page(
            greeting,
            sub,
            [button("Add sighting", "primary", "plus", self.theme, self.add_requested.emit)],
        )

        tiles = QHBoxLayout()
        tiles.setSpacing(12)
        diff = n.year_species - n.last_year_species_to_date
        compare = (
            f"{diff} more than this time in {today.year - 1}"
            if diff > 0
            else f"{-diff} fewer than this time in {today.year - 1}"
            if diff < 0
            else f"Same as this time in {today.year - 1}"
        )
        for tile in (
            StatTile(
                "Total sightings",
                f"{n.total_sightings:,}",
                f"Since {fmt_date(n.first_date, 'medium')}" if n.first_date else "",
            ),
            StatTile(
                "Life list",
                f"{n.life_species:,}",
                plural(n.life_species, "species", "species") + " recorded",
            ),
            StatTile(
                f"Species in {today.year}",
                f"{n.year_species:,}",
                compare if n.last_year_species_to_date else "",
                good=diff > 0,
            ),
            StatTile(
                f"Sightings in {MONTHS_LONG[today.month - 1]}",
                f"{n.month_sightings:,}",
                plural(n.month_days, "day") + " out recording" if n.month_days else "",
            ),
        ):
            tiles.addWidget(tile, 1)
        holder = QWidget()
        holder.setLayout(tiles)
        page.add(holder)

        # this year's activity: a square per day, darker = more sightings
        activity, act = _card(f"Your {today.year} so far")
        strip = ActivityStrip(self.theme)
        strip.set_counts(
            today.year,
            self.ctx.statistics.day_counts(date(today.year, 1, 1), date(today.year, 12, 31)),
            today,
        )
        strip.day_clicked.connect(self.open_day.emit)
        act.addWidget(strip)
        page.add(activity)

        grid = QGridLayout()
        grid.setSpacing(12)
        recent_card, rv = _card("Recent sightings")
        for s in self.ctx.sightings.page(SightingFilter(), "date", True, 0, 8):
            rv.addWidget(sighting_row(self.ctx, self.theme, s, self.open_sighting.emit))
        view_all = button(
            "View all sightings",
            "link",
            None,
            None,
            lambda: self.show_sightings.emit(SightingFilter()),
        )
        rv.addWidget(view_all, 0, Qt.AlignmentFlag.AlignLeft)
        rv.addStretch(1)  # rows stay together at the top when the card is tall
        grid.addWidget(recent_card, 0, 0, 3, 2)

        attention, av = _card("Needs attention")
        any_item = False
        if n.without_location:
            any_item = True
            av.addWidget(
                attention_row(
                    self.theme,
                    "pin",
                    f"{plural(n.without_location, 'sighting')} without a location",
                    "Add a place or position when you can",
                    "warning",
                    lambda: self.show_sightings.emit(SightingFilter(needs_location=True)),
                )
            )
        inbox = self.ctx.photos.inbox_count()
        if inbox:
            any_item = True
            av.addWidget(
                attention_row(
                    self.theme,
                    "image",
                    f"{plural(inbox, 'photo')} in your Photo Inbox",
                    "Say what they show to turn them into sightings",
                    "warning",
                    self.open_inbox.emit,
                )
            )
        av.addWidget(self._backup_row())
        if not any_item:
            ok = QLabel("Nothing else needs your attention.")
            ok.setProperty("role", "muted")
            av.addWidget(ok)
        av.addStretch(1)
        grid.addWidget(attention, 0, 2)

        new, nv = _card(f"New in {today.year}")
        firsts = self.ctx.statistics.recent_firsts(5)
        for f in firsts:
            badge = "★ Lifer" if f.kind == "lifer" else "First of the year"
            nv.addWidget(
                RowButton(
                    swatch(self.ctx.catalogue.category(f.category_id), self.theme.tokens, 28),
                    f.name,
                    f"{fmt_date(f.day, 'day')} · {badge}",
                    "›",
                    lambda sid=f.sighting_id: self.open_sighting.emit(sid),
                )
            )
        if not firsts:
            none = QLabel("Nothing new yet this year.")
            none.setProperty("role", "muted")
            nv.addWidget(none)
        nv.addStretch(1)
        grid.addWidget(new, 1, 2)

        top, tv = _card(f"Most seen in {today.year}")
        this_year = SightingFilter(date_from=date(today.year, 1, 1), date_to=today)
        chart = BarChart(self.theme, f"Most seen in {today.year}")
        chart.set_bars(
            [
                Bar(r.name, r.sightings, r.taxon_id)
                for r in self.ctx.statistics.top_species(this_year)
            ]
        )
        chart.clicked.connect(
            lambda taxon: self.show_sightings.emit(this_year.with_(taxon_ids=frozenset({taxon})))
        )
        tv.addWidget(chart)
        tv.addStretch(1)
        grid.addWidget(top, 2, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        holder2 = QWidget()
        holder2.setLayout(grid)
        page.add(holder2)
        page.finish()
        return page

    def _backup_row(self) -> QWidget:
        last = self.ctx.backup.last_result()
        if last is None:
            return attention_row(
                self.theme,
                "shield",
                "Not backed up yet",
                "Click to back up now",
                "warning",
                self.backup_requested.emit,
            )
        when = datetime.fromisoformat(last.when).astimezone()
        stamp = f"{fmt_date(when.date(), 'day')} at {when:%H:%M}"
        if not last.ok:
            return attention_row(
                self.theme,
                "alert",
                "Last backup failed",
                f"{stamp}: {last.message}",
                "warning",
                self.backup_requested.emit,
            )
        if self.ctx.backup.uses_default_folder():
            return attention_row(
                self.theme,
                "shield",
                f"Backed up {stamp}",
                "On the same drive as your data. Choose another drive in Settings.",
                "warning",
                None,
            )
        return attention_row(self.theme, "shield", f"Backed up {stamp}", "Verified", "good", None)
