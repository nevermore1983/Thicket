"""Reusable list rows and stat tiles."""

from __future__ import annotations

import html
from collections.abc import Callable

import shiboken6
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout

from wildlife.context import AppContext
from wildlife.domain.counting import format_count
from wildlife.domain.models import Sighting
from wildlife.ui.components.visuals import relative_day, rounded, swatch
from wildlife.ui.theme.icons import pixmap
from wildlife.ui.theme.manager import ThemeManager
from wildlife.ui.workers import run_in_background


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
        self.picture: QLabel | None = None
        if icon_pixmap is not None:
            self.picture = QLabel()
            self.picture.setPixmap(icon_pixmap)
            self.picture.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
            h.addWidget(self.picture)
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
    """The sighting's first photo as a rounded thumbnail if it's been made already, else
    its category swatch (see _fetch_picture for the rest)."""
    if s.cover_photo:
        photos = ctx.photos.for_sighting(s.id)
        thumb = ctx.photos.cached_thumbnail(photos[0], 256) if photos else None
        if thumb:
            return rounded(QPixmap(str(thumb)), size, 9)
    return swatch(ctx.catalogue.category(s.category_id), theme.tokens, size)


def _fetch_picture(ctx: AppContext, row: RowButton, s: Sighting, size: int) -> None:
    """A thumbnail not made yet is made in the background and swapped in when ready,
    so a list of many photographed sightings appears straight away."""
    if not s.cover_photo:
        return
    photos = ctx.photos.for_sighting(s.id)
    if not photos or ctx.photos.cached_thumbnail(photos[0], 256):
        return

    def ready(path) -> None:
        if path and shiboken6.isValid(row) and row.picture is not None:
            row.picture.setPixmap(rounded(QPixmap(str(path)), size, 9))

    run_in_background(lambda: ctx.photos.thumbnail(photos[0], 256), ready, lambda _e: None)


def _count_suffix(s: Sighting) -> str:
    if (s.count or 0) > 1 or s.count_qualifier.value != "exact":
        return f"  × {format_count(s.count, s.count_qualifier)}"
    return ""


def _where(s: Sighting) -> str:
    return s.where


def sighting_row(ctx: AppContext, theme: ThemeManager, s: Sighting, on_click) -> RowButton:
    category = ctx.catalogue.category(s.category_id)
    side = relative_day(s.observed_date, ctx.sightings._today()) + (
        f"\n{s.observed_time}" if s.observed_time else ""
    )
    row = RowButton(
        _picture(ctx, theme, s),
        f"{s.display_name}{_count_suffix(s)}",
        f"{_where(s)} · {category.name}",
        side,
        lambda: on_click(s.id),
    )
    _fetch_picture(ctx, row, s, 44)
    return row


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
    row = RowButton(
        _picture(ctx, theme, s, 40),
        title,
        f"{s.evidence.label} · {_where(s)}",
        s.observed_time or "–",
        lambda: on_click(s.id),
        rich=True,
    )
    _fetch_picture(ctx, row, s, 40)
    return row


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
