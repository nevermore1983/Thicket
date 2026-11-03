"""A heat table: a grid of cells shaded by how many (months by years, say)."""

from __future__ import annotations

from dataclasses import dataclass, field

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen, QPixmap

from wildlife.ui.components.charts.base import Chart, chart_font
from wildlife.ui.theme.manager import ThemeManager


# ---- heat table ------------------------------------------------------------------------
@dataclass
class HeatRow:
    label: str
    values: list[int]
    icon: QPixmap | None = None
    key: object = None
    extra: dict = field(default_factory=dict)


class HeatTable(Chart):
    """Rows x columns of cells shaded by amount (one hue, light to dark), the number written in."""

    ROW = 30
    HEAD = 24

    def __init__(
        self, theme: ThemeManager, name: str, columns: list[str], long_columns: list[str]
    ) -> None:
        super().__init__(theme, name)
        self.columns, self.long_columns = columns, long_columns
        self.rows: list[HeatRow] = []
        self.unit = "sightings"

    def set_rows(self, rows: list[HeatRow]) -> None:
        self.rows = rows
        self.hover = None
        self.setFixedHeight(self.HEAD + max(1, len(rows)) * self.ROW)
        self.setAccessibleDescription(f"{len(rows)} rows by {len(self.columns)} columns")
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(640, self.height())

    def _label_width(self) -> float:
        fm = QFontMetrics(chart_font(self, 13))
        widest = max((fm.horizontalAdvance(r.label) for r in self.rows), default=0)
        return min(widest + 34, self.width() * 0.32)

    def _cell(self, index: int) -> QRectF:
        row, col = divmod(index, len(self.columns))
        label_w = self._label_width()
        w = (self.width() - label_w) / len(self.columns)
        return QRectF(label_w + col * w, self.HEAD + row * self.ROW, w, self.ROW).adjusted(
            1, 1, -1, -1
        )

    def _level(self, value: int) -> int:
        top = max((v for r in self.rows for v in r.values), default=0)
        if value <= 0 or top <= 0:
            return 0
        return min(6, 1 + int(5.999 * value / top))

    def mark_count(self) -> int:
        return len(self.rows) * len(self.columns)

    def mark_rect(self, index: int) -> QRectF:
        return self._cell(index)

    def mark_at(self, pos: QPointF) -> int | None:
        label_w = self._label_width()
        if pos.x() < label_w or pos.y() < self.HEAD:
            return None
        col = int((pos.x() - label_w) // ((self.width() - label_w) / len(self.columns)))
        row = int((pos.y() - self.HEAD) // self.ROW)
        if 0 <= row < len(self.rows) and 0 <= col < len(self.columns):
            return row * len(self.columns) + col
        return None

    def key(self, index: int):
        row, col = divmod(index, len(self.columns))
        r = self.rows[row]
        return None if r.key is None or not r.values[col] else (r.key, col + 1)

    def tooltip(self, index: int) -> str:
        row, col = divmod(index, len(self.columns))
        r = self.rows[row]
        hint = "<br><i>Click to see them</i>" if self.key(index) is not None else ""
        return f"<b>{r.values[col]:,}</b> {self.unit}<br>{r.label}, {self.long_columns[col]}{hint}"

    def table(self) -> tuple[list[str], list[list[str]]]:
        return ["", *self.long_columns], [
            [r.label] + [f"{v:,}" for v in r.values] for r in self.rows
        ]

    def paintEvent(self, _event) -> None:
        t = self.theme.tokens
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        small = chart_font(self, 11)
        label_font = chart_font(self, 13)
        fm = QFontMetrics(label_font)
        label_w = self._label_width()
        p.setFont(small)
        p.setPen(QColor(t.text_3))
        for col, name in enumerate(self.columns):
            cell = self._cell(col)
            p.drawText(
                QRectF(cell.left(), 0, cell.width(), self.HEAD),
                int(Qt.AlignmentFlag.AlignCenter),
                name,
            )
        for row, r in enumerate(self.rows):
            y = self.HEAD + row * self.ROW
            x = 0.0
            if r.icon is not None:
                p.drawPixmap(int(x), int(y + self.ROW / 2 - 8), r.icon)
                x += 22
            p.setFont(label_font)
            p.setPen(QColor(t.text))
            p.drawText(
                QRectF(x, y, label_w - x - 6, self.ROW),
                int(Qt.AlignmentFlag.AlignVCenter),
                fm.elidedText(r.label, Qt.TextElideMode.ElideRight, int(label_w - x - 6)),
            )
            p.setFont(small)
            for col, value in enumerate(r.values):
                index = row * len(self.columns) + col
                cell = self._cell(index)
                level = self._level(value)
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(t.ramp[level]))
                p.drawRoundedRect(cell, 3, 3)
                if value:
                    # ink by the fill's lightness so the number always reads
                    dark_fill = QColor(t.ramp[level]).lightnessF() < 0.55
                    p.setPen(QColor("#ffffff" if dark_fill else t.text))
                    p.drawText(cell, int(Qt.AlignmentFlag.AlignCenter), f"{value:,}")
                if index == self.hover:
                    p.setPen(QPen(QColor(t.text), 1.5))
                    p.setBrush(Qt.BrushStyle.NoBrush)
                    p.drawRoundedRect(cell.adjusted(0.5, 0.5, -0.5, -0.5), 3, 3)
        p.end()
