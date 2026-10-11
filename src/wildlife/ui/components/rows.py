"""Reusable list rows and stat tiles."""

from __future__ import annotations

import html
from collections.abc import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from wildlife.context import AppContext
from wildlife.domain.counting import format_count
from wildlife.domain.models import Sighting
from wildlife.ui.components.visuals import relative_day, rounded, swatch
from wildlife.ui.theme.icons import pixmap
from wildlife.ui.theme.manager import ThemeManager


class StatTile(QFrame):
    def __init__(self, label: str, value: str, delta: str = "", good: bool = False) -> None:
        super().__init__()
        self.setObjectName("Tile")
        v = QVBoxLayout(self)
        v.setContentsMargins(18, 14, 18, 16)
        v.setSpacing(4)
        top = QLabel(label)
        top.setObjectName("TileLabel")
        value_label = QLabel(value)
        value_label.setObjectName("TileValue")
        v.addWidget(top)
        v.addWidget(value_label)
        if delta:
            d = QLabel(delta)
            d.setProperty("role", "deltaUp" if good else "delta")
            d.setWordWrap(True)
            v.addWidget(d)
        v.addStretch(1)


class RowButton(QFrame):
    """A clickable row: icon/thumbnail · title + meta · side text.

    A QFrame rather than a QPushButton: a button doesn't grow to fit a layout
    inside it, which made rows overlap. Keyboard: Tab to it, Enter/Space to open."""

    clicked = Signal()

    def __init__(
        self,
        icon_pixmap: QPixmap | None,
        title: str,
        meta: str,
        side: str = "",
        on_click: Callable[[], None] | None = None,
        rich: bool = False,
    ) -> None:
        super().__init__()
        self.setObjectName("RowButton")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        h = QHBoxLayout(self)
        h.setContentsMargins(6, 6, 6, 6)
        h.setSpacing(12)
        if icon_pixmap is not None:
            pic = QLabel()
            pic.setPixmap(icon_pixmap)
            pic.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            h.addWidget(pic)
        texts = QVBoxLayout()
        texts.setSpacing(1)
        t = QLabel(title)
        t.setObjectName("RowTitle")
        if rich:
            t.setTextFormat(Qt.TextFormat.RichText)
        m = QLabel(meta)
        m.setObjectName("RowMeta")
        for w in (t, m):
            w.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            texts.addWidget(w)
        h.addLayout(texts, 1)
        if side:
            s = QLabel(side)
            s.setObjectName("RowSide")
            s.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            s.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            h.addWidget(s)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover)  # lets the stylesheet show :hover
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus if on_click else Qt.FocusPolicy.NoFocus)
        if on_click:
            self.clicked.connect(on_click)
        else:
            self.setCursor(Qt.CursorShape.ArrowCursor)
        self.setAccessibleName(f"{title}, {meta}")

    def mouseReleaseEvent(self, event) -> None:
        if event.button() == Qt.MouseButton.LeftButton and self.rect().contains(
            event.position().toPoint()
        ):
            self.clicked.emit()
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter, Qt.Key.Key_Space):
            self.clicked.emit()
            return
        super().keyPressEvent(event)


def _picture(ctx: AppContext, theme: ThemeManager, s: Sighting, size: int = 44) -> QPixmap:
    """The sighting's first photo as a rounded thumbnail, else its category swatch."""
    category = ctx.catalogue.category(s.category_id)
    if s.cover_photo:
        photos = ctx.photos.for_sighting(s.id)
        thumb = ctx.photos.thumbnail(photos[0], 256) if photos else None
        if thumb:
            return rounded(QPixmap(str(thumb)), size, 9)
    return swatch(category, theme.tokens, size)


def _count_suffix(s: Sighting) -> str:
    if (s.count or 0) > 1 or s.count_qualifier.value != "exact":
        return f"  × {format_count(s.count, s.count_qualifier)}"
    return ""


def _where(s: Sighting) -> str:
    return s.place_name or ("Map position" if s.has_location else "No location")


def sighting_row(ctx: AppContext, theme: ThemeManager, s: Sighting, on_click) -> RowButton:
    category = ctx.catalogue.category(s.category_id)
    side = relative_day(s.observed_date, ctx.sightings._today()) + (
        f"\n{s.observed_time}" if s.observed_time else ""
    )
    return RowButton(
        _picture(ctx, theme, s),
        f"{s.display_name}{_count_suffix(s)}",
        f"{_where(s)} · {category.name}",
        side,
        lambda: on_click(s.id),
    )


FIRST_BADGES = {"lifer": "★ Lifer", "year": "★ First of the year"}


def day_row(
    ctx: AppContext, theme: ThemeManager, s: Sighting, mark: str | None, on_click
) -> RowButton:
    """A sighting within a day's list: time on the right, a badge for lifers and year firsts."""
    title = html.escape(f"{s.display_name}{_count_suffix(s)}")
    if mark in FIRST_BADGES:
        title += (
            f'&nbsp;&nbsp;<span style="color:{theme.tokens.accent}; font-weight:600;">'
            f"{FIRST_BADGES[mark]}</span>"
        )
    return RowButton(
        _picture(ctx, theme, s, 40),
        title,
        f"{s.evidence.label} · {_where(s)}",
        s.observed_time or "–",
        lambda: on_click(s.id),
        rich=True,
    )


def attention_row(
    theme: ThemeManager,
    icon_name: str,
    title: str,
    meta: str,
    tone: str,
    on_click: Callable[[], None] | None,
) -> RowButton:
    t = theme.tokens
    colour = {"warning": t.warning, "good": t.good_text}.get(tone, t.text_2)
    return RowButton(pixmap(icon_name, colour, 20), title, meta, "›" if on_click else "", on_click)
