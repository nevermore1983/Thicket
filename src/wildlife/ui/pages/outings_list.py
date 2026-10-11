"""The Outings tab on the Sightings page: every trip, newest first."""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QScrollArea, QVBoxLayout, QWidget

from wildlife.context import AppContext
from wildlife.domain.dates import fmt_date
from wildlife.domain.models import Outing
from wildlife.ui.components.common import EmptyState, button, clear_layout
from wildlife.ui.components.rows import RowButton
from wildlife.ui.components.visuals import plural
from wildlife.ui.panels.outing_detail import times_text, weather_text
from wildlife.ui.theme.icons import pixmap
from wildlife.ui.theme.manager import ThemeManager

PAGE = 100  # outings shown at first, and added by each 'Show more'


def outing_meta(o: Outing) -> str:
    # An outing without its own title is already named after its date
    parts = [fmt_date(o.outing_date)] if o.title else []
    parts.append(times_text(o))
    if o.weather or o.temperature_c is not None:
        parts.append(weather_text(o))
    if o.is_complete_list:
        parts.append("complete list")
    return " · ".join(parts)


class OutingsList(QWidget):
    open_outing = Signal(int)
    new_outing = Signal()
    start_outing = Signal()

    def __init__(self, ctx: AppContext, theme: ThemeManager) -> None:
        super().__init__()
        self.ctx, self.theme = ctx, theme
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        actions = QHBoxLayout()
        intro = QLabel(
            "An outing groups the sightings from one trip and keeps the weather and times."
        )
        intro.setProperty("role", "muted")
        intro.setWordWrap(True)
        actions.addWidget(intro, 1)
        self.start_button = button(
            "Start outing now", "secondary", "clock", theme, self.start_outing.emit
        )
        self.start_button.setToolTip("Begin an outing at the current time; new sightings join it")
        actions.addWidget(self.start_button)
        actions.addWidget(button("New outing", "secondary", "plus", theme, self.new_outing.emit))
        v.addLayout(actions)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setObjectName("PageScroll")
        self._body = QWidget()
        self._body.setObjectName("PageBody")
        self._rows = QVBoxLayout(self._body)
        self._rows.setContentsMargins(0, 0, 0, 0)
        self._rows.setSpacing(2)
        scroll.setWidget(self._body)
        v.addWidget(scroll, 1)
        self.footer = QLabel()
        self.footer.setProperty("role", "muted")
        v.addWidget(self.footer)

    def refresh(self) -> None:
        clear_layout(self._rows)
        self._shown = 0
        self.start_button.setEnabled(self.ctx.outings.in_progress() is None)
        if self.ctx.outings.count() == 0:
            self._rows.addWidget(
                EmptyState(
                    self.theme,
                    "route",
                    "No outings yet",
                    "Start one when you head out, or add one afterwards. "
                    "New sightings on that day join it automatically.",
                    [
                        button(
                            "Start outing now",
                            "primary",
                            "clock",
                            self.theme,
                            self.start_outing.emit,
                        )
                    ],
                )
            )
            self.footer.setText("")
            return
        self._more = button("Show more", "secondary", None, self.theme, self._add_page)
        self._rows.addWidget(self._more, 0, Qt.AlignmentFlag.AlignLeft)
        self._rows.addStretch(1)
        self._add_page()

    def _add_page(self) -> None:
        """Add the next PAGE outings above the 'Show more' button (rows are slow to build)."""
        outings = self.ctx.outings.page(self._shown, PAGE)
        icon = pixmap("route", self.theme.tokens.text_2, 20)
        at = self._rows.indexOf(self._more)
        for i, o in enumerate(outings):
            self._rows.insertWidget(
                at + i,
                RowButton(
                    icon,
                    o.display_title + ("  · in progress" if o.in_progress else ""),
                    outing_meta(o),
                    f"{plural(o.species, 'species', 'species')}\n{plural(o.sightings, 'sighting')}",
                    lambda oid=o.id: self.open_outing.emit(oid),
                ),
            )
        self._shown += len(outings)
        total = self.ctx.outings.count()
        self._more.setVisible(self._shown < total)
        shown = f" · showing the latest {self._shown:,}" if total > self._shown else ""
        self.footer.setText(f"{plural(total, 'outing')}{shown}")
