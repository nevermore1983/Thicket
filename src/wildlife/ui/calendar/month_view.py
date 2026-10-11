"""Month view: a painted grid of days with counts, category dots and the day's headline species.

Painting 42 cells directly is faster and more precise than 42 widgets with
labels inside, and keeps every cell exactly the same size.
"""

from __future__ import annotations

import math
from datetime import date, timedelta

from PySide6.QtCore import QEvent, QPoint, QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QToolTip, QWidget

from wildlife.context import AppContext
from wildlife.domain.dates import DAYS, MONTHS_LONG, fmt_date, month_end, week_start
from wildlife.services.calendar import DaySummary
from wildlife.ui.components.visuals import category_colours, plural
from wildlife.ui.theme.manager import ThemeManager
from wildlife.ui.theme.tokens import RADIUS_LG

HEADER_H = 32
MIN_ROW_H = 92


def day_tooltip(day: date, s: DaySummary | None) -> str:
    if s is None:
        return f"{fmt_date(day, 'full')}\nNo sightings"
    lines = [
        fmt_date(day, "full"),
        f"{plural(s.sightings, 'sighting')} · {plural(s.species, 'species', 'species')}",
    ]
    if s.lifers:
        lines.append(f"★ {plural(s.lifers, 'new species', 'new species')} for your life list")
    if s.year_firsts - s.lifers > 0:
        lines.append(f"★ {s.year_firsts - s.lifers} first of the year")
    return "\n".join(lines)


def cell_lines(s: DaySummary, room: int) -> list[tuple[str, bool]]:
    """What to write in a day cell with space for `room` lines: (text, starred) pairs.

    New species come first. If not everything fits, the last line says how many more."""
    if room <= 0:
        return []
    if room == 1:
        more = f" +{s.species - 1}" if s.species > 1 else ""
        return [(f"{s.names[0]}{more}", s.new_names > 0)]
    lines = [(name, i < s.new_names) for i, name in enumerate(s.names)]
    if s.species <= min(room, len(lines)):
        return lines
    keep = min(room - 1, len(lines))
    return [*lines[:keep], (f"+{s.species - keep} more", False)]


