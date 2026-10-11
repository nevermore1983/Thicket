"""Line icons (24 px grid, stroke-based) drawn from SVG in any theme colour.

Most come from Lucide (ISC licence, https://lucide.dev); the butterfly,
dragonfly, frog and snail are WildLife's own and still need a designer's polish.
"""

from __future__ import annotations

from functools import lru_cache

from PySide6.QtCore import QByteArray, QRectF, QSize, Qt
from PySide6.QtGui import QGuiApplication, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

PATHS: dict[str, str] = {
    "home": '<path d="M3 10.5 12 3l9 7.5"/><path d="M5 9.5V20a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1V9.5"/>',
    "list": '<path d="M8 6h13M8 12h13M8 18h13"/><circle cx="3.5" cy="6" r="1"/><circle cx="3.5" cy="12" r="1"/><circle cx="3.5" cy="18" r="1"/>',
    "calendar": '<rect x="3" y="4.5" width="18" height="17" rx="2"/><path d="M3 9.5h18M8 2.5v4M16 2.5v4"/>',
    "map": '<path d="M9 4 3 6.5v14L9 18l6 2.5 6-2.5V4l-6 2.5L9 4z"/><path d="M9 4v14M15 6.5v14"/>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"/><circle cx="9" cy="9" r="2"/><path d="m21 15-4.5-4.5L6 21"/>',
    "chart": '<path d="M5 20V11M11 20V5M17 20v-7M3 20h18"/>',
    "leaf": '<path d="M11 20A7 7 0 0 1 4 13c0-6 6-9 16-10-1 10-4 16-9 17z"/><path d="M4 21c3-5 6-8 11-11"/>',
    "pin": '<path d="M12 21s-7-6.1-7-11.5a7 7 0 0 1 14 0C19 14.9 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    "settings": '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
    "search": '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5"/>',
    "plus": '<path d="M12 5v14M5 12h14"/>',
    "x": '<path d="M6 6l12 12M18 6 6 18"/>',
    "check": '<path d="m5 12.5 4.5 4.5L19 7"/>',
    "camera": '<path d="M4 8h3l2-3h6l2 3h3a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V9a1 1 0 0 1 1-1z"/><circle cx="12" cy="13.5" r="3.5"/>',
    "upload": '<path d="M12 15V4M7 9l5-5 5 5"/><path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
    "sun": '<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/>',
    "moon": '<path d="M20 14.5A8 8 0 1 1 9.5 4 6.5 6.5 0 0 0 20 14.5z"/>',
    "monitor": '<rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/>',
    "folder": '<path d="M3 6a1 1 0 0 1 1-1h5l2 2h9a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V6z"/>',
    "shield": '<path d="M12 3 4 6v6c0 5 3.5 8 8 9 4.5-1 8-4 8-9V6l-8-3z"/><path d="m9 12 2 2 4-4"/>',
    "alert": '<path d="M12 3.5 2.5 20h19L12 3.5z"/><path d="M12 10v4M12 17v.5"/>',
    "info": '<circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8v.5"/>',
    "chevron-left": '<path d="m15 6-6 6 6 6"/>',
    "chevron-right": '<path d="m9 6 6 6-6 6"/>',
    "chevron-down": '<path d="m6 9 6 6 6-6"/>',
    "trash": '<path d="M4 7h16M10 11v6M14 11v6M6 7l1 13a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1l1-13M9 7V4h6v3"/>',
    "edit": '<path d="M4 20h4L19 9l-4-4L4 16v4z"/><path d="m13.5 6.5 4 4"/>',
    "star": '<path d="m12 3 2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1-4.4-4.3 6.1-.9z"/>',
    "download": '<path d="M12 4v11M7 10l5 5 5-5"/><path d="M4 15v4a1 1 0 0 0 1 1h14a1 1 0 0 0 1-1v-4"/>',
    "clock": '<circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/>',
    "dots": '<circle cx="7" cy="8" r="2.2"/><circle cx="15.5" cy="6.5" r="2.2"/><circle cx="12" cy="15" r="2.2"/><circle cx="18" cy="16.5" r="2.2"/><circle cx="6" cy="17" r="2.2"/>',
    "bird": '<path d="M16 7h.01"/><path d="M3.4 18H12a8 8 0 0 0 8-8V7a4 4 0 0 0-7.28-2.3L2 20"/><path d="m20 7 2 .5-2 .5"/><path d="M10 18v3"/><path d="M14 17.75V21"/><path d="M7 18a6 6 0 0 0 3.84-10.61"/>',
    "rabbit": '<path d="M13 16a3 3 0 0 1 2.24 5"/><path d="M18 12h.01"/><path d="M18 21h-8a4 4 0 0 1-4-4 7 7 0 0 1 7-7h.2L9.6 6.4a1 1 0 1 1 2.8-2.8L15.8 7h.2c3.3 0 6 2.7 6 6v1a2 2 0 0 1-2 2h-1a3 3 0 0 0-3 3"/><path d="M20 8.54V4a2 2 0 1 0-4 0v3"/><path d="M7.61 12.53a3 3 0 1 0-1.6 4.3"/>',
    "fish": '<path d="M6.5 12c.94-3.46 4.94-6 8.5-6 3.56 0 6.06 2.54 7 6-.94 3.47-3.44 6-7 6s-7.56-2.53-8.5-6Z"/><path d="M18 12v.5"/><path d="M16 17.93a9.77 9.77 0 0 1 0-11.86"/><path d="M7 10.67C7 8 5.58 5.97 2.73 5.5c-1 1.5-1 5 .23 6.5-1.24 1.5-1.24 5-.23 6.5C5.58 18.03 7 16 7 13.33"/>',
    "butterfly": '<path d="M12 8v11"/><path d="M12 9C10 5 4.5 3.5 3.5 6.5S6 12 12 11.5"/><path d="M12 9c2-4 7.5-5.5 8.5-2.5S18 12 12 11.5"/><path d="M12 12.5c-3.5 0-6.5 1.5-5.5 4.5s4.5 2 5.5-1"/><path d="M12 12.5c3.5 0 6.5 1.5 5.5 4.5s-4.5 2-5.5-1"/><path d="M10.5 5 12 7.5 13.5 5"/>',
    "dragonfly": '<path d="M12 6v15"/><circle cx="12" cy="4.5" r="1.5"/><path d="M12 8.5C8 6.5 3 6.5 2.5 8.5S7 10.5 12 9.5"/><path d="M12 8.5c4-2 9-2 9.5 0S17 10.5 12 9.5"/><path d="M12 11.5c-3.5-.5-7 .5-7 2.2s3.5 1 7-1.2"/><path d="M12 11.5c3.5-.5 7 .5 7 2.2s-3.5 1-7-1.2"/>',
    "frog": '<path d="M4.5 15c0-4 3.4-6.5 7.5-6.5s7.5 2.5 7.5 6.5c0 2.6-3.4 4-7.5 4s-7.5-1.4-7.5-4z"/><circle cx="8.5" cy="7.5" r="2"/><circle cx="15.5" cy="7.5" r="2"/><path d="M9.5 14.5c1.5 1 3.5 1 5 0"/><path d="M5 17.5 3 20h3M19 17.5l2 2.5h-3"/>',
    "bug": '<path d="m8 2 1.88 1.88"/><path d="M14.12 3.88 16 2"/><path d="M9 7.13v-1a3 3 0 1 1 6 0v1"/><path d="M12 20c-3.3 0-6-2.7-6-6v-3a4 4 0 0 1 4-4h4a4 4 0 0 1 4 4v3c0 3.3-2.7 6-6 6"/><path d="M12 20v-9"/><path d="M6.53 9C4.6 8.8 3 7.1 3 5"/><path d="M6 13H2"/><path d="M3 21c0-2.1 1.7-3.9 3.8-4"/><path d="M20.97 5c0 2.1-1.6 3.8-3.5 4"/><path d="M22 13h-4"/><path d="M17.2 17c2.1.1 3.8 1.9 3.8 4"/>',
    "snail": '<circle cx="10.5" cy="11.5" r="5.5"/><path d="M10.5 11.5a2.2 2.2 0 1 1 2.2 2.2"/><path d="M3 19h13.5a4.5 4.5 0 0 0 4.5-4.5V8"/><path d="m21 8 1-3M19 9l-1.5-3"/>',
    "paw-print": '<circle cx="7" cy="9" r="1.8"/><circle cx="11" cy="5.8" r="1.8"/><circle cx="15.5" cy="6.5" r="1.8"/><circle cx="18.5" cy="10.5" r="1.8"/><path d="M8 17.5c0-3 2-5.5 4.5-5.5s4.5 2.5 4.5 5c0 2-1.5 3-3 3-1 0-1.5-.5-2-.5s-1.2.5-2.2.5C8.7 20 8 19 8 17.5z"/>',
    "route": '<circle cx="6" cy="19" r="3"/><path d="M9 19h8.5a3.5 3.5 0 0 0 0-7h-11a3.5 3.5 0 0 1 0-7H15"/><circle cx="18" cy="5" r="3"/>',
}


