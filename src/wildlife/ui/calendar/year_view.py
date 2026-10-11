"""Year view: twelve painted mini months, each day shaded by how many sightings it had."""

from __future__ import annotations

import calendar as pycal
import math
from collections.abc import Iterable
from datetime import date

from PySide6.QtCore import QEvent, QPoint, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QHBoxLayout, QLabel, QSizePolicy, QToolTip, QWidget

from wildlife.domain.dates import MONTHS_LONG
from wildlife.services.calendar import DaySummary
from wildlife.ui.calendar.month_view import day_tooltip
from wildlife.ui.components.visuals import plural
from wildlife.ui.theme.manager import ThemeManager
from wildlife.ui.theme.tokens import RADIUS_LG

GAP = 12  # between mini months
PAD = 14  # inside a mini month
HEAD = 30  # mini month title row
CELL_GAP = 3
MIN_CARD_W = 160


def ramp_thresholds(counts: Iterable[int], steps: int = 6) -> list[int]:
    """Upper bounds for shades 1..steps, splitting the busy days into equal-sized groups.

    Equal groups (rather than equal steps up to the busiest day) stop one huge day
    making every other day look the same pale colour."""
    values = sorted(c for c in counts if c > 0)
    if not values:
        return []
    n = len(values)
    return [values[max(0, math.ceil(n * i / steps) - 1)] for i in range(1, steps + 1)]


def ramp_level(count: int, thresholds: list[int]) -> int:
    """0 for no sightings, else 1 (fewest) .. len(thresholds) (most)."""
    if count <= 0 or not thresholds:
        return 0
    return next((i for i, top in enumerate(thresholds, 1) if count <= top), len(thresholds))