class MonthView(QWidget):
    day_clicked = Signal(object)  # date
    day_activated = Signal(object)  # date (double-click)

    def __init__(self, ctx: AppContext, theme: ThemeManager) -> None:
        super().__init__()
        self.ctx, self.theme = ctx, theme
        self.month = date.today().replace(day=1)
        self.today = date.today()
        self.selected: date | None = None
        self.days: dict[date, DaySummary] = {}
        self._hover: date | None = None
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.setAccessibleName("Month calendar")
        theme.changed.connect(self.update)

    # ---- data -----------------------------------------------------------------
    def set_data(
        self, month: date, days: dict[date, DaySummary], today: date, selected: date | None
    ) -> None:
        self.month, self.days, self.today, self.selected = (
            month.replace(day=1),
            days,
            today,
            selected,
        )
        weeks = self.weeks()
        self.setMinimumHeight(HEADER_H + weeks * MIN_ROW_H)
        total = sum(s.sightings for d, s in days.items() if d.month == self.month.month)
        self.setAccessibleDescription(
            f"{MONTHS_LONG[self.month.month - 1]} {self.month.year}: {plural(total, 'sighting')}. "
            "Click a day to list it."
        )
        self.update()

    def first_cell(self) -> date:
        return week_start(self.month)

    def weeks(self) -> int:
        return math.ceil((self.month.weekday() + month_end(self.month).day) / 7)

    def range(self) -> tuple[date, date]:
        """First and last day drawn (includes the edges of the neighbouring months)."""
        start = self.first_cell()
        return start, start + timedelta(days=self.weeks() * 7 - 1)

    # ---- geometry ---------------------------------------------------------------
    def _cell_rect(self, index: int) -> QRectF:
        w = (self.width() - 1) / 7
        h = (self.height() - HEADER_H - 1) / self.weeks()
        row, col = divmod(index, 7)
        return QRectF(col * w, HEADER_H + row * h, w, h)

    def day_at(self, pos: QPoint) -> date | None:
        if pos.y() < HEADER_H or not self.rect().contains(pos):
            return None
        w = (self.width() - 1) / 7
        h = (self.height() - HEADER_H - 1) / self.weeks()
        col = min(6, int(pos.x() / w))
        row = min(self.weeks() - 1, int((pos.y() - HEADER_H) / h))
        return self.first_cell() + timedelta(days=row * 7 + col)

    # ---- painting -----------------------------------------------------------------
    def paintEvent(self, _event) -> None:
        t = self.theme.tokens
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        outer = QRectF(0.5, 0.5, self.width() - 1, self.height() - 1)
        clip = QPainterPath()
        clip.addRoundedRect(outer, RADIUS_LG, RADIUS_LG)
        p.setClipPath(clip)
        p.fillRect(self.rect(), QColor(t.surface))

        base = QFont(self.font())
        small = QFont(base)
        small.setPixelSize(12)
        small.setWeight(QFont.Weight.DemiBold)
        p.setFont(small)
        p.setPen(QColor(t.text_2))
        w = (self.width() - 1) / 7
        for i, name in enumerate(DAYS):
            p.drawText(
                QRectF(i * w + 10, 0, w - 10, HEADER_H),
                int(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft),
                name,
            )
        start = self.first_cell()
        for i in range(self.weeks() * 7):
            self._paint_cell(p, start + timedelta(days=i), self._cell_rect(i))

        # grid lines on top so cell fills don't cover them
        p.setPen(QPen(QColor(t.border), 1))
        p.drawLine(0, HEADER_H, self.width(), HEADER_H)
        h = (self.height() - HEADER_H - 1) / self.weeks()
        for r in range(1, self.weeks()):
            y = round(HEADER_H + r * h) + 0.5
            p.drawLine(QPointF(0, y), QPointF(self.width(), y))
        for c in range(1, 7):
            x = round(c * w) + 0.5
            p.drawLine(QPointF(x, HEADER_H), QPointF(x, self.height()))
        p.setClipping(False)
        p.setPen(QPen(QColor(t.border), 1))
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRoundedRect(outer, RADIUS_LG, RADIUS_LG)

        # selection and keyboard focus ring last, above the grid lines
        if self.selected:
            index = (self.selected - start).days
            if 0 <= index < self.weeks() * 7:
                pen = QPen(QColor(t.accent), 2)
                p.setPen(pen)
                p.drawRoundedRect(self._cell_rect(index).adjusted(2, 2, -2, -2), 6, 6)
        p.end()

    def _paint_cell(self, p: QPainter, day: date, r: QRectF) -> None:
        t = self.theme.tokens
        other = day.month != self.month.month
        if day == self._hover:
            p.fillRect(r, QColor(t.surface_2))
        elif other:
            p.fillRect(r, QColor(t.bg))
        s = self.days.get(day)

        # day number (a filled pill for today)
        number = QFont(self.font())
        number.setPixelSize(13)
        number.setWeight(QFont.Weight.DemiBold)
        p.setFont(number)
        fm = QFontMetrics(number)
        text = str(day.day)
        num_rect = QRectF(r.left() + 8, r.top() + 7, fm.horizontalAdvance(text) + 14, 20)
        if day == self.today:
            p.setPen(Qt.PenStyle.NoPen)
            p.setBrush(QColor(t.accent))
            p.drawRoundedRect(num_rect, 10, 10)
            p.setPen(QColor(t.accent_fg))
        else:
            num_rect.translate(-6, 0)
            p.setPen(QColor(t.text_3 if other else t.text))
        p.drawText(num_rect, int(Qt.AlignmentFlag.AlignCenter), text)
        if s is None:
            return

        # count badge, top right
        badge_font = QFont(self.font())
        badge_font.setPixelSize(11)
        badge_font.setWeight(QFont.Weight.DemiBold)
        p.setFont(badge_font)
        count = f"{s.sightings:,}"
        bw = QFontMetrics(badge_font).horizontalAdvance(count) + 14
        badge = QRectF(r.right() - bw - 8, r.top() + 8, bw, 18)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(t.surface_3))
        p.drawRoundedRect(badge, 9, 9)
        p.setPen(QColor(t.text_2))
        p.drawText(badge, int(Qt.AlignmentFlag.AlignCenter), count)

        # up to four category dots
        x = r.left() + 9
        p.setPen(Qt.PenStyle.NoPen)
        for cid in s.category_ids[:4]:
            fill, _ = category_colours(self.ctx.catalogue.category(cid), t)
            p.setBrush(QColor(fill))
            p.drawEllipse(QRectF(x, r.top() + 34, 8, 8))
            x += 11

        # species names under the dots, as many as fit, with a star for firsts
        line = QFont(self.font())
        line.setPixelSize(12)
        p.setFont(line)
        fm = QFontMetrics(line)
        line_h = fm.height() + 1
        top = r.top() + 48
        room = int((r.bottom() - 6 - top) // line_h)
        for i, (text, starred) in enumerate(cell_lines(s, room)):
            y = top + i * line_h
            x, width = r.left() + 9, r.width() - 18
            if starred:
                p.setPen(QColor(t.accent))
                p.drawText(QRectF(x, y, 13, fm.height()), int(Qt.AlignmentFlag.AlignVCenter), "★")
                x, width = x + 13, width - 13
            p.setPen(QColor(t.text_3 if other or text.startswith("+") else t.text_2))
            p.drawText(
                QRectF(x, y, width, fm.height()),
                int(Qt.AlignmentFlag.AlignVCenter),
                fm.elidedText(text, Qt.TextElideMode.ElideRight, int(width)),
            )

    # ---- interaction ------------------------------------------------------------------
    def mouseMoveEvent(self, event) -> None:
        day = self.day_at(event.position().toPoint())
        if day != self._hover:
            self._hover = day
            self.setCursor(Qt.CursorShape.PointingHandCursor if day else Qt.CursorShape.ArrowCursor)
            self.update()

    def leaveEvent(self, _event) -> None:
        self._hover = None
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        day = self.day_at(event.position().toPoint())
        if event.button() == Qt.MouseButton.LeftButton and day:
            self.day_clicked.emit(day)

    def mouseDoubleClickEvent(self, event) -> None:
        day = self.day_at(event.position().toPoint())
        if day:
            self.day_activated.emit(day)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.day_clicked.emit(self.selected or self.today)
            return
        super().keyPressEvent(event)

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.ToolTip:
            day = self.day_at(e.pos())
            if day:
                QToolTip.showText(e.globalPos(), day_tooltip(day, self.days.get(day)), self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)
