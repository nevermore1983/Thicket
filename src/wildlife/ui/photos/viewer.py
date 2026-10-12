"""Full-screen photo viewer: ← → to move, R rotate, I info, Z zoom to 100 %, Esc to close.

It is modal and owns the keyboard, so arrow keys never also move the page behind it.
Pictures load in the background: a 2048 px screen copy first (quick), the original
only when you zoom in.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

from PIL.ImageQt import ImageQt
from PySide6.QtCore import QPointF, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPixmap
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.domain import geo
from wildlife.domain.dates import fmt_date
from wildlife.domain.errors import PhotoError
from wildlife.domain.models import Photo
from wildlife.services.photos import open_image
from wildlife.ui.theme.icons import icon
from wildlife.ui.theme.manager import ThemeManager
from wildlife.ui.theme.tokens import DARK
from wildlife.ui.workers import run_in_background

T = DARK  # photos are viewed on dark, whatever the app's theme


def size_text(n: int) -> str:
    return f"{n / 1e6:.1f} MB" if n >= 1e6 else f"{max(1, round(n / 1e3))} KB"


def taken_text(photo: Photo) -> str:
    if not photo.taken_at:
        return "Unknown"
    moment = datetime.strptime(photo.taken_at, "%Y-%m-%d %H:%M:%S")
    text = f"{fmt_date(moment.date())} at {moment:%H:%M}"
    return text + (" (from the file name)" if photo.taken_source == "file_name" else "")


class Stage(QWidget):
    """Draws the picture: fitted to the window, or at 100 % and dragged to pan."""

    def __init__(self) -> None:
        super().__init__()
        self.picture: QPixmap | None = None
        self.message = ""
        self.actual = False  # 100 % instead of fit
        self.offset = QPointF(0, 0)
        self._drag: QPointF | None = None
        self.setMinimumSize(200, 200)

    def show_picture(self, picture: QPixmap | None, message: str = "") -> None:
        self.picture, self.message = picture, message
        self.offset = QPointF(0, 0)
        self.update()

    def paintEvent(self, _event) -> None:
        p = QPainter(self)
        p.fillRect(self.rect(), QColor(T.bg))
        if self.picture is None or self.picture.isNull():
            p.setPen(QColor(T.text_2))
            p.drawText(self.rect(), int(Qt.AlignmentFlag.AlignCenter), self.message)
            return
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        ratio = self.picture.devicePixelRatio()
        w, h = self.picture.width() / ratio, self.picture.height() / ratio
        if not self.actual:
            scale = min(self.width() / w, self.height() / h, 1.0 if max(w, h) < 600 else 99)
            w, h = w * scale, h * scale
        x = (self.width() - w) / 2 + self.offset.x()
        y = (self.height() - h) / 2 + self.offset.y()
        p.drawPixmap(QRectF(x, y, w, h), self.picture, QRectF(self.picture.rect()))

    def mousePressEvent(self, event) -> None:
        if self.actual:
            self._drag = event.position() - self.offset
            self.setCursor(Qt.CursorShape.ClosedHandCursor)

    def mouseMoveEvent(self, event) -> None:
        if self._drag is not None:
            self.offset = event.position() - self._drag
            self.update()

    def mouseReleaseEvent(self, _event) -> None:
        self._drag = None
        self.setCursor(Qt.CursorShape.OpenHandCursor if self.actual else Qt.CursorShape.ArrowCursor)


class PhotoViewer(QDialog):
    open_sighting = Signal(int)
    changed = Signal(int)  # photo id: rotated, captioned, made cover, located or removed

    def __init__(
        self,
        ctx: AppContext,
        theme: ThemeManager,
        photos: list[Photo],
        index: int = 0,
        sighting_id: int | None = None,
        titles: list[str] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.ctx, self.theme = ctx, theme
        self.photos, self.index = list(photos), max(0, min(index, len(photos) - 1))
        self.sighting_id = sighting_id  # set when viewing one sighting's photos
        self.titles = titles or [""] * len(photos)
        self._generation = 0
        self.setWindowTitle("Photo")
        self.setModal(True)
        self.setObjectName("Viewer")
        self.setStyleSheet(
            f"QDialog#Viewer {{ background: {T.bg}; }}"
            f"QDialog#Viewer QLabel {{ color: {T.text}; }}"
            f"QLabel#ViewerTitle {{ font-size: 15px; font-weight: 600; }}"
            f"QLabel#ViewerSub, QLabel[role='muted'] {{ color: {T.text_2}; }}"
            f"QFrame#ViewerInfo {{ background: {T.surface}; border-left: 1px solid {T.border}; }}"
            f"QDialog#Viewer QPushButton {{ background: transparent; color: {T.text}; border: 1px solid {T.border};"
            f" border-radius: 8px; padding: 6px 10px; }}"
            f"QDialog#Viewer QPushButton:hover {{ background: {T.surface_2}; }}"
            f"QDialog#Viewer QPushButton:checked {{ background: {T.surface_3}; }}"
            f"QDialog#Viewer QLineEdit {{ background: {T.surface_2}; color: {T.text}; border: 1px solid {T.border};"
            f" border-radius: 8px; padding: 6px 8px; }}"
        )
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)
        bar = QHBoxLayout()
        bar.setContentsMargins(16, 10, 12, 10)
        bar.setSpacing(8)
        names = QVBoxLayout()
        names.setSpacing(0)
        self.title = QLabel()
        self.title.setObjectName("ViewerTitle")
        self.subtitle = QLabel()
        self.subtitle.setObjectName("ViewerSub")
        names.addWidget(self.title)
        names.addWidget(self.subtitle)
        bar.addLayout(names, 1)
        self.rotate_btn = self._button(
            "Rotate", "rotate", "Rotate clockwise (R)", lambda: self.rotate()
        )
        self.zoom_btn = self._button(
            "100 %", "search", "Zoom to the original size (Z)", self.toggle_zoom, True
        )
        self.info_btn = self._button("Info", "info", "Show details (I)", self.toggle_info, True)
        self.cover_btn = self._button(
            "Make cover", "star", "Use as the sighting's main photo", self.make_cover
        )
        self.cover_btn.setVisible(sighting_id is not None)
        self.open_btn = self._button(
            "Open sighting", "list", "Open this photo's sighting", self._open_sighting
        )
        close = self._button("", "x", "Close (Esc)", self.close)
        for b in (
            self.rotate_btn,
            self.zoom_btn,
            self.info_btn,
            self.cover_btn,
            self.open_btn,
            close,
        ):
            bar.addWidget(b)
        outer.addLayout(bar)

        body = QHBoxLayout()
        body.setSpacing(0)
        self.stage = Stage()
        body.addWidget(self.stage, 1)
        self.info = self._build_info()
        self.info.hide()
        body.addWidget(self.info)
        outer.addLayout(body, 1)

        self.missing_bar = QWidget()
        mb = QHBoxLayout(self.missing_bar)
        mb.setContentsMargins(16, 10, 16, 14)
        mb.addStretch(1)
        mb.addWidget(
            self._button("Locate…", "folder", "Find the file and put it back", self.locate)
        )
        mb.addWidget(
            self._button("Remove photo", "trash", "Move this photo to the recycle bin", self.remove)
        )
        mb.addStretch(1)
        self.missing_bar.hide()
        outer.addWidget(self.missing_bar)
        self.show_current()

    def _button(self, text, icon_name, tip, slot, checkable=False) -> QPushButton:
        b = QPushButton(text)
        b.setIcon(icon(icon_name, T.text, 16))
        b.setToolTip(tip)
        b.setCheckable(checkable)
        b.setFocusPolicy(Qt.FocusPolicy.NoFocus)  # keys belong to the viewer
        b.clicked.connect(lambda _=False: slot())
        return b

    def _build_info(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("ViewerInfo")
        frame.setFixedWidth(320)
        v = QVBoxLayout(frame)
        v.setContentsMargins(18, 16, 18, 16)
        form = QFormLayout()
        form.setHorizontalSpacing(12)
        form.setVerticalSpacing(8)
        self.facts: dict[str, QLabel] = {}
        for key in ("File", "Taken", "Camera", "Size", "RAW original", "Position"):
            value = QLabel()
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            label = QLabel(key)
            label.setProperty("role", "muted")
            form.addRow(label, value)
            self.facts[key] = value
        v.addLayout(form)
        v.addSpacing(10)
        caption_label = QLabel("Caption")
        caption_label.setProperty("role", "muted")
        v.addWidget(caption_label)
        self.caption = QLineEdit()
        self.caption.setPlaceholderText("Add a caption…")
        self.caption.editingFinished.connect(self._save_caption)
        v.addWidget(self.caption)
        v.addStretch(1)
        return frame

    # ---- showing -------------------------------------------------------------------
    @property
    def photo(self) -> Photo:
        return self.photos[self.index]

    def show_current(self) -> None:
        photo = self.photo
        self._generation += 1
        generation = self._generation
        self.title.setText(self.titles[self.index] or photo.original_name)
        self.subtitle.setText(
            f"{taken_text(photo)}  ·  {self.index + 1} of {len(self.photos)}"
            + ("  ·  RAW" if photo.has_raw else "")
        )
        self.open_btn.setVisible(bool(photo.sighting_ids))
        self._fill_info(photo)
        missing = not self.ctx.photos.path_of(photo).exists()
        self.missing_bar.setVisible(missing)
        self.rotate_btn.setEnabled(not missing)
        self.zoom_btn.setEnabled(not missing)
        if missing:
            self.stage.show_picture(
                None,
                f"The file for this photo is missing:\n{photo.original_name}\n\n"
                "Locate it to put it back, or remove the photo.",
            )
            return
        self.stage.show_picture(None, "Loading…")
        if self.stage.actual:
            self._load_original(generation)
        else:
            run_in_background(
                lambda: self.ctx.photos.screen_image(photo),
                on_done=lambda path: self._loaded(generation, QPixmap(str(path)) if path else None),
            )

    def _load_original(self, generation: int) -> None:
        photo = self.photo
        path = self.ctx.photos.path_of(photo)
        run_in_background(
            lambda: ImageQt(open_image(path, photo.rotation)).copy(),
            on_done=lambda image: self._loaded(generation, QPixmap.fromImage(image)),
            on_error=lambda _exc: self._loaded(generation, None),
        )

    def _loaded(self, generation: int, picture: QPixmap | None) -> None:
        if generation != self._generation:
            return  # you've moved on to another photo
        self.stage.show_picture(picture, "" if picture else "This photo can't be displayed.")
        if self.index + 1 < len(self.photos):  # get the next one ready, so → is instant
            upcoming = self.photos[self.index + 1]
            run_in_background(lambda: self.ctx.photos.screen_image(upcoming))

    def _fill_info(self, photo: Photo) -> None:
        f = self.facts
        f["File"].setText(photo.original_name)
        f["Taken"].setText(taken_text(photo))
        f["Camera"].setText(photo.camera or "Not recorded")
        dims = f"{photo.width:,} × {photo.height:,}" if photo.width else "?"
        f["Size"].setText(f"{dims} · {size_text(photo.file_size)}")
        if photo.raw_rel_path:
            f["RAW original"].setText(f"{photo.raw_name} ({size_text(photo.raw_size or 0)})")
        else:
            f["RAW original"].setText("This is the RAW file" if photo.is_raw else "None")
        if photo.gps_latitude is not None:
            ref = geo.grid_ref_for(photo.gps_latitude, photo.gps_longitude, 10)
            f["Position"].setText(ref or f"{photo.gps_latitude:.5f}, {photo.gps_longitude:.5f}")
        else:
            f["Position"].setText("No GPS in this photo")
        self.caption.blockSignals(True)
        self.caption.setText(photo.caption or "")
        self.caption.blockSignals(False)

    # ---- actions -------------------------------------------------------------------
    def go(self, step: int) -> None:
        new = max(0, min(len(self.photos) - 1, self.index + step))
        if new != self.index:
            self._save_caption()
            self.index = new
            self.show_current()

    def rotate(self) -> None:
        updated = self.ctx.photos.rotate(self.photo.id)
        self.photos[self.index] = updated
        self.changed.emit(updated.id)
        self.show_current()

    def toggle_zoom(self) -> None:
        self.stage.actual = not self.stage.actual
        self.zoom_btn.setChecked(self.stage.actual)
        self.stage.setCursor(
            Qt.CursorShape.OpenHandCursor if self.stage.actual else Qt.CursorShape.ArrowCursor
        )
        self.show_current()

    def toggle_info(self) -> None:
        self.info.setVisible(not self.info.isVisible())
        self.info_btn.setChecked(self.info.isVisible())

    def make_cover(self) -> None:
        if self.sighting_id is not None:
            self.ctx.photos.make_cover(self.sighting_id, self.photo.id)
            self.changed.emit(self.photo.id)
            self.subtitle.setText(self.subtitle.text() + "  ·  now the cover photo")

    def _save_caption(self) -> None:
        text = self.caption.text().strip() or None
        if text != self.photo.caption:
            self.ctx.photos.set_caption(self.photo.id, text)
            self.photos[self.index] = self.ctx.photos.get(self.photo.id)
            self.changed.emit(self.photo.id)

    def _open_sighting(self) -> None:
        if self.photo.sighting_ids:
            self.open_sighting.emit(self.sighting_id or self.photo.sighting_ids[0])
            self.close()

    def locate(self) -> None:
        name, _ = QFileDialog.getOpenFileName(self, f"Find {self.photo.original_name}")
        if not name:
            return
        try:
            self.ctx.photos.locate(self.photo.id, Path(name))
        except PhotoError as exc:
            QMessageBox.information(self, "Not the same photo", exc.user_message)
            return
        self.changed.emit(self.photo.id)
        self.show_current()

    def remove(self) -> None:
        photo = self.photo
        self.ctx.photos.delete([photo.id])
        self.changed.emit(photo.id)
        del self.photos[self.index]
        del self.titles[self.index]
        if not self.photos:
            self.close()
            return
        self.index = min(self.index, len(self.photos) - 1)
        self.show_current()

    # ---- keyboard ------------------------------------------------------------------
    def keyPressEvent(self, event) -> None:
        if self.caption.hasFocus() and event.key() != Qt.Key.Key_Escape:
            return super().keyPressEvent(event)  # typing a caption
        key = event.key()
        actions = {
            Qt.Key.Key_Left: lambda: self.go(-1),
            Qt.Key.Key_Right: lambda: self.go(1),
            Qt.Key.Key_Home: lambda: self.go(-len(self.photos)),
            Qt.Key.Key_End: lambda: self.go(len(self.photos)),
            Qt.Key.Key_R: self.rotate,
            Qt.Key.Key_I: self.toggle_info,
            Qt.Key.Key_Z: self.toggle_zoom,
            Qt.Key.Key_Escape: self.close,
        }
        if key in actions:
            if key == Qt.Key.Key_R and not self.rotate_btn.isEnabled():
                return
            actions[key]()
            return
        super().keyPressEvent(event)

    def closeEvent(self, event) -> None:
        self._save_caption()
        super().closeEvent(event)

    def open_full(self) -> None:
        """Show covering the main window (like full screen, without hiding the taskbar)."""
        window = self.parentWidget().window() if self.parentWidget() else None
        if window is not None:
            self.setGeometry(window.geometry())
        self.showMaximized() if window is None else self.show()
        self.setFocus()
