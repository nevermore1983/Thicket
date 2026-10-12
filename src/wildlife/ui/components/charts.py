"""Painted charts for the Statistics page and panels.

Rules (from the data-visualisation checklist in docs/04-ui-ux-design.md):
thin marks with 4 px rounded data-ends, hairline recessive gridlines, one y axis,
text in text colours (never the series colour), a hover tooltip on every mark where
the value leads, a legend whenever there are two series, keyboard access
(arrows + Enter), and a table version of every chart (`table()`).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from wildlife.ui.theme.manager import ThemeManager

BAR = 16  # bar / column thickness (the rules cap it at 24)
RADIUS = 4


def nice_ticks(top: float, count: int = 4) -> list[int]:
    """Round axis ticks from 0 that cover `top`: 0, 50, 100, 150 rather than 0, 47, 94..."""
    if top <= 0:
        return [0, 1]
    raw = top / count
    magnitude = 10 ** math.floor(math.log10(raw))
    step = next(m * magnitude for m in (1, 2, 2.5, 5, 10) if m * magnitude >= raw)
    step = max(1, round(step))
    return list(range(0, int(math.ceil(top / step) * step) + 1, step))


def _font(widget: QWidget, px: int, weight=QFont.Weight.Normal) -> QFont:
    f = QFont(widget.font())
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


def _bar_path(r: QRectF, horizontal: bool) -> QPainterPath:
    """A bar with a rounded data-end and a square end at the baseline."""
    path = QPainterPath()
    rad = min(RADIUS, (r.height() if horizontal else r.width()) / 2, r.width(), r.height())
    if horizontal:  # grows to the right
        path.moveTo(r.left(), r.top())
        path.lineTo(r.right() - rad, r.top())
        path.quadTo(r.right(), r.top(), r.right(), r.top() + rad)
        path.lineTo(r.right(), r.bottom() - rad)
        path.quadTo(r.right(), r.bottom(), r.right() - rad, r.bottom())
        path.lineTo(r.left(), r.bottom())
    else:  # grows upwards
        path.moveTo(r.left(), r.bottom())
        path.lineTo(r.left(), r.top() + rad)
        path.quadTo(r.left(), r.top(), r.left() + rad, r.top())
        path.lineTo(r.right() - rad, r.top())
        path.quadTo(r.right(), r.top(), r.right(), r.top() + rad)
        path.lineTo(r.right(), r.bottom())
    path.closeSubpath()
    return path


class Chart(QWidget):
    """Shared behaviour: theme, a hovered/focused mark, tooltips, clicks and keys."""

    clicked = Signal(object)  # the key of the mark (e.g. a category id)

    def __init__(self, theme: ThemeManager, name: str) -> None:
        super().__init__()
        self.theme = theme
        self.hover: int | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName(name)
        theme.changed.connect(self.update)

    @property
    def data_colour(self) -> QColor:
        return QColor(self.theme.tokens.ramp[4])

    @property
    def other_colour(self) -> QColor:
        return QColor(self.theme.tokens.text_3)

    # subclasses provide these
    def mark_count(self) -> int:
        return 0

    def mark_at(self, pos: QPointF) -> int | None:
        return None

    def mark_rect(self, index: int) -> QRectF:
        return QRectF()

    def tooltip(self, index: int) -> str:
        return ""

    def key(self, index: int):
        return None

    def table(self) -> tuple[list[str], list[list[str]]]:
        return [], []

    # interaction
    def _set_hover(self, index: int | None) -> None:
        if index != self.hover:
            self.hover = index
            self.update()

    def mouseMoveEvent(self, event) -> None:
        index = self.mark_at(event.position())
        self._set_hover(index)
        clickable = index is not None and self.key(index) is not None
        self.setCursor(
            Qt.CursorShape.PointingHandCursor if clickable else Qt.CursorShape.ArrowCursor
        )

    def leaveEvent(self, _event) -> None:
        if not self.hasFocus():
            self._set_hover(None)

    def mouseReleaseEvent(self, event) -> None:
        index = self.mark_at(event.position())
        if event.button() == Qt.MouseButton.LeftButton and index is not None:
            key = self.key(index)
            if key is not None:
                self.clicked.emit(key)

    def keyPressEvent(self, event) -> None:
        n = self.mark_count()
        if not n:
            return super().keyPressEvent(event)
        step = {Qt.Key.Key_Left: -1, Qt.Key.Key_Up: -1, Qt.Key.Key_Right: 1, Qt.Key.Key_Down: 1}
        if event.key() in step:
            current = self.hover if self.hover is not None else -1
            self._set_hover(max(0, min(n - 1, current + step[event.key()])))
            self._show_tip_for_focus()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.hover is not None:
            key = self.key(self.hover)
            if key is not None:
                self.clicked.emit(key)
        else:
            super().keyPressEvent(event)

    def _show_tip_for_focus(self) -> None:
        if self.hover is not None:
            centre = self.mark_rect(self.hover).center().toPoint()
            QToolTip.showText(self.mapToGlobal(centre), self.tooltip(self.hover), self)

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self._set_hover(None)

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.ToolTip:
            index = self.mark_at(QPointF(e.pos()))
            if index is not None:
                QToolTip.showText(e.globalPos(), self.tooltip(index), self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)

    def _focus_ring(self, p: QPainter) -> None:
        if self.hasFocus() and self.hover is not None:
            p.setPen(QPen(QColor(self.theme.tokens.text), 1.5, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(self.mark_rect(self.hover).adjusted(-3, -3, 3, 3), 5, 5)


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
        fm = QFontMetrics(_font(self, 13))
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
        label_font, value_font = _font(self, 13), _font(self, 12)
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
            p.fillPath(_bar_path(bar, True), colour)
            p.setFont(value_font)
            p.setPen(QColor(t.text_2))
            p.drawText(
                QRectF(bar.right() + 6, row.top(), 60, row.height()),
                int(Qt.AlignmentFlag.AlignVCenter),
                f"{b.value:,}",
            )
        self._focus_ring(p)
        p.end()


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
        small = _font(self, 11)
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
                p.fillPath(_bar_path(self._column(i, s), False), colour)
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
        small = _font(self, 11)
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
        label_font = _font(self, 12, QFont.Weight.DemiBold)
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
        fm = QFontMetrics(_font(self, 13))
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
        small = _font(self, 11)
        label_font = _font(self, 13)
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
