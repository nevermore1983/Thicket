"""Horizontal bars: top species, places and the like."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPixmap

from wildlife.ui.components.charts.base import BAR, Chart, bar_path, chart_font
from wildlife.ui.theme.manager import ThemeManager


# ---- horizontal bars ------------------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Bar:
    label: str
    value: int
    key: object = None  # what a click opens; None = not clickable
    icon: QPixmap | None = None  # e.g. a category swatch beside the label


class BarChart(Chart):
    """Ranked horizontal bars, one colour (the length carries the value)."""

    ROW = 28

    def __init__(self, theme: ThemeManager, name: str, unit: str = "sightings") -> None:
        super().__init__(theme, name)
        self.bars: list[Bar] = []
        self.unit = unit
        self.extra: tuple[str, list[int]] | None = None

    def set_bars(
        self,
        bars: list[Bar],
        unit: str | None = None,
        extra: tuple[str, list[int]] | None = None,  # another column for the table version
    ) -> None:
        self.bars = bars
        self.unit = unit or self.unit
        self.extra = extra
        self.hover = None
        self.setFixedHeight(max(self.ROW, len(bars) * self.ROW))
        top = ", ".join(f"{b.label} {b.value:,}" for b in bars[:3])
        self.setAccessibleDescription(f"{len(bars)} bars. Highest: {top}")
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(400, len(self.bars) * self.ROW)

    def _label_width(self) -> float:
        fm = QFontMetrics(chart_font(self, 13))
        widest = max((fm.horizontalAdvance(b.label) for b in self.bars), default=0)
        icons = 22 if any(b.icon for b in self.bars) else 0
        return min(widest + icons + 12, self.width() * 0.45)

    def _bar_rect(self, index: int) -> QRectF:
        label_w = self._label_width()
        value_w = 52
        top = max((b.value for b in self.bars), default=1) or 1
        width = (self.width() - label_w - value_w) * self.bars[index].value / top
        y = index * self.ROW + (self.ROW - BAR) / 2
        return QRectF(label_w, y, max(2.0, width), BAR)

    def mark_count(self) -> int:
        return len(self.bars)

    def mark_rect(self, index: int) -> QRectF:
        return QRectF(0, index * self.ROW, self.width(), self.ROW)

    def mark_at(self, pos: QPointF) -> int | None:
        index = int(pos.y() // self.ROW)
        return index if 0 <= index < len(self.bars) else None

    def key(self, index: int):
        return self.bars[index].key

    def tooltip(self, index: int) -> str:
        b = self.bars[index]
        hint = "<br><i>Click to see them</i>" if b.key is not None else ""
        return f"<b>{b.value:,}</b> {self.unit}<br>{b.label}{hint}"

    def table(self) -> tuple[list[str], list[list[str]]]:
        headers = ["", self.unit.capitalize()]
        rows = [[b.label, f"{b.value:,}"] for b in self.bars]
        if self.extra:
            headers.append(self.extra[0])
            rows = [[*row, f"{v:,}"] for row, v in zip(rows, self.extra[1], strict=True)]
        return headers, rows

    def paintEvent(self, _event) -> None:
        t = self.theme.tokens
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        label_font, value_font = chart_font(self, 13), chart_font(self, 12)
        fm = QFontMetrics(label_font)
        label_w = self._label_width()
        for i, b in enumerate(self.bars):
            row = self.mark_rect(i)
            if i == self.hover:
                p.fillRect(row, QColor(t.surface_2))
            x = 0.0
            if b.icon is not None:
                p.drawPixmap(int(x), int(row.center().y() - 8), b.icon)
                x += 22
            p.setFont(label_font)
            p.setPen(QColor(t.text))
            p.drawText(
                QRectF(x, row.top(), label_w - x - 8, row.height()),
                int(Qt.AlignmentFlag.AlignVCenter),
                fm.elidedText(b.label, Qt.TextElideMode.ElideRight, int(label_w - x - 8)),
            )
            bar = self._bar_rect(i)
            colour = self.data_colour.lighter(112) if i == self.hover else self.data_colour
            p.fillPath(bar_path(bar, True), colour)
            p.setFont(value_font)
            p.setPen(QColor(t.text_2))
            p.drawText(
                QRectF(bar.right() + 6, row.top(), 60, row.height()),
                int(Qt.AlignmentFlag.AlignVCenter),
                f"{b.value:,}",
            )
        self._focus_ring(p)
        p.end()
