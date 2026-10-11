"""Small drawn things: category swatches, photo thumbnails, formatted dates."""

from __future__ import annotations

from datetime import date
from functools import lru_cache

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QPainter, QPainterPath, QPixmap

from wildlife.domain.models import Category
from wildlife.ui.theme.icons import pixmap as icon_pixmap
from wildlife.ui.theme.tokens import Tokens

DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
MONTHS_LONG = (
    "January",
    "February",
    "March",
    "April",
    "May",
    "June",
    "July",
    "August",
    "September",
    "October",
    "November",
    "December",
)


def category_colours(category: Category, tokens: Tokens) -> tuple[str, str]:
    """(fill, icon ink) for a category in the current theme.

    Category ids 1-8 are the validated colour slots; anything else uses the
    stored colour (user-added categories reuse one of the eight slots)."""
    slot = category.id if 1 <= category.id <= 8 else 0
    if category.is_fallback:
        slot = 0
    return tokens.categories[slot], tokens.category_ink[slot]


@lru_cache(maxsize=256)
def _swatch(fill: str, ink: str, icon: str, size: int, ratio: float) -> QPixmap:
    pm = QPixmap(round(size * ratio), round(size * ratio))
    pm.fill(Qt.GlobalColor.transparent)
    pm.setDevicePixelRatio(ratio)
    p = QPainter(pm)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    p.setPen(Qt.PenStyle.NoPen)
    p.setBrush(QColor(fill))
    p.drawEllipse(QRectF(0, 0, size, size))
    inner = round(size * 0.62)
    p.drawPixmap(
        round((size - inner) / 2), round((size - inner) / 2), icon_pixmap(icon, ink, inner, 2.2)
    )
    p.end()
    return pm


def swatch(category: Category, tokens: Tokens, size: int = 18) -> QPixmap:
    fill, ink = category_colours(category, tokens)
    app = QGuiApplication.instance()
    return _swatch(fill, ink, category.icon, size, app.devicePixelRatio() if app else 1.0)


def rounded(pm: QPixmap, size: int, radius: int = 8) -> QPixmap:
    """Crop a photo to a rounded square thumbnail."""
    app = QGuiApplication.instance()
    ratio = app.devicePixelRatio() if app else 1.0
    out = QPixmap(round(size * ratio), round(size * ratio))
    out.fill(Qt.GlobalColor.transparent)
    out.setDevicePixelRatio(ratio)
    scaled = pm.scaled(
        round(size * ratio),
        round(size * ratio),
        Qt.AspectRatioMode.KeepAspectRatioByExpanding,
        Qt.TransformationMode.SmoothTransformation,
    )
    scaled.setDevicePixelRatio(ratio)
    p = QPainter(out)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    path = QPainterPath()
    path.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    p.setClipPath(path)
    p.drawPixmap(
        round((size - scaled.width() / ratio) / 2),
        round((size - scaled.height() / ratio) / 2),
        scaled,
    )
    p.end()
    return out


def fmt_date(d: date, style: str = "short") -> str:
    """UK-style dates: short 'Sun 11 Oct 2026', medium '11 Oct 2026', day '11 Oct', full."""
    if style == "medium":
        return f"{d.day} {MONTHS[d.month - 1]} {d.year}"
    if style == "day":
        return f"{d.day} {MONTHS[d.month - 1]}"
    if style == "full":
        return (
            f"{('Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday')[d.weekday()]} "
            f"{d.day} {MONTHS_LONG[d.month - 1]} {d.year}"
        )
    return f"{DAYS[d.weekday()]} {d.day} {MONTHS[d.month - 1]} {d.year}"


def relative_day(d: date, today: date) -> str:
    delta = (today - d).days
    if delta == 0:
        return "Today"
    if delta == 1:
        return "Yesterday"
    if 1 < delta < 7:
        return ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")[
            d.weekday()
        ]
    return fmt_date(d, "day" if delta < 300 else "medium")


def plural(n: int, word: str, words: str | None = None) -> str:
    return f"{n:,} {word if n == 1 else (words or word + 's')}"
