"""Day view: the day's sightings in time order, beside the day's outings and their weather."""

from __future__ import annotations

from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QBoxLayout, QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from wildlife.context import AppContext
from wildlife.domain.models import Outing, Sighting
from wildlife.services.calendar import Firsts
from wildlife.ui.components.common import EmptyState, button, clear_layout
from wildlife.ui.components.rows import RowButton, day_row
from wildlife.ui.components.visuals import plural
from wildlife.ui.theme.icons import pixmap
from wildlife.ui.theme.manager import ThemeManager


def species_count(items: list[Sighting]) -> int:
    """Different species in a list (subspecies count as their species)."""
    return len({s.species_id or s.display_name for s in items})


def outing_summary(o: Outing) -> str:
    """'07:30–11:00 · Sunny, 12 °C · 14 sightings' (the outing panel has the full details)."""
    parts = []
    if o.start_time:
        parts.append(f"{o.start_time}–{o.end_time or 'now'}")
    weather = [o.weather.label] if o.weather else []
    if o.temperature_c is not None:
        weather.append(f"{o.temperature_c:g} °C")
    if weather:
        parts.append(", ".join(weather))
    parts.append(plural(o.sightings, "sighting"))
    return " · ".join(parts)


def _card(title: str) -> tuple[QFrame, QVBoxLayout, QHBoxLayout]:
    card = QFrame()
    card.setObjectName("Card")
    v = QVBoxLayout(card)
    v.setContentsMargins(16, 14, 16, 14)
    v.setSpacing(4)
    head = QHBoxLayout()
    heading = QLabel(title)
    heading.setProperty("role", "sectionTitle")
    head.addWidget(heading)
    head.addStretch(1)
    v.addLayout(head)
    v.addSpacing(6)
    return card, v, head


class DayView(QWidget):
    open_sighting = Signal(int)
    add_on = Signal(object)  # date
    open_outing = Signal(int)
    new_outing = Signal(object)  # date
    show_map = Signal(object)  # date

    def __init__(self, ctx: AppContext, theme: ThemeManager) -> None:
        super().__init__()
        self.ctx, self.theme = ctx, theme
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(12)
        self.setAccessibleName("Day")

    def resizeEvent(self, event) -> None:
        # Side by side when there's room; the outings card moves below the list when narrow
        narrow = self.width() < 720
        self._layout.setDirection(
            QBoxLayout.Direction.TopToBottom if narrow else QBoxLayout.Direction.LeftToRight
        )
        super().resizeEvent(event)

    def set_data(
        self,
        day: date,
        items: list[Sighting],
        firsts: Firsts,
        outings: list[Outing],
        filtered: bool,
    ) -> None:
        clear_layout(self._layout)
        t = self.theme
        if items:
            title = f"{plural(len(items), 'sighting')} · {plural(species_count(items), 'species', 'species')}"
            card, v, head = _card(title + (" (filtered)" if filtered else ""))
            head.addWidget(
                button("Show on map", "secondary", "map", t, lambda: self.show_map.emit(day))
            )
            head.addWidget(
                button("Add on this date", "secondary", "plus", t, lambda: self.add_on.emit(day))
            )
            for s in items:
                v.addWidget(day_row(self.ctx, t, s, firsts.mark(s.id), self.open_sighting.emit))
        else:
            card, v, _ = _card("Sightings")
            v.addWidget(
                EmptyState(
                    t,
                    "calendar",
                    "No sightings on this day" + (" match the filters" if filtered else ""),
                    "Add one if you forgot to record something.",
                    [
                        button(
                            "Add sighting on this date",
                            "primary",
                            "plus",
                            t,
                            lambda: self.add_on.emit(day),
                        )
                    ],
                )
            )
        v.addStretch(1)
        self._layout.addWidget(card, 2, Qt.AlignmentFlag.AlignTop)

        side, sv, _ = _card("Outings")
        if outings:
            for o in outings:
                sv.addWidget(
                    RowButton(
                        pixmap("route", t.tokens.text_2, 20),
                        o.display_title,
                        outing_summary(o),
                        "›",
                        lambda oid=o.id: self.open_outing.emit(oid),
                    )
                )
        else:
            note = QLabel(
                "No outing recorded. An outing groups a trip's sightings and keeps the weather."
            )
            note.setProperty("role", "muted")
            note.setWordWrap(True)
            sv.addWidget(note)
        sv.addSpacing(6)
        sv.addWidget(
            button(
                "New outing on this day", "secondary", "plus", t, lambda: self.new_outing.emit(day)
            ),
            0,
            Qt.AlignmentFlag.AlignLeft,
        )
        side.setMinimumWidth(280)
        self._layout.addWidget(side, 1, Qt.AlignmentFlag.AlignTop)
