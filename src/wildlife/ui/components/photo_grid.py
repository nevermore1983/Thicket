"""A painted grid of photo tiles: fast with thousands of photos, selectable, keyboard-friendly.

Only the tiles on screen are drawn, and their thumbnails load in the background
(ThumbnailLoader), so opening a library of 5,000 photos doesn't wait for 5,000 files.
"""

from __future__ import annotations

import math
import time
from dataclasses import dataclass

from PySide6.QtCore import QEvent, QPoint, QRect, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QSizePolicy, QToolTip, QWidget

from wildlife.domain.models import Photo
from wildlife.ui.components.thumbnails import ThumbnailLoader
from wildlife.ui.theme.icons import pixmap as icon_pixmap
from wildlife.ui.theme.manager import ThemeManager

GAP = 10
CAPTION_H = 38  # room under a tile for two lines of text


@dataclass(frozen=True, slots=True)
class GridItem:
    photo: Photo
    title: str = ""  # under the tile, e.g. the species
    subtitle: str = ""  # under the title, e.g. the date
    overlay: str = ""  # on the picture's bottom edge, e.g. '08:04 · GPS'
    tooltip: str = ""


class PhotoGrid(QWidget):
    activated = Signal(int)  # index: double-click or Enter (single click when not selectable)
    selection_changed = Signal()

    def __init__(
        self,
        loader: ThumbnailLoader,
        theme: ThemeManager,
        selectable: bool = False,
        tile: int = 168,
        captions: bool = True,
    ) -> None:
        super().__init__()
        self.loader, self.theme = loader, theme
        self.selectable, self.tile, self.captions = selectable, tile, captions
        self.items: list[GridItem] = []
        self.selected: set[int] = set()
        self.current = 0
        self._anchor = 0
        self._hover: int | None = None
        self._after_double_click = False
        self._press_snapshot: set[int] | None = None
        self._last_press: float | None = None
        self._index_of: dict[int, list[int]] = {}
        self._scaled: dict[tuple[int, int, int], QPixmap] = {}
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.setAccessibleName("Photos")
        loader.ready.connect(self._thumbnail_ready)
        theme.changed.connect(self.update)

    # ---- content -------------------------------------------------------------------
    def set_items(self, items: list[GridItem]) -> None:
        self.items = items
        self.selected = {i for i in self.selected if i < len(items)}
        self.current = min(self.current, max(0, len(items) - 1))
        self._index_of = {}
        for i, item in enumerate(items):
            self._index_of.setdefault(item.photo.id, []).append(i)
        self._scaled.clear()
        self.setAccessibleDescription(f"{len(items)} photos")
        self._resize_to_content()
        self.update()

    def set_tile_size(self, size: int) -> None:
        self.tile = size
        self._scaled.clear()
        self._resize_to_content()
        self.update()

    def selected_photos(self) -> list[Photo]:
        return [self.items[i].photo for i in sorted(self.selected)]

    def set_selected(self, indices) -> None:
        self.selected = {i for i in indices if 0 <= i < len(self.items)}
        self.update()
        self.selection_changed.emit()

    def select_all(self) -> None:
        self.set_selected(range(len(self.items)))

    def clear_selection(self) -> None:
        self.set_selected(())

    # ---- geometry ------------------------------------------------------------------
    def _columns(self, width: int | None = None) -> int:
        width = self.width() if width is None else width
        return max(1, (width + GAP) // (self.tile + GAP))

    def _cell(self, width: int | None = None) -> tuple[float, float]:
        """(tile width, row height) so the tiles exactly fill the width."""
        width = self.width() if width is None else width
        cols = self._columns(width)
        tile = (width - GAP * (cols - 1)) / cols
        return tile, tile + (CAPTION_H if self.captions else 0) + GAP

    def hasHeightForWidth(self) -> bool:
        return True

    def heightForWidth(self, width: int) -> int:
        if not self.items:
            return 0
        rows = math.ceil(len(self.items) / self._columns(width))
        return math.ceil(rows * self._cell(width)[1] - GAP)

    def sizeHint(self) -> QSize:
        return QSize(800, self.heightForWidth(800))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._resize_to_content()

    def _resize_to_content(self) -> None:
        self.setFixedHeight(max(0, self.heightForWidth(max(self.width(), self.tile))))

    def tile_rect(self, index: int) -> QRectF:
        tile, row_h = self._cell()
        cols = self._columns()
        row, col = divmod(index, cols)
        return QRectF(col * (tile + GAP), row * row_h, tile, tile)

    def index_at(self, pos: QPoint) -> int | None:
        tile, row_h = self._cell()
        col = int(pos.x() // (tile + GAP))
        row = int(pos.y() // row_h)
        index = row * self._columns() + col
        if not (0 <= col < self._columns() and 0 <= index < len(self.items)):
            return None
        hit = self.tile_rect(index).adjusted(0, 0, 0, CAPTION_H if self.captions else 0)
        return index if hit.contains(pos) else None

    # ---- painting ------------------------------------------------------------------
    def paintEvent(self, event) -> None:
        if not self.items:
            return
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        _, row_h = self._cell()
        cols = self._columns()
        area = event.rect()
        first = max(0, int(area.top() // row_h) * cols)
        last = min(len(self.items), (int(area.bottom() // row_h) + 1) * cols)
        for i in range(first, last):
            self._paint_tile(p, i)
        p.end()
        self._cancel_offscreen()

    def _cancel_offscreen(self) -> None:
        """Stop making thumbnails for tiles scrolled out of view (one row either side kept)."""
        seen = self.visibleRegion().boundingRect()
        if seen.isEmpty():
            return
        _, row_h = self._cell()
        cols = self._columns()
        first = max(0, (int(seen.top() // row_h) - 1) * cols)
        last = min(len(self.items), (int(seen.bottom() // row_h) + 2) * cols)
        size = 256 if self.tile <= 220 else 1024
        keep = {self.loader.key(self.items[i].photo, size) for i in range(first, last)}
        self.loader.cancel_except(self, keep)

    def _paint_tile(self, p: QPainter, index: int) -> None:
        t = self.theme.tokens
        item = self.items[index]
        r = self.tile_rect(index)
        clip = QPainterPath()
        clip.addRoundedRect(r, 10, 10)
        p.save()
        p.setClipPath(clip)
        thumb = self.loader.get(item.photo, 256 if self.tile <= 220 else 1024, owner=self)
        if isinstance(thumb, QPixmap):
            p.drawPixmap(r.toRect(), self._fill(item.photo, thumb, int(r.width())))
        else:
            p.fillRect(r, QColor(t.surface_3))
            if isinstance(thumb, str):  # "File missing" or "Can't display"
                icon = icon_pixmap("alert", t.warning, 22)
                p.drawPixmap(int(r.center().x() - 11), int(r.center().y() - 22), icon)
                p.setPen(QColor(t.warning))
                p.drawText(
                    QRectF(r.left(), r.center().y() + 4, r.width(), 20),
                    int(Qt.AlignmentFlag.AlignCenter),
                    thumb,
                )
        if item.overlay:
            band = QRectF(r.left(), r.bottom() - 24, r.width(), 24)
            p.fillRect(band, QColor(0, 0, 0, 120))
            small = QFont(self.font())
            small.setPixelSize(11)
            p.setFont(small)
            p.setPen(QColor("#ffffff"))
            p.drawText(band.adjusted(8, 0, -8, 0), int(Qt.AlignmentFlag.AlignVCenter), item.overlay)
        p.restore()

        if item.photo.has_raw:
            self._pill(p, QRectF(r.left() + 6, r.top() + 6, 34, 18), "RAW")
        if index in self.selected:
            p.setPen(QPen(QColor(t.accent), 3))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(1.5, 1.5, -1.5, -1.5), 9, 9)
        if self.selectable:
            box = QRectF(r.right() - 28, r.top() + 6, 22, 22)
            p.setPen(QPen(QColor("#ffffff"), 2))
            p.setBrush(QColor(t.accent) if index in self.selected else QColor(0, 0, 0, 70))
            p.drawEllipse(box)
            if index in self.selected:
                p.drawPixmap(
                    int(box.left() + 3),
                    int(box.top() + 3),
                    icon_pixmap("check", t.accent_fg, 16, 3),
                )
        if index == self._hover and index not in self.selected:
            p.setPen(QPen(QColor(t.border_strong), 2))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(1, 1, -1, -1), 10, 10)
        if index == self.current and self.hasFocus():
            p.setPen(QPen(QColor(t.text), 2, Qt.PenStyle.DashLine))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRoundedRect(r.adjusted(-3, -3, 3, 3), 12, 12)
        if self.captions:
            self._paint_caption(p, item, r)

    def _paint_caption(self, p: QPainter, item: GridItem, r: QRectF) -> None:
        t = self.theme.tokens
        bold = QFont(self.font())
        bold.setPixelSize(13)
        bold.setWeight(QFont.Weight.DemiBold)
        p.setFont(bold)
        p.setPen(QColor(t.text))
        width = int(r.width())
        p.drawText(
            QRectF(r.left(), r.bottom() + 4, width, 17),
            int(Qt.AlignmentFlag.AlignVCenter),
            QFontMetrics(bold).elidedText(item.title, Qt.TextElideMode.ElideRight, width),
        )
        small = QFont(self.font())
        small.setPixelSize(12)
        p.setFont(small)
        p.setPen(QColor(t.text_2))
        p.drawText(
            QRectF(r.left(), r.bottom() + 21, width, 16),
            int(Qt.AlignmentFlag.AlignVCenter),
            QFontMetrics(small).elidedText(item.subtitle, Qt.TextElideMode.ElideRight, width),
        )

    def _pill(self, p: QPainter, r: QRectF, text: str) -> None:
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QColor(0, 0, 0, 150))
        p.drawRoundedRect(r, 9, 9)
        font = QFont(self.font())
        font.setPixelSize(10)
        font.setWeight(QFont.Weight.Bold)
        p.setFont(font)
        p.setPen(QColor("#ffffff"))
        p.drawText(r, int(Qt.AlignmentFlag.AlignCenter), text)

    def _fill(self, photo: Photo, thumb: QPixmap, size: int) -> QPixmap:
        """The thumbnail cropped to fill a square tile (cached per size)."""
        key = (photo.id, photo.rotation, size)
        if key not in self._scaled:
            ratio = self.devicePixelRatioF()
            px = round(size * ratio)
            scaled = thumb.scaled(
                px,
                px,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )
            x, y = (scaled.width() - px) // 2, (scaled.height() - px) // 2
            cropped = scaled.copy(QRect(x, y, px, px))
            cropped.setDevicePixelRatio(ratio)
            self._scaled[key] = cropped
        return self._scaled[key]

    def _thumbnail_ready(self, key) -> None:
        for index in self._index_of.get(key[0], []):
            self.update(self.tile_rect(index).toRect().adjusted(-4, -4, 4, 4))

    def refresh_photo(self, photo_id: int) -> None:
        """Repaint one photo (after it was rotated or its file was found)."""
        self._scaled = {k: v for k, v in self._scaled.items() if k[0] != photo_id}
        self.loader.forget(photo_id)
        self._thumbnail_ready((photo_id,))

    # ---- interaction ---------------------------------------------------------------
    def mouseMoveEvent(self, event) -> None:
        index = self.index_at(event.position().toPoint())
        if index != self._hover:
            old, self._hover = self._hover, index
            for i in (old, index):
                if i is not None:
                    self.update(self.tile_rect(i).toRect().adjusted(-4, -4, 4, 4))
            self.setCursor(
                Qt.CursorShape.PointingHandCursor
                if index is not None
                else Qt.CursorShape.ArrowCursor
            )

    def leaveEvent(self, _event) -> None:
        self._hover = None
        self.update()

    def mousePressEvent(self, event) -> None:
        """Remember the selection at the first press of a click pair (see the double-click)."""
        now = time.monotonic()
        interval = QApplication.doubleClickInterval() / 1000
        if self._last_press is None or now - self._last_press > interval:
            self._press_snapshot = set(self.selected)
        self._last_press = now
        self._after_double_click = False
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:
        if event.button() != Qt.MouseButton.LeftButton:
            return
        if self._after_double_click:  # the release that ends a double-click: already handled
            self._after_double_click = False
            return
        index = self.index_at(event.position().toPoint())
        if index is None:
            return
        self.current = index
        if not self.selectable:
            self.activated.emit(index)
            return
        mods = event.modifiers()
        if mods & Qt.KeyboardModifier.ShiftModifier:
            low, high = sorted((self._anchor, index))
            self.set_selected(self.selected | set(range(low, high + 1)))
        else:
            self._toggle(index)
            self._anchor = index

    def mouseDoubleClickEvent(self, event) -> None:
        index = self.index_at(event.position().toPoint())
        if index is not None and self.selectable:
            # Opening with a double-click mustn't change the selection: put back what it was
            # before the pair of clicks, and ignore the release that may follow
            if self._press_snapshot is not None:
                self.set_selected(self._press_snapshot)
            self._after_double_click = True
            self.activated.emit(index)

    def _toggle(self, index: int) -> None:
        self.set_selected(self.selected ^ {index})

    def keyPressEvent(self, event) -> None:
        if not self.items:
            return super().keyPressEvent(event)
        cols = self._columns()
        key = event.key()
        moves = {
            Qt.Key.Key_Left: -1,
            Qt.Key.Key_Right: 1,
            Qt.Key.Key_Up: -cols,
            Qt.Key.Key_Down: cols,
            Qt.Key.Key_Home: -len(self.items),
            Qt.Key.Key_End: len(self.items),
        }
        if key in moves:
            self.current = max(0, min(len(self.items) - 1, self.current + moves[key]))
            if self.selectable and event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self.set_selected(self.selected | {self.current})
            self._scroll_to(self.current)
            self.update()
        elif key == Qt.Key.Key_Space and self.selectable:
            self._toggle(self.current)
        elif key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self.activated.emit(self.current)
        elif (
            key == Qt.Key.Key_A
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
            and self.selectable
        ):
            self.select_all()
        else:
            super().keyPressEvent(event)

    def _scroll_to(self, index: int) -> None:
        """Ask a surrounding scroll area to show this tile."""
        area = self.parentWidget()
        while area is not None and not hasattr(area, "ensureVisible"):
            area = area.parentWidget()
        if area is not None:
            r = self.tile_rect(index).toRect()
            centre = self.mapTo(area.widget(), r.center())
            area.ensureVisible(centre.x(), centre.y(), r.width() // 2 + 20, r.height() // 2 + 40)

    def focusInEvent(self, event) -> None:
        super().focusInEvent(event)
        self.update()

    def focusOutEvent(self, event) -> None:
        super().focusOutEvent(event)
        self.update()

    def event(self, e) -> bool:
        if e.type() == QEvent.Type.ToolTip:
            index = self.index_at(e.pos())
            if index is not None and self.items[index].tooltip:
                QToolTip.showText(e.globalPos(), self.items[index].tooltip, self)
            else:
                QToolTip.hideText()
            return True
        return super().event(e)
