"""'Drop photos here or click to choose': the box the sighting editor adds photos with."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QDragEnterEvent, QDropEvent
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
)

from wildlife.ui.components.visuals import plural
from wildlife.ui.theme.icons import pixmap
from wildlife.ui.theme.manager import ThemeManager


class PhotoDropZone(QFrame):
    """'Drop photos here or click to choose' box."""

    def __init__(self, theme: ThemeManager, on_files, on_click) -> None:
        super().__init__()
        self.setObjectName("DropZone")
        self.setAcceptDrops(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self._theme, self._on_files, self._on_click = theme, on_files, on_click
        h = QHBoxLayout(self)
        h.setContentsMargins(14, 12, 14, 12)
        h.setSpacing(10)
        self._icon = QLabel()
        self._text = QLabel("Drop photos here or click to choose")
        self._text.setProperty("role", "muted")
        h.addWidget(self._icon)
        h.addWidget(self._text, 1)
        self._count = 0
        theme.changed.connect(self._paint)
        self._paint()

    def _paint(self) -> None:
        self._icon.setPixmap(pixmap("camera", self._theme.tokens.text_2, 20))

    def set_count(self, n: int) -> None:
        self._count = n
        self._text.setText(
            f"{plural(n, 'photo')} attached. Drop or click to add more."
            if n
            else "Drop photos here or click to choose"
        )

    def set_busy(self, busy: bool) -> None:
        self._text.setText("Adding photos…" if busy else self._text.text())
        if not busy:
            self.set_count(self._count)

    def mousePressEvent(self, event) -> None:
        self._on_click()

    def dragEnterEvent(self, event: QDragEnterEvent) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self.setProperty("over", True)
            self.style().polish(self)

    def dragLeaveEvent(self, event) -> None:
        self.setProperty("over", False)
        self.style().polish(self)

    def dropEvent(self, event: QDropEvent) -> None:
        self.setProperty("over", False)
        self.style().polish(self)
        files = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if files:
            self._on_files(files)
