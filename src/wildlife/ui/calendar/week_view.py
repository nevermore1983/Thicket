"""Week view: seven columns, each listing that day's sightings as small cards (untimed first)."""

from __future__ import annotations

from datetime import date, timedelta

from PySide6.QtCore import QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from wildlife.context import AppContext
from wildlife.domain.dates import DAYS
from wildlife.domain.models import Sighting
from wildlife.services.calendar import Firsts
from wildlife.ui.components.common import clear_layout
from wildlife.ui.components.rows import FIRST_BADGES
from wildlife.ui.components.visuals import category_colours, plural
from wildlife.ui.theme.manager import ThemeManager

MAX_CARDS = 30  # per column; the rest are one click away in the day list


class WeekCard(QWidget):
    """One sighting: category colour bar, name, time and place, ★ for firsts."""

    clicked = Signal()

    def __init__(self, ctx: AppContext, theme: ThemeManager, s: Sighting, mark: str | None):
        super().__init__()
        self.ctx, self.theme, self.s, self.mark = ctx, theme, s, mark
        self.setFixedHeight(48)
        self.setMinimumWidth(110)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)
        self.meta = f"{s.observed_time or 'Time unknown'} · {s.where}"
        self.setToolTip(
            f"{s.display_name}\n{self.meta}" + (f"\n{FIRST_BADGES[mark]}" if mark else "")
        )
        self.setAccessibleName(f"{s.display_name}, {self.meta}")

    def sizeHint(self) -> QSize:
        return QSize(150, 48)

    def paintEvent(self, _event) -> None:
        t = self.theme.tokens
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        r = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        hovered = self.underMouse()
        p.setPen(
            QPen(QColor(t.accent if self.hasFocus() else t.border), 2 if self.hasFocus() else 1)
        )
        p.setBrush(QColor(t.surface_2 if hovered else t.surface))
        p.drawRoundedRect(r, 8, 8)
        fill, _ = category_colours(self.ctx.catalogue.category(self.s.category_id), t)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(fill))
        p.drawRoundedRect(QRectF(r.left() + 3, r.top() + 6, 3, r.height() - 12), 1.5, 1.5)

        right = r.right() - 8
        if self.mark:
            p.setPen(QColor(t.accent))
            p.setFont(self.font())
            p.drawText(
                QRectF(right - 14, r.top() + 6, 14, 18), int(Qt.AlignmentFlag.AlignCenter), "★"
            )
            right -= 16
        bold = QFont(self.font())
        bold.setPixelSize(13)
        bold.setWeight(QFont.Weight.DemiBold)
        p.setFont(bold)
        p.setPen(QColor(t.text))
        width = int(right - r.left() - 12)
        p.drawText(
            QRectF(r.left() + 12, r.top() + 6, width, 18),
            int(Qt.AlignmentFlag.AlignVCenter),
            QFontMetrics(bold).elidedText(self.s.display_name, Qt.TextElideMode.ElideRight, width),
        )
        small = QFont(self.font())
        small.setPixelSize(12)
        p.setFont(small)
        p.setPen(QColor(t.text_2))
        width = int(r.right() - 8 - r.left() - 12)
        p.drawText(
            QRectF(r.left() + 12, r.top() + 25, width, 17),
            int(Qt.AlignmentFlag.AlignVCenter),
            QFontMetrics(small).elidedText(self.meta, Qt.TextElideMode.ElideRight, width),
        )
        p.end()

    def enterEvent(self, _event) -> None:
        self.update()

    def leaveEvent(self, _event) -> None:
        self.update()

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


class WeekView(QWidget):
    open_sighting = Signal(int)
    day_clicked = Signal(object)  # date
    add_on = Signal(object)  # date

    def __init__(self, ctx: AppContext, theme: ThemeManager) -> None:
        super().__init__()
        self.ctx, self.theme = ctx, theme
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)
        self.setAccessibleName("Week calendar")

    def set_data(
        self,
        start: date,
        by_day: dict[date, list[Sighting]],
        firsts: Firsts,
        today: date,
        selected: date | None,
    ) -> None:
        clear_layout(self._layout)
        for i in range(7):
            day = start + timedelta(days=i)
            self._layout.addWidget(
                self._column(day, by_day.get(day, []), firsts, day == today, day == selected), 1
            )

    def _column(
        self, day: date, items: list[Sighting], firsts: Firsts, is_today: bool, is_selected: bool
    ) -> QFrame:
        col = QFrame()
        col.setObjectName("WeekCol")
        col.setProperty("selected", is_selected)
        col.setMinimumWidth(124)
        v = QVBoxLayout(col)
        v.setContentsMargins(8, 8, 8, 10)
        v.setSpacing(6)
        head = QPushButton(f"{DAYS[day.weekday()]} {day.day}")
        head.setObjectName("WeekColHead")
        head.setProperty("today", is_today)
        head.setCursor(Qt.CursorShape.PointingHandCursor)
        head.setToolTip("List this day")
        head.clicked.connect(lambda: self.day_clicked.emit(day))
        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.addWidget(head)
        row.addStretch(1)
        if items:
            n = QLabel(f"{len(items):,}")
            n.setProperty("role", "caption")
            n.setToolTip(plural(len(items), "sighting"))
            row.addWidget(n)
        v.addLayout(row)
        for s in items[:MAX_CARDS]:
            card = WeekCard(self.ctx, self.theme, s, firsts.mark(s.id))
            card.clicked.connect(lambda sid=s.id: self.open_sighting.emit(sid))
            v.addWidget(card)
        if len(items) > MAX_CARDS:
            more = QPushButton(f"+ {len(items) - MAX_CARDS} more")
            more.setProperty("variant", "link")
            more.clicked.connect(lambda: self.day_clicked.emit(day))
            v.addWidget(more, 0, Qt.AlignmentFlag.AlignLeft)
        v.addStretch(1)
        if not items:
            add = QPushButton("+ Add")
            add.setProperty("variant", "link")
            add.setToolTip("Add a sighting on this date")
            add.clicked.connect(lambda: self.add_on.emit(day))
            v.addWidget(add, 0, Qt.AlignmentFlag.AlignLeft)
        return col
