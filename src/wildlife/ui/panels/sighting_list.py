"""Side panel listing a handful of sightings, e.g. several at the same spot on the map."""

from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QFrame, QLabel, QScrollArea, QVBoxLayout, QWidget

from wildlife.context import AppContext
from wildlife.domain.errors import NotFoundError
from wildlife.ui.components.common import clear_layout
from wildlife.ui.components.rows import sighting_row
from wildlife.ui.components.side_panel import PanelView
from wildlife.ui.components.visuals import plural
from wildlife.ui.theme.manager import ThemeManager

MAX_ROWS = 300


class SightingListPanel(PanelView):
    open_sighting = Signal(int)

    def __init__(self, ctx: AppContext, theme: ThemeManager, ids: list[int], title: str) -> None:
        super().__init__()
        self.ctx, self.theme, self.ids = ctx, theme, ids
        self.title = title
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setObjectName("PanelBody")
        scroll.setWidget(body)
        outer.addWidget(scroll)
        self._rows = QVBoxLayout(body)
        self._rows.setContentsMargins(14, 12, 14, 16)
        self._rows.setSpacing(4)
        self.reload()

    def reload(self) -> None:
        clear_layout(self._rows)
        found = []
        for i in self.ids[:MAX_ROWS]:
            try:
                found.append(self.ctx.sightings.get(i))
            except NotFoundError:
                continue  # deleted since the map was drawn
        found.sort(key=lambda s: (s.observed_date, s.observed_time or ""), reverse=True)
        summary = QLabel(
            plural(len(found), "sighting")
            + (f" (showing {MAX_ROWS} of {len(self.ids):,})" if len(self.ids) > MAX_ROWS else "")
        )
        summary.setProperty("role", "muted")
        self._rows.addWidget(summary)
        for s in found:
            self._rows.addWidget(sighting_row(self.ctx, self.theme, s, self.open_sighting.emit))
        self._rows.addStretch(1)
