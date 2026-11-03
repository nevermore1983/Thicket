"""What every chart shares: the Chart widget (hover, keyboard, tooltips, a table
version) and the drawing helpers. The rules are in charts/__init__.py."""

from __future__ import annotations

import math

from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
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


def chart_font(widget: QWidget, px: int, weight=QFont.Weight.Normal) -> QFont:
    f = QFont(widget.font())
    f.setPixelSize(px)
    f.setWeight(weight)
    return f


def bar_path(r: QRectF, horizontal: bool) -> QPainterPath:
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
