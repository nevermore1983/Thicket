"""Places and My species: simple lists for now (maps and profiles come in later phases)."""

from __future__ import annotations

import html
from datetime import date

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QStackedWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.domain import geo
from wildlife.domain.filters import SightingFilter
from wildlife.ui.components.common import EmptyState, button
from wildlife.ui.components.visuals import fmt_date, plural, swatch
from wildlife.ui.theme.manager import ThemeManager


def _table(headers: list[str]) -> QTableWidget:
    table = QTableWidget(0, len(headers))
    table.setHorizontalHeaderLabels(headers)
    table.verticalHeader().hide()
    table.verticalHeader().setDefaultSectionSize(38)
    table.setShowGrid(False)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
    table.horizontalHeader().setHighlightSections(False)
    table.horizontalHeader().setDefaultAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter
    )
    table.setSortingEnabled(True)
    return table


class _NumberItem(QTableWidgetItem):
    """Sorts by number, not text."""

    def __init__(self, value: int, text: str | None = None) -> None:
        super().__init__(text if text is not None else f"{value:,}")
        self.setData(Qt.ItemDataRole.UserRole + 1, value)
        self.setTextAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)

    def __lt__(self, other) -> bool:
        return (self.data(Qt.ItemDataRole.UserRole + 1) or 0) < (
            other.data(Qt.ItemDataRole.UserRole + 1) or 0
        )


class _ListPage(QWidget):
    def __init__(
        self,
        title: str,
        subtitle: str,
        actions: list[QWidget],
        table: QTableWidget,
        empty: EmptyState,
    ) -> None:
        super().__init__()
        self.setObjectName("Page")
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 16)
        v.setSpacing(14)
        head = QHBoxLayout()
        titles = QVBoxLayout()
        t = QLabel(title)
        t.setObjectName("PageTitle")
        s = QLabel(subtitle)
        s.setObjectName("PageSubtitle")
        titles.addWidget(t)
        titles.addWidget(s)
        head.addLayout(titles, 1)
        for a in actions:
            head.addWidget(a)
        v.addLayout(head)
        self.stack = QStackedWidget()
        self.stack.addWidget(table)
        holder = QWidget()
        hv = QVBoxLayout(holder)
        hv.setContentsMargins(0, 0, 0, 0)
        hv.addWidget(empty)
        hv.addStretch(1)
        self.stack.addWidget(holder)
        v.addWidget(self.stack, 1)
        self.footer = QLabel()
        self.footer.setProperty("role", "muted")
        v.addWidget(self.footer)


class PlacesPage(_ListPage):
    edit_place = Signal(int)
    new_place = Signal()

    def __init__(self, ctx: AppContext, theme: ThemeManager) -> None:
        table = _table(["Place", "Sightings", "Species", "Last visit", "Grid reference"])
        empty = EmptyState(
            theme,
            "pin",
            "No places yet",
            "Save the spots you visit often, like your garden or a local reserve, to record faster.",
            [button("New place", "primary", "plus", theme, lambda: self.new_place.emit())],
        )
        super().__init__(
            "Places",
            "Saved locations you visit. Sightings inside a place's radius suggest it.",
            [button("New place", "primary", "plus", theme, lambda: self.new_place.emit())],
            table,
            empty,
        )
        self.ctx, self.theme, self.table = ctx, theme, table
        table.doubleClicked.connect(
            lambda idx: self.edit_place.emit(
                table.item(idx.row(), 0).data(Qt.ItemDataRole.UserRole)
            )
        )
        self.refresh()

    def refresh(self) -> None:
        places = self.ctx.places.all()
        usage = self.ctx.places.usage()
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(places))
        for row, p in enumerate(places):
            sightings, species, last = usage.get(p.id, (0, 0, None))
            name = QTableWidgetItem(("★ " if p.is_favourite else "") + p.name)
            name.setData(Qt.ItemDataRole.UserRole, p.id)
            self.table.setItem(row, 0, name)
            self.table.setItem(row, 1, _NumberItem(sightings))
            self.table.setItem(row, 2, _NumberItem(species))
            last_item = _NumberItem(
                date.fromisoformat(last).toordinal() if last else 0,
                fmt_date(date.fromisoformat(last), "medium") if last else "Never",
            )
            last_item.setTextAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
            self.table.setItem(row, 3, last_item)
            self.table.setItem(
                row,
                4,
                QTableWidgetItem(
                    geo.grid_ref_for(p.latitude, p.longitude, 1000)
                    or f"{p.latitude:.3f}, {p.longitude:.3f}"
                ),
            )
        self.table.setSortingEnabled(True)
        for col, width in ((1, 100), (2, 90), (3, 120), (4, 140)):
            self.table.horizontalHeader().resizeSection(col, width)
        self.stack.setCurrentIndex(0 if places else 1)
        self.footer.setText(
            f"{plural(len(places), 'place')} · double-click to edit" if places else ""
        )


class SpeciesPage(_ListPage):
    show_sightings = Signal(object)

    def __init__(self, ctx: AppContext, theme: ThemeManager) -> None:
        table = _table(["Species", "Category", "Sightings", "First seen", "Last seen"])
        empty = EmptyState(
            theme,
            "leaf",
            "Your species list is empty",
            "Each species you record is added here, with when you first and last saw it.",
        )
        super().__init__(
            "My species",
            "Your life list: certain identifications of wild animals, at species level.",
            [],
            table,
            empty,
        )
        self.ctx, self.theme, self.table = ctx, theme, table
        table.doubleClicked.connect(self._open)
        theme.changed.connect(self.refresh)
        self.refresh()

    def refresh(self) -> None:
        rows = self.ctx.stats.life_list()
        t = self.theme.tokens
        self.table.setSortingEnabled(False)
        self.table.setRowCount(len(rows))
        for i, r in enumerate(rows):
            category = self.ctx.catalogue.category(r.category_id)
            label = r.common_name or r.scientific_name
            name = QTableWidgetItem(swatch(category, t, 18), label)
            name.setData(Qt.ItemDataRole.UserRole, r.taxon_id)
            name.setToolTip(html.escape(r.scientific_name))
            self.table.setItem(i, 0, name)
            self.table.setItem(i, 1, QTableWidgetItem(category.name))
            self.table.setItem(i, 2, _NumberItem(r.sightings))
            first = _NumberItem(r.first_seen.toordinal(), fmt_date(r.first_seen, "medium"))
            last = _NumberItem(r.last_seen.toordinal(), fmt_date(r.last_seen, "medium"))
            for item in (first, last):
                item.setTextAlignment(
                    int(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
                )
            self.table.setItem(i, 3, first)
            self.table.setItem(i, 4, last)
        self.table.setSortingEnabled(True)
        for col, width in ((1, 190), (2, 90), (3, 130), (4, 130)):
            self.table.horizontalHeader().resizeSection(col, width)
        self.stack.setCurrentIndex(0 if rows else 1)
        self.footer.setText(
            f"{plural(len(rows), 'species', 'species')} on your life list · double-click to see "
            "the sightings"
            if rows
            else ""
        )

    def _open(self, index) -> None:
        taxon_id = self.table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
        self.show_sightings.emit(SightingFilter(taxon_ids=frozenset({taxon_id})))