def render(painter: QPainter, name: str, colour: str, rect: QRectF, stroke: float = 1.8) -> None:
    """Draw icon `name` into `rect` with an existing painter (any size, any device)."""
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{colour}" '
        f'stroke-width="{stroke}" stroke-linecap="round" stroke-linejoin="round">{PATHS[name]}</svg>'
    )
    QSvgRenderer(QByteArray(svg.encode())).render(painter, rect)


@lru_cache(maxsize=512)
def pixmap(name: str, colour: str, size: int = 18, stroke: float = 1.8) -> QPixmap:
    """Render icon `name` in `colour` at `size` logical pixels (sharp on high-DPI screens)."""
    app = QGuiApplication.instance()
    ratio = app.devicePixelRatio() if app else 1.0
    pm = QPixmap(QSize(round(size * ratio), round(size * ratio)))
    pm.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pm)
    render(painter, name, colour, QRectF(0, 0, pm.width(), pm.height()), stroke)
    painter.end()
    pm.setDevicePixelRatio(ratio)
    return pm


def icon(name: str, colour: str, size: int = 18, checked_colour: str | None = None) -> QIcon:
    """A QIcon; if `checked_colour` is given, checkable buttons switch colour when checked."""
    result = QIcon(pixmap(name, colour, size))
    if checked_colour:
        result.addPixmap(pixmap(name, checked_colour, size), QIcon.Mode.Normal, QIcon.State.On)
    return result
