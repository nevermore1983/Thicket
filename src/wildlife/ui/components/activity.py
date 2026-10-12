"""A year of days as a strip of small squares (weeks across, Monday to Sunday down)."""

from __future__ import annotations

import math
from datetime import date, timedelta

from PySide6.QtCore import QEvent, QPointF, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QSizePolicy, QToolTip, QWidget

from wildlife.domain.dates import MONTHS, fmt_date
from wildlife.ui.calendar.year_view import ramp_level, ramp_thresholds
from wildlife.ui.components.visuals import plural
from wildlife.ui.theme.manager import ThemeManager

LABEL_W = 26  # room for 'Mon', 'Wed', 'Fri'
HEAD_H = 16  # room for month names
GAP = 3


class ActivityStrip(QWidget):
    day_clicked = Signal(object)  # date

    def __init__(self, theme: ThemeManager) -> None:
        super().__init__()
        self.theme = theme
        self.counts: dict[date, int] = {}
        self.year = date.today().year
        self.today = date.today()
        self._thresholds: list[int] = []
        self._hover: date | None = None
        self.setMouseTracking(True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Activity this year")
        theme.changed.connect(self.update)

    def set_counts(self, year: int, counts: dict[date, int], today: date) -> None:
        self.year, self.counts, self.today = year, counts, today
        self._thresholds = ramp_thresholds(counts.values())
        days = sum(1 for n in counts.values() if n)
        self.setAccessibleDescription(
            f"{year}: {plural(sum(counts.values()), 'sighting')} on {plural(days, 'day')}"
        )
        self._resize()
        self.update()

    def _start(self) -> date:
        first = date(self.year, 1, 1)
        return first - timedelta(days=first.weekday())  # the Monday on or before 1 Jan

    def _weeks(self) -> int:
        return math.ceil(((date(self.year, 12, 31) - self._start()).days + 1) / 7)

    def _cell(self) -> float:
        return max(6.0, min(14.0, (self.width() - LABEL_W) / self._weeks() - GAP))

    def _resize(self) -> None:
        self.setFixedHeight(int(HEAD_H + 7 * (self._cell() + GAP)))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._resize()

    def sizeHint(self) -> QSize:
        return QSize(800, self.height())

    def _rect(self, day: date) -> QRectF:
        offset = (day - self._start()).days
        week, weekday = divmod(offset, 7)
        size = self._cell()
        return QRectF(LABEL_W + week * (size + GAP), HEAD_H + weekday * (size + GAP), size, size)

    def day_at(self, pos: QPointF) -> date | None:
        size = self._cell()
        week = int((pos.x() - LABEL_W) // (size + GAP))
        weekday = int((pos.y() - HEAD_H) // (size + GAP))
        if pos.x() < LABEL_W or pos.y() < HEAD_H or not 0 <= weekday < 7:
            return None
        day = self._start() + timedelta(days=week * 7 + weekday)
        return (
            day
            if day.year == self.year and self._rect(day).adjusted(-1, -1, 1, 1).contains(pos)
            else None
        )

    def paintEvent(self, _event) -> None:
        t = self.theme.tokens
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        small = QFont(self.font())
        small.setPixelSize(10)
        p.setFont(small)
        p.setPen(QColor(t.text_3))
        for weekday, name in ((0, "Mon"), (2, "Wed"), (4, "Fri")):
            r = self._rect(self._start() + timedelta(days=weekday))
            p.drawText(
                QRectF(0, r.top() - 2, LABEL_W - 4, r.height() + 4),
                int(Qt.AlignmentFlag.AlignVCenter),
                name,
            )
        for month in range(1, 13):
            r = self._rect(date(self.year, month, 1))
            p.drawText(
                QRectF(r.left(), 0, 40, HEAD_H - 2),
                int(Qt.AlignmentFlag.AlignVCenter),
                MONTHS[month - 1],
            )
        day = date(self.year, 1, 1)
        while day.year == self.year:
            r = self._rect(day)
            radius = max(1.5, r.width() / 5)
            if day > self.today:
                p.setPen(QPen(QColor(t.border), 1))
                p.setBrush(Qt.BrushStyle.NoBrush)
            else:
                p.setPen(Qt.PenStyle.NoPen)
                p.setBrush(QColor(t.ramp[ramp_level(self.counts.get(day, 0), self._thresholds)]))
            p.drawRoundedRect(r, radius, radius)
            ring = t.accent if day == self.today else t.text if day == self._hover else None
            if ring:
                p.setPen(QPen(QColor(ring), 1.5))
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRoundedRect(r.adjusted(-1.5, -1.5, 1.5, 1.5), radius + 1, radius + 1)
            day += timedelta(days=1)
        p.end()

    def mouseMoveEvent(self, event) -> None:
        day = self.day_at(event.position())
        if day != self._hover:
            self._hover = day
            self.setCursor(Qt.CursorShape.PointingHandCursor if day else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, _event) -> None:
        self._hover = None
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        day = self.day_at(event.position())
        if event.button() == Qt.MouseButton.LeftButton and day:
            self.day_clicked.emit(day)

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.ToolTip:
            day = self.day_at(QPointF(e.pos()))
            if day:
                n = self.counts.get(day, 0)
                text = f"<b>{n:,}</b> {'sighting' if n == 1 else 'sightings'}<br>{fmt_date(day)}"
                QToolTip.showText(e.globalPos(), text + "<br><i>Click to open the day</i>", self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)
