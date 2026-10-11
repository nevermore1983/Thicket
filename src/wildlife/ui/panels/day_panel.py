"""Side panel listing one day's sightings, opened by clicking a day in the calendar."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from wildlife.context import AppContext
from wildlife.domain.dates import fmt_date
from wildlife.domain.filters import SightingFilter
from wildlife.ui.calendar.day_view import outing_summary, species_count
from wildlife.ui.components.common import EmptyState, button
from wildlife.ui.components.rows import RowButton, day_row
from wildlife.ui.components.side_panel import PanelView
from wildlife.ui.components.visuals import plural
from wildlife.ui.theme.icons import pixmap
from wildlife.ui.theme.manager import ThemeManager

MAX_ROWS = 300


class DayPanel(PanelView):
    open_sighting = Signal(int)
    add_on = Signal(object)  # date
    open_day_view = Signal(object)  # date
    open_outing = Signal(int)

    def __init__(
        self, ctx: AppContext, theme: ThemeManager, day: date, flt: SightingFilter
    ) -> None:
        super().__init__()
        self.ctx, self.theme, self.day, self.filter = ctx, theme, day, flt
        self.title = fmt_date(day, "full")
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(0)
        self._content: QWidget | None = None
        self.reload()
        theme.changed.connect(self.reload)

    def reload(self) -> None:
        if self._content is not None:
            self._layout.removeWidget(self._content)
            self._content.deleteLater()
        t, day = self.theme, self.day
        day_filter = self.filter.with_(date_from=day, date_to=day)
        items = self.ctx.sightings.page(day_filter, "date", False, 0, MAX_ROWS)
        firsts = self.ctx.calendar.firsts(self.filter, day, day)
        outings = self.ctx.outings.on_date(day)

        content = QWidget()
        v = QVBoxLayout(content)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("PanelBody")
        scroll.setWidget(body)
        b = QVBoxLayout(body)
        b.setContentsMargins(14, 12, 14, 16)
        b.setSpacing(4)
        if items:
            filtered = " (filtered)" if not self.filter.is_empty else ""
            summary = QLabel(
                f"{plural(len(items), 'sighting')} · "
                f"{plural(species_count(items), 'species', 'species')}{filtered}"
            )
            summary.setProperty("role", "muted")
            b.addWidget(summary)
            b.addSpacing(6)
            for s in items:
                b.addWidget(day_row(self.ctx, t, s, firsts.mark(s.id), self.open_sighting.emit))
        else:
            b.addWidget(
                EmptyState(
                    t,
                    "calendar",
                    "No sightings on this day",
                    "Nothing matches the current filters."
                    if not self.filter.is_empty
                    else "Add one if you forgot to record something.",
                )
            )
        if outings:
            b.addSpacing(12)
            heading = QLabel("Outings")
            heading.setProperty("role", "sectionTitle")
            b.addWidget(heading)
            for o in outings:
                b.addWidget(
                    RowButton(
                        pixmap("route", t.tokens.text_2, 20),
                        o.display_title,
                        outing_summary(o),
                        "›",
                        lambda oid=o.id: self.open_outing.emit(oid),
                    )
                )
        b.addStretch(1)
        v.addWidget(scroll, 1)

        foot = QFrame()
        foot.setObjectName("PanelFoot")
        fh = QHBoxLayout(foot)
        fh.setContentsMargins(18, 12, 18, 12)
        fh.addWidget(
            button("Add sighting on this date", "primary", "plus", t, lambda: self.add_on.emit(day))
        )
        fh.addStretch(1)
        fh.addWidget(
            button("Open day view", "secondary", None, t, lambda: self.open_day_view.emit(day))
        )
        v.addWidget(foot)
        self._layout.addWidget(content)
        self._content = content
