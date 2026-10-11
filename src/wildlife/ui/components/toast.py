"""Toasts: short, non-blocking messages at the bottom of the window, with optional Undo."""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QEvent, QObject, Qt, QTimer
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QWidget

from wildlife.ui.theme.icons import pixmap
from wildlife.ui.theme.manager import ThemeManager


class Toast(QFrame):
    def __init__(
        self,
        host: ToastHost,
        message: str,
        undo: Callable[[], None] | None,
        open_: Callable[[], None] | None,
    ) -> None:
        super().__init__(host.parent_widget)
        self.setObjectName("Toast")
        self._host = host
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 8, 8)
        layout.setSpacing(10)
        tick = QLabel()
        tick.setPixmap(pixmap("check", host.theme.tokens.accent, 17, 2.4))
        layout.addWidget(tick)
        text = QLabel(message)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.NoTextInteraction)
        layout.addWidget(text)
        if undo:
            layout.addWidget(self._action("Undo", lambda: (undo(), host.show("Undone"))))
        if open_:
            layout.addWidget(self._action("Open", open_))
        close = self._action("✕", lambda: None)
        close.setAccessibleName("Dismiss")
        layout.addWidget(close)
        self.adjustSize()
        QTimer.singleShot(10_000 if undo else 4_000, self.dismiss)

    def _action(self, label: str, fn: Callable[[], object]) -> QPushButton:
        btn = QPushButton(label)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(lambda: (self.dismiss(), fn()))
        return btn

    def dismiss(self) -> None:
        if self.isVisible():
            self.hide()
            self._host.remove(self)


class ToastHost(QObject):
    """Owns the toasts shown over `parent_widget` and keeps them placed bottom-centre."""

    def __init__(self, parent_widget: QWidget, theme: ThemeManager) -> None:
        super().__init__(parent_widget)
        self.parent_widget, self.theme = parent_widget, theme
        self._toasts: list[Toast] = []
        self.last_undo: Callable[[], None] | None = None
        parent_widget.installEventFilter(self)

    def show(
        self,
        message: str,
        undo: Callable[[], None] | None = None,
        open_: Callable[[], None] | None = None,
    ) -> Toast:
        toast = Toast(self, message, undo, open_)
        self.last_undo = undo
        self._toasts.append(toast)
        toast.show()
        toast.raise_()
        self._layout()
        return toast

    def remove(self, toast: Toast) -> None:
        if toast in self._toasts:
            self._toasts.remove(toast)
            toast.deleteLater()
        self._layout()

    def messages(self) -> list[str]:
        """Visible messages (used by tests)."""
        return [t.findChildren(QLabel)[1].text() for t in self._toasts]

    def _layout(self) -> None:
        y = self.parent_widget.height() - 20
        for toast in reversed(self._toasts):
            toast.adjustSize()
            y -= toast.height()
            toast.move((self.parent_widget.width() - toast.width()) // 2, y)
            y -= 8

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Resize:
            self._layout()
        return False
