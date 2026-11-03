"""A step line: species added up over the year (cumulative)."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from PySide6.QtCore import QPointF, QRectF, QSize, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen

from wildlife.ui.components.charts.base import Chart, chart_font, nice_ticks
from wildlife.ui.theme.manager import ThemeManager


# ---- step line (cumulative) ------------------------------------------------------------
@dataclass
class Line:
    label: str
    points: list[tuple[int, int]]  # (x, y) steps: y holds until the next x
    emphasis: bool = True
    end: int | None = None  # last x to draw to (e.g. today); default: the axis end

    def value_at(self, x: int) -> int:
        value = 0
        for px, py in self.points:
            if px > x:
                break
            value = py
        return value


class StepLineChart(Chart):
    """Running totals over time; a crosshair finds the day, the tooltip lists every line."""

    PLOT_H = 220
    AXIS_W = 44
    AXIS_H = 22
    END_W = 96  # room for the end labels

    def __init__(self, theme: ThemeManager, name: str, unit: str = "species") -> None:
        super().__init__(theme, name)
        self.lines: list[Line] = []
        self.days = 365
        self.x_label: Callable[[int], str] = str
        self.x_ticks: list[tuple[int, str]] = []
        self.unit = unit
        self.setFixedHeight(self.PLOT_H + self.AXIS_H + 12)

    def set_lines(
        self,
        lines: list[Line],
        days: int,
        x_ticks: list[tuple[int, str]],
        x_label: Callable[[int], str],
    ) -> None:
        self.lines, self.days, self.x_ticks, self.x_label = lines, max(1, days), x_ticks, x_label
        self.hover = None
        ends = ", ".join(f"{ln.label}: {ln.points[-1][1] if ln.points else 0}" for ln in lines)
        self.setAccessibleDescription(f"Running total of {self.unit}. {ends}")
        self.update()

    def sizeHint(self) -> QSize:
        return QSize(600, self.height())

    def _plot(self) -> QRectF:
        return QRectF(self.AXIS_W, 10, self.width() - self.AXIS_W - self.END_W, self.PLOT_H)

    def _xy(self, x: float, y: float, top: int) -> QPointF:
        plot = self._plot()
        return QPointF(
            plot.left() + plot.width() * x / self.days,
            plot.bottom() - plot.height() * y / (top or 1),
        )

    def mark_count(self) -> int:
        return self.days + 1

    def mark_at(self, pos: QPointF) -> int | None:
        plot = self._plot()
        if not plot.adjusted(0, -10, 0, self.AXIS_H).contains(pos) or not self.lines:
            return None
        return max(0, min(self.days, round((pos.x() - plot.left()) / plot.width() * self.days)))

    def mark_rect(self, index: int) -> QRectF:
        x = self._xy(index, 0, 1).x()
        plot = self._plot()
        return QRectF(x - 2, plot.top(), 4, plot.height())

    def keyPressEvent(self, event) -> None:
        # Arrow keys move a week at a time along the timeline
        if event.key() in (Qt.Key.Key_Left, Qt.Key.Key_Right) and self.lines:
            current = self.hover if self.hover is not None else 0
            delta = 7 if event.key() == Qt.Key.Key_Right else -7
            self._set_hover(max(0, min(self.days, current + delta)))
            self._show_tip_for_focus()
            return
        super().keyPressEvent(event)

    def tooltip(self, index: int) -> str:
        rows = []
        for ln in self.lines:
            if ln.end is not None and index > ln.end:
                continue
            rows.append(f"<b>{ln.value_at(index):,}</b> {self.unit} · {ln.label}")
        return "<br>".join([*rows, self.x_label(index)])

    def table(self) -> tuple[list[str], list[list[str]]]:
        headers = ["Date"] + [ln.label for ln in self.lines]
        days = sorted({x for ln in self.lines for x, _ in ln.points})
        return headers, [
            [self.x_label(d)] + [f"{ln.value_at(d):,}" for ln in self.lines] for d in days
        ]

    def paintEvent(self, _event) -> None:
        t = self.theme.tokens
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        small = chart_font(self, 11)
        p.setFont(small)
        plot = self._plot()
        top_value = max((y for ln in self.lines for _, y in ln.points), default=0)
        ticks = nice_ticks(top_value)
        top = ticks[-1] or 1
        for tick in ticks:
            y = self._xy(0, tick, top).y()
            p.setPen(QPen(QColor(t.border), 1))
            p.drawLine(QPointF(plot.left(), y), QPointF(plot.right(), y))
            p.setPen(QColor(t.text_3))
            p.drawText(
                QRectF(0, y - 8, self.AXIS_W - 6, 16),
                int(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter),
                f"{tick:,}",
            )
        for x, label in self.x_ticks:
            px = self._xy(x, 0, top).x()
            p.drawText(
                QRectF(px - 30, plot.bottom() + 4, 60, 16), int(Qt.AlignmentFlag.AlignCenter), label
            )
        # context lines first, the line the chart is about last (on top)
        label_font = chart_font(self, 12, QFont.Weight.DemiBold)
        placed: list[float] = []
        for ln in sorted(self.lines, key=lambda ln: ln.emphasis):
            colour = self.data_colour if ln.emphasis else self.other_colour
            end = self.days if ln.end is None else min(ln.end, self.days)
            path = QPainterPath(self._xy(0, 0, top))
            value = 0
            for x, y in ln.points:
                if x > end:
                    break
                path.lineTo(self._xy(x, value, top))
                path.lineTo(self._xy(x, y, top))
                value = y
            last = self._xy(end, value, top)
            path.lineTo(last)
            pen = QPen(colour, 2)
            pen.setCapStyle(Qt.PenCapStyle.RoundCap)
            pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
            p.setPen(pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)
            # end dot with a surface ring, and a direct label in text colour
            p.setPen(QPen(QColor(t.surface), 2))
            p.setBrush(colour)
            p.drawEllipse(last, 4.5, 4.5)
            label_y = last.y()
            if any(abs(label_y - other) < 16 for other in placed):
                label_y += 16 if all(label_y >= o for o in placed) else -16
            placed.append(label_y)
            p.setFont(label_font)
            p.setPen(QColor(t.text if ln.emphasis else t.text_2))
            p.drawText(
                QRectF(last.x() + 9, label_y - 9, self.END_W, 18),
                int(Qt.AlignmentFlag.AlignVCenter),
                f"{ln.label} · {value:,}",
            )
        if self.hover is not None and self.lines:
            x = self._xy(self.hover, 0, top).x()
            p.setPen(QPen(QColor(t.text_3), 1))
            p.drawLine(QPointF(x, plot.top()), QPointF(x, plot.bottom()))
        p.end()
