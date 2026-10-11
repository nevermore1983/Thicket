"""The right-hand side panel: view or edit something without leaving the page.

Views stack (Sighting > Species > back). The panel pushes the page aside rather
than covering it, so the list or calendar behind stays visible.
"""

from __future__ import annotations

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from wildlife.ui.theme.icons import icon
from wildlife.ui.theme.manager import ThemeManager

PANEL_WIDTH = 440


class PanelView(QWidget):
    """Base class for anything shown in the side panel."""

    title = ""

    def can_close(self) -> bool:
        """Return False to stop the panel closing (e.g. after asking about unsaved changes)."""
        return True

    def on_shown(self) -> None:
        """Called each time the view becomes visible (focus a field, refresh...)."""


class SidePanel(QFrame):
    closed = Signal()

    def __init__(self, theme: ThemeManager) -> None:
        super().__init__()
        self.setObjectName("SidePanel")
        self.setFixedWidth(PANEL_WIDTH)
        self.hide()
        self._theme = theme
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        head = QFrame()
        head.setObjectName("PanelHead")
        h = QHBoxLayout(head)
        h.setContentsMargins(10, 10, 10, 10)
        self._back = QPushButton()
        self._back.setProperty("variant", "ghost")
        self._back.setToolTip("Back")
        self._back.setAccessibleName("Back")
        self._back.setFixedWidth(36)
        self._back.clicked.connect(self.back)
        self._title = QLabel()
        self._title.setProperty("role", "rowTitle")
        self._close = QPushButton()
        self._close.setProperty("variant", "ghost")
        self._close.setToolTip("Close (Esc)")
        self._close.setAccessibleName("Close")
        self._close.setFixedWidth(36)
        self._close.clicked.connect(self.close_panel)
        h.addWidget(self._back)
        h.addWidget(self._title, 1)
        h.addWidget(self._close)
        layout.addWidget(head)
        self._stack = QStackedWidget()
        layout.addWidget(self._stack, 1)
        self._paint()
        theme.changed.connect(self._paint)

    def _paint(self) -> None:
        t = self._theme.tokens
        self._back.setIcon(icon("chevron-left", t.text_2, 18))
        self._close.setIcon(icon("x", t.text_2, 18))

    # ---- stack management ---------------------------------------------------
    def current(self) -> PanelView | None:
        return self._stack.currentWidget()

    def show_view(self, view: PanelView, push: bool = False) -> None:
        """Show `view`. push=True keeps the current view underneath (Back returns to it)."""
        if not push and not self._clear():
            return
        self._stack.addWidget(view)
        self._stack.setCurrentWidget(view)
        self._update_head()
        self.show()
        view.on_shown()

    def replace_top(self, view: PanelView) -> None:
        top = self.current()
        self._stack.addWidget(view)
        self._stack.setCurrentWidget(view)
        if top is not None:
            self._stack.removeWidget(top)
            top.deleteLater()
        self._update_head()
        view.on_shown()

    def back(self) -> None:
        top = self.current()
        if top is None or not top.can_close():
            return
        self._stack.removeWidget(top)
        top.deleteLater()
        if self._stack.count() == 0:
            self.hide()
            self.closed.emit()
        else:
            self._update_head()
            self.current().on_shown()

    def close_panel(self) -> bool:
        if not self._clear():
            return False
        self.hide()
        self.closed.emit()
        return True

    def _clear(self) -> bool:
        while self._stack.count():
            top = self._stack.widget(self._stack.count() - 1)
            if not top.can_close():
                return False
            self._stack.removeWidget(top)
            top.deleteLater()
        return True

    def _update_head(self) -> None:
        self._back.setVisible(self._stack.count() > 1)
        view = self.current()
        self._title.setText(view.title if view else "")

    def keyPressEvent(self, event) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.back() if self._stack.count() > 1 else self.close_panel()
            return
        super().keyPressEvent(event)
