"""The species field: type a few letters, get ranked suggestions, pick with Enter."""

from __future__ import annotations

import html

from PySide6.QtCore import QEvent, QObject, Qt, QTimer, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wildlife.domain.models import Taxon
from wildlife.services.species_catalogue import SpeciesCatalogue
from wildlife.ui.components.visuals import swatch
from wildlife.ui.theme.icons import icon
from wildlife.ui.theme.manager import ThemeManager
from wildlife.ui.theme.tokens import FONT_SCI

MAX_SUGGESTIONS = 8


def species_html(taxon: Taxon, sci_colour: str) -> str:
    """'Robin <i>Erithacus rubecula</i>' with the scientific name in the field-guide serif."""
    sci = (
        f"<span style=\"font-family:'{FONT_SCI}', Georgia, serif; font-style:italic; color:{sci_colour};\">"
        f"{html.escape(taxon.scientific_name)}</span>"
    )
    if taxon.common_name:
        return f"<b>{html.escape(taxon.common_name)}</b>&nbsp; {sci}"
    return (
        f"<span style=\"font-family:'{FONT_SCI}', Georgia, serif; font-style:italic;\"><b>"
        f"{html.escape(taxon.scientific_name)}</b></span>"
    )


class SpeciesPicker(QWidget):
    chosen = Signal(object)  # Taxon, or None when cleared

    def __init__(self, catalogue: SpeciesCatalogue, theme: ThemeManager) -> None:
        super().__init__()
        self._catalogue, self._theme = catalogue, theme
        self._taxon: Taxon | None = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)

        self.edit = QLineEdit()
        self.edit.setObjectName("SpeciesInput")
        self.edit.setPlaceholderText("Start typing a common or scientific name…")
        self.edit.setAccessibleName("Species")
        self.edit.installEventFilter(self)
        layout.addWidget(self.edit)

        self._chosen_box = QFrame()
        self._chosen_box.setObjectName("ChosenSpecies")
        chosen = QHBoxLayout(self._chosen_box)
        chosen.setContentsMargins(8, 6, 6, 6)
        self._chosen_swatch = QLabel()
        self._chosen_label = QLabel()
        self._chosen_label.setTextFormat(Qt.TextFormat.RichText)
        self._change = QPushButton()
        self._change.setProperty("variant", "ghost")
        self._change.setFixedWidth(32)
        self._change.setToolTip("Change species")
        self._change.setAccessibleName("Change species")
        self._change.clicked.connect(self.clear)
        chosen.addWidget(self._chosen_swatch)
        chosen.addWidget(self._chosen_label, 1)
        chosen.addWidget(self._change)
        self._chosen_box.hide()
        layout.addWidget(self._chosen_box)

        self.list = QListWidget()
        self.list.setObjectName("Suggestions")
        self.list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.list.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.list.itemClicked.connect(lambda item: self._pick(item.data(Qt.ItemDataRole.UserRole)))
        self.list.hide()
        layout.addWidget(self.list)

        self._timer = QTimer(self, singleShot=True, interval=80)  # wait for a pause in typing
        self._timer.timeout.connect(self._refresh)
        self.edit.textEdited.connect(lambda _: self._timer.start())
        theme.changed.connect(self._paint)
        self._paint()

    # ---- public -------------------------------------------------------------
    @property
    def taxon(self) -> Taxon | None:
        return self._taxon

    def set_taxon(self, taxon: Taxon | None) -> None:
        self._taxon = taxon
        if taxon is None:
            self._chosen_box.hide()
            self.edit.show()
            self.edit.clear()
        else:
            self.edit.hide()
            self.list.hide()
            self._chosen_box.show()
            self._paint()

    def clear(self) -> None:
        self.set_taxon(None)
        self.chosen.emit(None)
        self.edit.setFocus()

    def focus(self) -> None:
        (self.edit if self._taxon is None else self._change).setFocus()

    # ---- internals ----------------------------------------------------------
    def _paint(self) -> None:
        t = self._theme.tokens
        self._change.setIcon(icon("x", t.text_2, 16))
        if self._taxon:
            category = self._catalogue.category(self._taxon.category_id)
            self._chosen_swatch.setPixmap(swatch(category, t, 18))
            self._chosen_label.setText(species_html(self._taxon, t.text_2))

    def _refresh(self) -> None:
        text = self.edit.text().strip()
        self.list.clear()
        if not text:
            self.list.hide()
            return
        t = self._theme.tokens
        matches = self._catalogue.search(text, MAX_SUGGESTIONS)
        for match in matches:
            item = QListWidgetItem()
            item.setData(Qt.ItemDataRole.UserRole, match.taxon)
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(8, 4, 8, 4)
            sw = QLabel()
            sw.setPixmap(swatch(self._catalogue.category(match.taxon.category_id), t, 16))
            label = QLabel(species_html(match.taxon, t.text_2))
            label.setTextFormat(Qt.TextFormat.RichText)
            h.addWidget(sw)
            h.addWidget(label, 1)
            if match.uses:
                uses = QLabel(f"seen {match.uses}×")
                uses.setProperty("role", "caption")
                h.addWidget(uses)
            elif match.matched_name not in (match.taxon.common_name, match.taxon.scientific_name):
                also = QLabel(f"also “{match.matched_name}”")
                also.setProperty("role", "caption")
                h.addWidget(also)
            item.setSizeHint(row.sizeHint())
            self.list.addItem(item)
            self.list.setItemWidget(item, row)
        if not matches:
            empty = QListWidgetItem(
                f"No species called “{text}”. Check the spelling, or try the scientific name."
            )
            empty.setFlags(Qt.ItemFlag.NoItemFlags)
            self.list.addItem(empty)
        self.list.setCurrentRow(0 if matches else -1)
        rows = self.list.count()
        self.list.setFixedHeight(sum(self.list.sizeHintForRow(i) for i in range(rows)) + 6)
        self.list.show()

    def _pick(self, taxon: Taxon | None) -> None:
        if taxon is None:
            return
        self.set_taxon(taxon)
        self.chosen.emit(taxon)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if obj is self.edit and event.type() == QEvent.Type.KeyPress and self.list.isVisible():
            key = event.key()
            if key in (Qt.Key.Key_Down, Qt.Key.Key_Up):
                row = self.list.currentRow() + (1 if key == Qt.Key.Key_Down else -1)
                self.list.setCurrentRow(max(0, min(self.list.count() - 1, row)))
                return True
            if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not event.modifiers():
                if self._timer.isActive():  # Enter pressed before the list refreshed
                    self._timer.stop()
                    self._refresh()
                item = self.list.currentItem()
                if item is not None and item.data(Qt.ItemDataRole.UserRole) is not None:
                    self._pick(item.data(Qt.ItemDataRole.UserRole))
                return True
            if key == Qt.Key.Key_Escape:
                self.list.hide()
                return True
        return super().eventFilter(obj, event)
