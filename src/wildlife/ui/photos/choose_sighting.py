"""'Add to existing sighting…': pick the sighting some Inbox photos belong to.

Sightings from the photos' own day come first (nearly always the right one); a search
box finds any other.
"""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
)

from wildlife.context import AppContext
from wildlife.domain.dates import fmt_date
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import Sighting
from wildlife.ui.components.visuals import swatch
from wildlife.ui.theme.manager import ThemeManager


def describe(s: Sighting) -> str:
    when = fmt_date(s.observed_date) + (f" {s.observed_time}" if s.observed_time else "")
    where = f" · {s.place_name}" if s.place_name else ""
    return f"{s.display_name}  ·  {when}{where}"


class ChooseSightingDialog(QDialog):
    def __init__(
        self, ctx: AppContext, theme: ThemeManager, around: date | None, parent=None
    ) -> None:
        super().__init__(parent)
        self.ctx, self.theme, self.around = ctx, theme, around
        self.chosen: int | None = None
        self.setWindowTitle("Add photos to a sighting")
        self.resize(520, 480)
        v = QVBoxLayout(self)
        intro = QLabel(
            f"Sightings around {fmt_date(around)} are listed first."
            if around
            else "Choose the sighting these photos belong to."
        )
        intro.setProperty("role", "muted")
        intro.setWordWrap(True)
        v.addWidget(intro)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search by species, place or notes…")
        self.search.setClearButtonEnabled(True)
        self._timer = QTimer(self, singleShot=True, interval=200)
        self._timer.timeout.connect(self._fill)
        self.search.textEdited.connect(lambda _: self._timer.start())
        v.addWidget(self.search)
        self.list = QListWidget()
        self.list.itemDoubleClicked.connect(lambda _: self.accept())
        self.list.currentRowChanged.connect(lambda _: self._sync())
        v.addWidget(self.list, 1)
        self.buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Add photos")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        v.addWidget(self.buttons)
        self._fill()
        self.search.setFocus()

    def _sightings(self) -> list[Sighting]:
        text = self.search.text().strip()
        if text:
            return self.ctx.sightings.page(SightingFilter(text=text), "date", True, 0, 100)
        if self.around:
            near = SightingFilter(
                date_from=self.around - timedelta(days=1), date_to=self.around + timedelta(days=1)
            )
            found = self.ctx.sightings.page(near, "date", True, 0, 100)
            if found:
                return found
        return self.ctx.sightings.page(SightingFilter(), "date", True, 0, 50)

    def _fill(self) -> None:
        self.list.clear()
        for s in self._sightings():
            item = QListWidgetItem(
                swatch(self.ctx.catalogue.category(s.category_id), self.theme.tokens, 18),
                describe(s),
            )
            item.setData(Qt.ItemDataRole.UserRole, s.id)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self.list.addItem("No sightings found")
            self.list.item(0).setFlags(Qt.ItemFlag.NoItemFlags)
        self._sync()

    def _sync(self) -> None:
        item = self.list.currentItem()
        self.chosen = item.data(Qt.ItemDataRole.UserRole) if item else None
        self.buttons.button(QDialogButtonBox.StandardButton.Ok).setEnabled(self.chosen is not None)
