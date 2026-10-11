"""Sightings: every record in a fast, sortable, filterable table."""

from __future__ import annotations

from PySide6.QtCore import QAbstractTableModel, QModelIndex, QRect, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QKeySequence, QPainter, QShortcut
from PySide6.QtWidgets import (
    QAbstractItemView,
    QDialog,
    QDialogButtonBox,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QStackedWidget,
    QStyle,
    QStyledItemDelegate,
    QStyleOptionViewItem,
    QTableView,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.domain.counting import format_count
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import Sighting
from wildlife.ui.components.common import EmptyState, Segmented, button
from wildlife.ui.components.filter_bar import FilterBar
from wildlife.ui.components.species_picker import SpeciesPicker
from wildlife.ui.components.visuals import fmt_date, plural, swatch
from wildlife.ui.pages.outings_list import OutingsList
from wildlife.ui.theme.manager import ThemeManager
from wildlife.ui.theme.tokens import FONT_SCI

PAGE_SIZE = 200
COLUMNS = [  # (title, sort key or None)
    ("Species", "species"),
    ("Date", "date"),
    ("Time", None),
    ("Place", "place"),
    ("Count", "count"),
    ("Evidence", None),
    ("Photos", None),
]


class SightingTableModel(QAbstractTableModel):
    """Loads sightings a page at a time as you scroll (fine for 100,000+ records)."""

    def __init__(self, ctx: AppContext) -> None:
        super().__init__()
        self.ctx = ctx
        self.filter = SightingFilter()
        self.sort_key, self.descending = "date", True
        self.rows: list[Sighting] = []
        self.total = 0

    def reload(self, flt: SightingFilter | None = None) -> None:
        if flt is not None:
            self.filter = flt
        self.beginResetModel()
        self.total = self.ctx.sightings.totals(self.filter)[0]
        self.rows = self.ctx.sightings.page(
            self.filter, self.sort_key, self.descending, 0, PAGE_SIZE
        )
        self.endResetModel()

    # ---- Qt model API ------------------------------------------------------
    def rowCount(self, parent=QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self.rows)

    def columnCount(self, parent=QModelIndex()) -> int:  # noqa: B008
        return len(COLUMNS)

    def canFetchMore(self, parent) -> bool:
        return len(self.rows) < self.total

    def fetchMore(self, parent) -> None:
        more = self.ctx.sightings.page(
            self.filter, self.sort_key, self.descending, len(self.rows), PAGE_SIZE
        )
        if more:
            self.beginInsertRows(QModelIndex(), len(self.rows), len(self.rows) + len(more) - 1)
            self.rows += more
            self.endInsertRows()

    def headerData(self, section, orientation, role=Qt.ItemDataRole.DisplayRole):
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.DisplayRole:
            return COLUMNS[section][0]
        if orientation == Qt.Orientation.Horizontal and role == Qt.ItemDataRole.TextAlignmentRole:
            return (
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
                if section == 4
                else None
            )
        return None

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        s = self.rows[index.row()]
        col = index.column()
        if role == Qt.ItemDataRole.UserRole:
            return s
        if role == Qt.ItemDataRole.DisplayRole:
            return [
                s.display_name,
                fmt_date(s.observed_date),
                s.observed_time or "–",
                s.place_name or ("Map position" if s.has_location else "No location"),
                format_count(s.count, s.count_qualifier),
                s.evidence.label
                + ("" if s.identification.value == "certain" else f" · {s.identification.label}"),
                plural(s.photo_count, "photo") if s.photo_count else "",
            ][col]
        if role == Qt.ItemDataRole.TextAlignmentRole and col == 4:
            return int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        if role == Qt.ItemDataRole.ToolTipRole and col == 3 and not s.has_location:
            return "Add a place or position when you can"
        return None

    def sort(self, column: int, order=Qt.SortOrder.AscendingOrder) -> None:
        key = COLUMNS[column][1]
        if key is None:
            return
        self.sort_key, self.descending = key, order == Qt.SortOrder.DescendingOrder
        self.reload()


class SpeciesDelegate(QStyledItemDelegate):
    """Draws: [category swatch] Common name  Scientific name (italic serif)."""

    def __init__(self, ctx: AppContext, theme: ThemeManager) -> None:
        super().__init__()
        self.ctx, self.theme = ctx, theme

    def paint(self, painter: QPainter, option: QStyleOptionViewItem, index) -> None:
        s: Sighting = index.data(Qt.ItemDataRole.UserRole)
        self.initStyleOption(option, index)
        option.text = ""
        style = option.widget.style() if option.widget else None
        if style:
            style.drawControl(QStyle.ControlElement.CE_ItemViewItem, option, painter, option.widget)
        t = self.theme.tokens
        rect = option.rect.adjusted(8, 0, -6, 0)
        sw = swatch(self.ctx.catalogue.category(s.category_id), t, 18)
        painter.drawPixmap(rect.left(), rect.center().y() - 9, sw)
        x = rect.left() + 28
        painter.save()
        bold = QFont(option.font)
        bold.setWeight(QFont.Weight.DemiBold)
        painter.setFont(bold)
        painter.setPen(option.palette.color(option.palette.ColorRole.Text))
        name = s.common_name or s.scientific_name
        width = painter.fontMetrics().horizontalAdvance(name)
        painter.drawText(
            QRect(x, rect.top(), rect.right() - x, rect.height()),
            int(Qt.AlignmentFlag.AlignVCenter),
            name,
        )
        if s.common_name:
            sci = QFont(FONT_SCI)
            sci.setItalic(True)
            sci.setPixelSize(13)
            painter.setFont(sci)
            painter.setPen(QColor(t.text_3))
            painter.drawText(
                QRect(
                    x + width + 8, rect.top(), max(0, rect.right() - x - width - 8), rect.height()
                ),
                int(Qt.AlignmentFlag.AlignVCenter),
                s.scientific_name,
            )
        painter.restore()

    def sizeHint(self, option, index) -> QSize:
        return QSize(260, 36)


class SightingsPage(QWidget):
    open_sighting = Signal(int)
    add_requested = Signal()
    toast = Signal(str, object)  # message, undo callable or None

    def __init__(self, ctx: AppContext, theme: ThemeManager) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.ctx, self.theme = ctx, theme
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 16)
        v.setSpacing(14)

        head = QHBoxLayout()
        title = QLabel("Sightings")
        title.setObjectName("PageTitle")
        head.addWidget(title)
        head.addSpacing(12)
        self.tabs = Segmented([("sightings", "All sightings"), ("outings", "Outings")], "sightings")
        self.tabs.changed.connect(self.show_tab)
        head.addWidget(self.tabs)
        head.addStretch(1)
        head.addWidget(
            button(
                "Export…",
                "secondary",
                "download",
                theme,
                lambda: self.toast.emit("Export arrives in a later phase", None),
            )
        )
        head.addWidget(button("Add sighting", "primary", "plus", theme, self.add_requested.emit))
        v.addLayout(head)

        # "All sightings" tab
        body = QWidget()
        bv = QVBoxLayout(body)
        bv.setContentsMargins(0, 0, 0, 0)
        bv.setSpacing(14)
        self.filter_bar = FilterBar(ctx, theme)
        self.filter_bar.changed.connect(self._filter_changed)
        bv.addWidget(self.filter_bar)

        self.bulk = QFrame()
        self.bulk.setObjectName("BulkBar")
        bh = QHBoxLayout(self.bulk)
        bh.setContentsMargins(14, 6, 8, 6)
        self.bulk_label = QLabel()
        self.bulk_label.setObjectName("BulkLabel")
        bh.addWidget(self.bulk_label, 1)
        change = QPushButton("Change species…")
        change.clicked.connect(self._change_species)
        delete = QPushButton("Delete")
        delete.clicked.connect(self.delete_selected)
        clear = QPushButton("Clear selection")
        clear.clicked.connect(lambda: self.table.clearSelection())
        for b in (change, delete, clear):
            b.setProperty("variant", "bulk")
            bh.addWidget(b)
        self.bulk.hide()
        bv.addWidget(self.bulk)

        self.model = SightingTableModel(ctx)
        self.table = QTableView()
        self.table.setObjectName("SightingTable")
        self.table.setModel(self.model)
        self.table.setItemDelegateForColumn(0, SpeciesDelegate(ctx, theme))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.table.setSortingEnabled(True)
        self.table.horizontalHeader().setSortIndicator(1, Qt.SortOrder.DescendingOrder)
        self.table.verticalHeader().hide()
        self.table.verticalHeader().setDefaultSectionSize(38)
        self.table.setShowGrid(False)
        self.table.setWordWrap(False)
        self.table.setAlternatingRowColors(False)
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setHighlightSections(False)
        header.setDefaultAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        for col, width in ((1, 140), (2, 64), (3, 190), (4, 80), (5, 150), (6, 70)):
            header.resizeSection(col, width)
        self.table.doubleClicked.connect(
            lambda idx: self.open_sighting.emit(self.model.rows[idx.row()].id)
        )
        self.table.selectionModel().selectionChanged.connect(self._selection_changed)
        QShortcut(QKeySequence(Qt.Key.Key_Return), self.table, activated=self._open_current)
        QShortcut(QKeySequence(Qt.Key.Key_Delete), self.table, activated=self.delete_selected)

        self.empty_all = EmptyState(
            theme,
            "list",
            "No sightings yet",
            "Sightings you add appear here. You can sort, filter and edit many at once.",
            [button("Add sighting", "primary", "plus", theme, self.add_requested.emit)],
        )
        self.empty_filtered = EmptyState(
            theme,
            "search",
            "No sightings match these filters",
            "Try a wider date range or fewer categories.",
            [
                button(
                    "Clear filters",
                    "secondary",
                    None,
                    None,
                    lambda: self.filter_bar.set_filter(SightingFilter()),
                )
            ],
        )
        self.stack = QStackedWidget()
        for w in (self.table, self._top(self.empty_all), self._top(self.empty_filtered)):
            self.stack.addWidget(w)
        bv.addWidget(self.stack, 1)
        self.footer = QLabel()
        self.footer.setProperty("role", "muted")
        bv.addWidget(self.footer)

        # "Outings" tab
        self.outings = OutingsList(ctx, theme)
        self.tab_stack = QStackedWidget()
        self.tab_stack.addWidget(body)
        self.tab_stack.addWidget(self.outings)
        v.addWidget(self.tab_stack, 1)
        self.refresh()

    def show_tab(self, key: str) -> None:
        self.tabs.set_current(key)
        self.tab_stack.setCurrentIndex(0 if key == "sightings" else 1)
        if key == "outings":
            self.outings.refresh()

    @staticmethod
    def _top(widget: QWidget) -> QWidget:
        holder = QWidget()
        hv = QVBoxLayout(holder)
        hv.setContentsMargins(0, 0, 0, 0)
        hv.addWidget(widget)
        hv.addStretch(1)
        return holder

    # ---- behaviour ----------------------------------------------------------
    def set_filter(self, flt: SightingFilter) -> None:
        self.show_tab("sightings")
        self.filter_bar.set_filter(flt)

    def _filter_changed(self, flt: SightingFilter) -> None:
        self.model.reload(flt)
        self._update_states()

    def refresh(self) -> None:
        if self.tab_stack.currentIndex() == 1:
            self.outings.refresh()
        selected = {s.id for s in self.selected()}
        self.model.reload()
        self._update_states()
        if selected:
            for row, s in enumerate(self.model.rows):
                if s.id in selected:
                    self.table.selectRow(row)

    def _update_states(self) -> None:
        if self.model.total:
            self.stack.setCurrentIndex(0)
        else:
            self.stack.setCurrentIndex(2 if not self.model.filter.is_empty else 1)
        sightings, species = self.ctx.sightings.totals(self.model.filter)
        self.footer.setText(
            f"{plural(sightings, 'sighting')} · {plural(species, 'species', 'species')}"
            + ("" if self.model.filter.is_empty else " match these filters")
            + "   ·   Double-click to open · Delete to move to the recycle bin"
        )
        self._selection_changed()

    def selected(self) -> list[Sighting]:
        rows = {i.row() for i in self.table.selectionModel().selectedRows()}
        return [self.model.rows[r] for r in sorted(rows) if r < len(self.model.rows)]

    def _selection_changed(self, *_) -> None:
        n = len(self.table.selectionModel().selectedRows())
        self.bulk.setVisible(n > 1)
        self.bulk_label.setText(f"{plural(n, 'sighting')} selected")

    def _open_current(self) -> None:
        index = self.table.currentIndex()
        if index.isValid():
            self.open_sighting.emit(self.model.rows[index.row()].id)

    def delete_selected(self) -> None:
        chosen = self.selected()
        if not chosen:
            return
        undo = self.ctx.sightings.delete([s.id for s in chosen])
        name = chosen[0].display_name if len(chosen) == 1 else plural(len(chosen), "sighting")
        self.toast.emit(f"{name} moved to the recycle bin", undo.run)

    def _change_species(self) -> None:
        chosen = self.selected()
        dialog = QDialog(self)
        dialog.setWindowTitle(f"Change species for {plural(len(chosen), 'sighting')}")
        dialog.setMinimumWidth(420)
        dv = QVBoxLayout(dialog)
        picker = SpeciesPicker(self.ctx.catalogue, self.theme)
        dv.addWidget(QLabel("New species"))
        dv.addWidget(picker)
        note = QLabel("You can undo this straight afterwards.")
        note.setProperty("role", "help")
        dv.addWidget(note)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dv.addWidget(buttons)
        picker.focus()
        if dialog.exec() and picker.taxon is not None:
            undo = self.ctx.sightings.change_species([s.id for s in chosen], picker.taxon.id)
            self.toast.emit(
                f"{plural(len(chosen), 'sighting')} changed to {picker.taxon.display_name}",
                undo.run,
            )
