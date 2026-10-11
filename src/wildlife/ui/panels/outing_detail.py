"""Read-only view of one outing: summary, weather and its sightings."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.domain.dates import fmt_date
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import Outing
from wildlife.ui.components.common import button
from wildlife.ui.components.rows import StatTile, day_row
from wildlife.ui.components.side_panel import PanelView
from wildlife.ui.theme.manager import ThemeManager


def weather_text(o: Outing) -> str:
    parts = [o.weather.label if o.weather else None]
    if o.temperature_c is not None:
        parts.append(f"{o.temperature_c:g} °C")
    if o.wind:
        parts.append(f"{o.wind.label.lower()} wind")
    if o.visibility:
        parts.append(f"{o.visibility.label.lower()} visibility")
    return ", ".join(p for p in parts if p) or "Not recorded"


def times_text(o: Outing) -> str:
    if o.start_time and o.end_time:
        return f"{o.start_time}–{o.end_time}"
    if o.start_time:
        return f"from {o.start_time}" + (" · in progress" if o.in_progress else "")
    return "Times not recorded"


class OutingDetail(PanelView):
    open_sighting = Signal(int)
    edit_requested = Signal(int)
    delete_requested = Signal(int)
    end_requested = Signal(int)
    add_requested = Signal(object)  # Outing: add a sighting to it
    show_list = Signal(object)  # SightingFilter

    def __init__(self, ctx: AppContext, theme: ThemeManager, outing_id: int) -> None:
        super().__init__()
        self.ctx, self.theme, self.outing_id = ctx, theme, outing_id
        self.title = "Outing"
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
        o = self.ctx.outings.get(self.outing_id)
        self.title = "Outing in progress" if o.in_progress else "Outing"
        t = self.theme
        flt = SightingFilter(outing_id=o.id)
        items = self.ctx.sightings.page(flt, "date", False, 0, 500)
        firsts = self.ctx.calendar.firsts(flt, o.outing_date, o.outing_date)

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
        b.setContentsMargins(18, 14, 18, 20)
        b.setSpacing(12)

        name = QLabel(o.display_title)
        name.setObjectName("CalTitle")
        name.setWordWrap(True)
        b.addWidget(name)
        when = QLabel(f"{fmt_date(o.outing_date, 'full')} · {times_text(o)}")
        when.setProperty("role", "muted")
        when.setWordWrap(True)
        b.addWidget(when)

        tiles = QGridLayout()
        tiles.setSpacing(8)
        new = len(firsts.lifers | firsts.year_firsts)
        for i, (label, value) in enumerate(
            (("Species", o.species), ("Sightings", o.sightings), ("New this year", new))
        ):
            tiles.addWidget(StatTile(label, f"{value:,}"), 0, i)
        b.addLayout(tiles)

        facts = QGridLayout()
        facts.setHorizontalSpacing(16)
        facts.setVerticalSpacing(6)
        rows = [
            ("Place", o.place_name or "No place"),
            ("Weather", weather_text(o)),
            (
                "Complete list",
                "Yes, every species identified was recorded" if o.is_complete_list else "No",
            ),
        ]
        if o.notes:
            rows.append(("Notes", o.notes))
        for r, (label, value) in enumerate(rows):
            k = QLabel(label)
            k.setProperty("role", "muted")
            val = QLabel(value)
            val.setWordWrap(True)
            val.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            facts.addWidget(k, r, 0, Qt.AlignmentFlag.AlignTop)
            facts.addWidget(val, r, 1)
        facts.setColumnStretch(1, 1)
        b.addLayout(facts)

        heading = QLabel("Sightings")
        heading.setProperty("role", "sectionTitle")
        b.addWidget(heading)
        if items:
            for s in items:
                b.addWidget(day_row(self.ctx, t, s, firsts.mark(s.id), self.open_sighting.emit))
            b.addWidget(
                button(
                    "Show in the sightings list", "link", None, t, lambda: self.show_list.emit(flt)
                ),
                0,
                Qt.AlignmentFlag.AlignLeft,
            )
        else:
            none = QLabel("No sightings in this outing yet.")
            none.setProperty("role", "muted")
            b.addWidget(none)
        b.addStretch(1)
        v.addWidget(scroll, 1)

        foot = QFrame()
        foot.setObjectName("PanelFoot")
        fh = QHBoxLayout(foot)
        fh.setContentsMargins(18, 12, 18, 12)
        fh.setSpacing(8)
        if o.in_progress:
            fh.addWidget(
                button("Add sighting", "primary", "plus", t, lambda: self.add_requested.emit(o))
            )
            fh.addWidget(
                button("End outing", "secondary", None, t, lambda: self.end_requested.emit(o.id))
            )
        else:
            fh.addWidget(
                button("Edit", "primary", "edit", t, lambda: self.edit_requested.emit(o.id))
            )
            fh.addWidget(
                button("Add sighting", "secondary", "plus", t, lambda: self.add_requested.emit(o))
            )
        fh.addStretch(1)
        delete = button("Delete", "ghost", "trash", t, lambda: self.delete_requested.emit(o.id))
        delete.setToolTip("Delete the outing. Its sightings are kept.")
        fh.addWidget(delete)
        v.addWidget(foot)
        self._layout.addWidget(content)
        self._content = content
