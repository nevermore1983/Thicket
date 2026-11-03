"""Columns, one or two series: months, hours, years."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFontMetrics, QPainter, QPen

from wildlife.ui.components.charts.base import BAR, Chart, bar_path, chart_font, nice_ticks
from wildlife.ui.theme.manager import ThemeManager


# ---- columns (one or two series) -------------------------------------------------------
@dataclass(frozen=True, slots=True)
class Series:
    label: str
    values: list[int]
    emphasis: bool = True  # the series the chart is about (data colour) vs context (grey)


class ColumnChart(Chart):
    """Columns along an axis (hours, months). With two series they're grouped side by side."""

    PLOT_H = 170
    AXIS_W = 40
    AXIS_H = 22
    LEGEND_H = 24

    def __init__(
        self,
        theme: ThemeManager,
        name: str,
        labels: list[str],
        unit: str = "sightings",
        tick_every: int = 1,
        long_labels: list[str] | None = None,
    ) -> None:
        Chart.__init__(self, theme, name)
        self.labels, self.unit, self.tick_every = labels, unit, tick_every
        self.long_labels = long_labels or labels
        self.series: list[Series] = []
        self.keys: list[object] = [None] * len(labels)
        self.setFixedHeight(self.PLOT_H + self.AXIS_H + 8)

    def set_series(self, series: list[Series], keys: list | None = None) -> None:
        self.series = series
        self.keys = keys or [None] * len(self.labels)
        legend = self.LEGEND_H if len(series) > 1 else 0
        self.setFixedHeight(self.PLOT_H + self.AXIS_H + 8 + legend)
        totals = ", ".join(f"{s.label}: {sum(s.values):,}" for s in series)
        self.setAccessibleDescription(f"{len(self.labels)} columns. {totals}")
        self.hover = None
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(500, self.height())

    def _top(self) -> int:
        return max((v for s in self.series for v in s.values), default=0)

    def _plot(self) -> QRectF:
        legend = self.LEGEND_H if len(self.series) > 1 else 0
        return QRectF(self.AXIS_W, legend + 6, self.width() - self.AXIS_W - 4, self.PLOT_H)

    def _slot(self, index: int) -> QRectF:
        plot = self._plot()
        w = plot.width() / len(self.labels)
        return QRectF(plot.left() + index * w, plot.top(), w, plot.height())

    def _column(self, index: int, s: int) -> QRectF:
        slot = self._slot(index)
        n = len(self.series)
        thickness = min(BAR, (slot.width() - 6 - 2 * (n - 1)) / n)
        group = n * thickness + 2 * (n - 1)
        x = slot.center().x() - group / 2 + s * (thickness + 2)
        top = nice_ticks(self._top())[-1] or 1
        h = slot.height() * self.series[s].values[index] / top
        return QRectF(x, slot.bottom() - h, thickness, h)

    def mark_count(self) -> int:
        return len(self.labels)

    def mark_rect(self, index: int) -> QRectF:
        return self._slot(index)

    def mark_at(self, pos: QPointF) -> int | None:
        plot = self._plot()
        if not plot.adjusted(0, -6, 0, self.AXIS_H).contains(pos):
            return None
        index = int((pos.x() - plot.left()) // (plot.width() / len(self.labels)))
        return index if 0 <= index < len(self.labels) else None

    def key(self, index: int):
        return self.keys[index]

    def tooltip(self, index: int) -> str:
        if len(self.series) == 1:
            lines = f"<b>{self.series[0].values[index]:,}</b> {self.unit}"
        else:
            lines = "<br>".join(f"<b>{s.values[index]:,}</b> {s.label}" for s in self.series)
        hint = "<br><i>Click to see them</i>" if self.keys[index] is not None else ""
        return f"{lines}<br>{self.long_labels[index]}{hint}"

    def table(self) -> tuple[list[str], list[list[str]]]:
        headers = [""] + (
            [self.unit.capitalize()] if len(self.series) == 1 else [s.label for s in self.series]
        )
        rows = [
            [self.long_labels[i]] + [f"{s.values[i]:,}" for s in self.series]
            for i in range(len(self.labels))
        ]
        return headers, rows

    def paintEvent(self, _event) -> None:
        t = self.theme.tokens
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        small = chart_font(self, 11)
        p.setFont(small)
        plot = self._plot()
        ticks = nice_ticks(self._top())
        # legend (two series): a swatch beside each label, in text colour
        if len(self.series) > 1:
            x = plot.left()
            for s in self.series:
                colour = self.data_colour if s.emphasis else self.other_colour
                p.fillRect(QRectF(x, 6, 10, 10), colour)
                p.setPen(QColor(t.text_2))
                p.drawText(QRectF(x + 15, 0, 120, 22), int(Qt.AlignmentFlag.AlignVCenter), s.label)
                x += 30 + QFontMetrics(small).horizontalAdvance(s.label)
        # gridlines and y ticks
        for tick in ticks:
            y = plot.bottom() - plot.height() * tick / (ticks[-1] or 1)
            p.setPen(QPen(QColor(t.border), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(t.text_3))
            p.drawText(
                QRectF(0, y - 8, self.AXIS_W - 6, 16),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                f"{tick:,}",
            )
        # columns
        for i in range(len(self.labels)):
            if i == self.hover:
                p.fillRect(self._slot(i), QColor(t.surface_2))
            for s, series in enumerate(self.series):
                if series.values[i] <= 0:
                    continue
                colour = self.data_colour if series.emphasis else self.other_colour
                if i == self.hover:
                    colour = colour.lighter(112)
                p.fillPath(bar_path(self._column(i, s), False), colour)
            if i % self.tick_every == 0:
                p.setPen(QColor(t.text_3))
                slot = self._slot(i)
                p.drawText(
                    QRectF(slot.left() - 10, plot.bottom() + 4, slot.width() + 20, 16),
                    int(Qt.AlignmentFlag.AlignCenter),
                    self.labels[i],
                )
        self._focus_ring(p)
        p.end()