class YearView(QWidget):
    day_clicked = Signal(object)  # date
    day_activated = Signal(object)  # date (double-click)
    month_clicked = Signal(object)  # first day of the month

    def __init__(self, theme: ThemeManager) -> None:
        super().__init__()
        self.theme = theme
        self.year = date.today().year
        self.today = date.today()
        self.selected: date | None = None
        self.days: dict[date, DaySummary] = {}
        self._thresholds: list[int] = []
        self._hover: date | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Year calendar")
        theme.changed.connect(self.update)

    def set_data(
        self, year: int, days: dict[date, DaySummary], today: date, selected: date | None
    ) -> None:
        self.year, self.days, self.today, self.selected = year, days, today, selected
        self._thresholds = ramp_thresholds(s.sightings for s in days.values())
        total = sum(s.sightings for s in days.values())
        self.setAccessibleDescription(
            f"{year}: {plural(total, 'sighting')} on {plural(len(days), 'day')}. "
            "Click a day to list it, or a month name to open that month."
        )
        self.updateGeometry()
        self.update()

    def month_totals(self) -> list[int]:
        totals = [0] * 12
        for d, s in self.days.items():
            totals[d.month - 1] += s.sightings
        return totals

    # ---- geometry -------------------------------------------------------------------
    def _columns(self, width: int | None = None) -> int:
        """6 x 2 months when there's room, so the whole year fits on screen; else 4, 3 or 2."""
        width = self.width() if width is None else width
        fits = width // MIN_CARD_W
        return next(c for c in (6, 4, 3, 2) if c <= fits) if fits >= 2 else 2

    def _card_size(self, width: int) -> tuple[float, float, float]:
        cols = self._columns(width)
        card_w = (width - GAP * (cols - 1)) / cols
        cell = (card_w - 2 * PAD - 6 * CELL_GAP) / 7
        card_h = HEAD + PAD + 6 * cell + 5 * CELL_GAP + PAD
        return card_w, card_h, cell

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        _, card_h, _ = self._card_size(width)
        rows = math.ceil(12 / self._columns(width))
        return math.ceil(rows * card_h + (rows - 1) * GAP) + 2

    def sizeHint(self) -> QSize:
        return QSize(900, self.heightForWidth(900))

    def resizeEvent(self, event) -> None:
        # Fixed vertical policy + height-for-width: keep the height in step with the width
        self.setFixedHeight(self.heightForWidth(self.width()))
        super().resizeEvent(event)

    def _card_rect(self, month: int) -> QRectF:
        card_w, card_h, _ = self._card_size(self.width())
        row, col = divmod(month - 1, self._columns())
        return QRectF(
            col * (card_w + GAP) + 0.5, row * (card_h + GAP) + 0.5, card_w - 1, card_h - 1
        )

    def _day_rect(self, day: date) -> QRectF:
        card = self._card_rect(day.month)
        _, _, cell = self._card_size(self.width())
        offset = date(day.year, day.month, 1).weekday() + day.day - 1
        row, col = divmod(offset, 7)
        return QRectF(
            card.left() + PAD + col * (cell + CELL_GAP),
            card.top() + HEAD + PAD / 2 + row * (cell + CELL_GAP),
            cell,
            cell,
        )

    def hit(self, pos: QPoint) -> tuple[int | None, date | None]:
        """(month, day) under the mouse; day is None over a title or a gap."""
        for month in range(1, 13):
            if self._card_rect(month).contains(pos):
                for d in range(1, pycal.monthrange(self.year, month)[1] + 1):
                    day = date(self.year, month, d)
                    if self._day_rect(day).adjusted(-1, -1, 1, 1).contains(pos):
                        return month, day
                return month, None
        return None, None

    # ---- painting ----------------------------------------------------------------------
    def paintEvent(self, _event) -> None:
        t = self.theme.tokens
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        title = QFont(self.font())
        title.setPixelSize(14)
        title.setWeight(QFont.Weight.DemiBold)
        caption = QFont(self.font())
        caption.setPixelSize(12)
        totals = self.month_totals()
        for month in range(1, 13):
            card = self._card_rect(month)
            p.setPen(QPen(QColor(t.border), 1))
            p.setBrush(QColor(t.surface))
            p.drawRoundedRect(card, RADIUS_LG, RADIUS_LG)
            head = QRectF(card.left() + PAD, card.top() + 8, card.width() - 2 * PAD, HEAD - 6)
            p.setFont(title)
            p.setPen(QColor(t.text))
            p.drawText(head, int(Qt.AlignmentFlag.AlignVCenter), MONTHS_LONG[month - 1])
            n = totals[month - 1]
            text = plural(n, "sighting") if n else "–"
            room = head.width() - QFontMetrics(title).horizontalAdvance(MONTHS_LONG[month - 1]) - 8
            if QFontMetrics(caption).horizontalAdvance(text) > room:
                text = f"{n:,}" if n else "–"  # narrow card: just the number
            p.setFont(caption)
            p.setPen(QColor(t.text_3))
            p.drawText(head, int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignRight), text)
            for d in range(1, pycal.monthrange(self.year, month)[1] + 1):
                self._paint_day(p, date(self.year, month, d))
        p.end()

    def _paint_day(self, p: QPainter, day: date) -> None:
        t = self.theme.tokens
        r = self._day_rect(day)
        s = self.days.get(day)
        radius = max(2.0, r.width() / 6)
        level = 0
        if day > self.today:
            p.setPen(QPen(QColor(t.border), 1))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(0.5, 0.5, -0.5, -0.5), radius, radius)
        else:
            level = ramp_level(s.sightings if s else 0, self._thresholds)
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.ramp[level]))
            p.drawRoundedRect(r, radius, radius)
        # Only lifers get a star here: nearly every busy day has a 'first of the year'
        if s and s.lifers and r.width() >= 12:
            p.setPen(QColor(t.accent_fg if level >= 4 else t.accent))
            star = QFont(self.font())
            star.setPixelSize(max(8, int(r.width() * 0.55)))
            p.setFont(star)
            p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), "★")
        ring = None
        if day == self.selected:
            ring = t.text
        elif day == self.today:
            ring = t.accent
        elif day == self._hover:
            ring = t.border_strong
        if ring:
            p.setPen(QPen(QColor(ring), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(-1.5, -1.5, 1.5, 1.5), radius + 1, radius + 1)

    # ---- interaction ---------------------------------------------------------------------
    def mouseMoveEvent(self, event) -> None:
        month, day = self.hit(event.position().toPoint())
        if day != self._hover:
            self._hover = day
            self.update()
        self.setCursor(Qt.CursorShape.PointingHandCursor if month else Qt.CursorShape.ArrowCursor)

    def leaveEvent(self, _event) -> None:
        self._hover = None
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        month, day = self.hit(event.position().toPoint())
        if day:
            self.day_clicked.emit(day)
        elif month:
            self.month_clicked.emit(date(self.year, month, 1))

    def mouseDoubleClickEvent(self, event) -> None:
        _, day = self.hit(event.position().toPoint())
        if day:
            self.day_activated.emit(day)

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.ToolTip:
            month, day = self.hit(e.pos())
            if day:
                text = day_tooltip(day, self.days.get(day))
            elif month:
                text = f"Open {MONTHS_LONG[month - 1]} {self.year}"
            else:
                text = ""
            QToolTip.showText(e.globalPos(), text, self) if text else QToolTip.hideText()
            return True
        return super().event(e)


class RampLegend(QWidget):
    """'Fewer ▢▢▢▢▢▢▢ More sightings per day'."""

    def __init__(
        self, theme: ThemeManager, star_text: str = "★ New species for your life list"
    ) -> None:
        super().__init__()
        self.theme = theme
        h = QHBoxLayout(self)
        h.setContentsMargins(0, 0, 0, 0)
        h.setSpacing(4)
        fewer, more = QLabel("Fewer"), QLabel("More sightings per day")
        self._squares = _Squares(theme)
        for w in (fewer, more):
            w.setProperty("role", "caption")
        h.addWidget(fewer)
        h.addWidget(self._squares)
        h.addWidget(more)
        h.addSpacing(16)
        star = QLabel(star_text)
        star.setProperty("role", "caption")
        h.addWidget(star)
        h.addStretch(1)


class _Squares(QWidget):
    def __init__(self, theme: ThemeManager) -> None:
        super().__init__()
        self.theme = theme
        self.setFixedSize(7 * 16, 14)
        theme.changed.connect(self.update)

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setPen(Qt.PenStyle.NoPen)
        for i, colour in enumerate(self.theme.tokens.ramp):
            p.setBrush(QColor(colour))
            p.drawRoundedRect(QRectF(i * 16 + 1, 1, 12, 12), 3, 3)
        p.end()
