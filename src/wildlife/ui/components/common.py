"""Small reusable building blocks: buttons, segmented control, empty state, callout, page."""

from __future__ import annotations

from collections.abc import Callable, Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QButtonGroup,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from wildlife.ui.theme.icons import icon, pixmap
from wildlife.ui.theme.manager import ThemeManager


def clear_layout(layout) -> None:
    """Remove and delete everything in a layout.

    Widgets are hidden straight away: deleteLater() only happens once the event
    loop runs, and until then an unplaced widget would still draw (at Qt's
    default 640 x 480 size) on top of whatever replaces it."""
    while layout.count():
        item = layout.takeAt(0)
        if (w := item.widget()) is not None:
            w.hide()
            w.deleteLater()


def button(
    text: str,
    variant: str = "secondary",
    icon_name: str | None = None,
    theme: ThemeManager | None = None,
    on_click: Callable[[], None] | None = None,
) -> QPushButton:
    """A themed button. variant: primary | secondary | ghost | link."""
    btn = QPushButton(text)
    btn.setProperty("variant", variant)
    btn.setCursor(Qt.CursorShape.PointingHandCursor)
    if icon_name and theme:

        def paint() -> None:
            t = theme.tokens
            colour = (
                t.accent_fg if variant == "primary" else t.accent if variant == "link" else t.text_2
            )
            btn.setIcon(icon(icon_name, colour, 16))

        paint()
        theme.changed.connect(paint)
    if on_click:
        btn.clicked.connect(on_click)
    return btn


class Segmented(QFrame):
    """A row of mutually exclusive options, e.g. System / Light / Dark."""

    changed = Signal(str)

    def __init__(
        self, options: Sequence[tuple[str, str]], current: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.setObjectName("Segmented")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(3, 3, 3, 3)
        layout.setSpacing(2)
        self._group = QButtonGroup(self)
        self._buttons: dict[str, QPushButton] = {}
        for key, label in options:
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.setChecked(key == current)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            # never squeeze a label: the layout must find room elsewhere
            btn.setSizePolicy(QSizePolicy.Policy.Minimum, QSizePolicy.Policy.Fixed)
            self._group.addButton(btn)
            self._buttons[key] = btn
            layout.addWidget(btn)
            btn.clicked.connect(lambda _=False, k=key: self.changed.emit(k))

    def set_current(self, key: str) -> None:
        self._buttons[key].setChecked(True)

    def button_for(self, key: str) -> QPushButton:
        return self._buttons[key]


class EmptyState(QFrame):
    """Icon + title + explanation + optional actions. Every empty list gets one."""

    def __init__(
        self,
        theme: ThemeManager,
        icon_name: str,
        title: str,
        text: str,
        actions: Sequence[QPushButton] = (),
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.setObjectName("EmptyState")
        self._theme, self._icon_name = theme, icon_name
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 40, 24, 40)
        layout.setSpacing(8)
        self._icon = QLabel()
        self._icon.setObjectName("EmptyStateIcon")
        self._icon.setFixedSize(52, 52)
        self._icon.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label = QLabel(title)
        title_label.setObjectName("EmptyStateTitle")
        body = QLabel(text)
        body.setObjectName("EmptyStateText")
        body.setWordWrap(True)
        # A wrapped label centred in a layout gets its height before its width and
        # clips to one line; a fixed width avoids that (the window is >= 1024 px wide).
        body.setFixedWidth(460)
        body.setAlignment(Qt.AlignmentFlag.AlignHCenter)
        body.setMinimumHeight(body.heightForWidth(460))
        for w in (self._icon, title_label, body):
            layout.addWidget(w, 0, Qt.AlignmentFlag.AlignHCenter)
        if actions:
            row = QHBoxLayout()
            row.setSpacing(8)
            row.addStretch()
            for a in actions:
                row.addWidget(a)
            row.addStretch()
            layout.addSpacing(8)
            layout.addLayout(row)
        self._paint()
        theme.changed.connect(self._paint)

    def _paint(self) -> None:
        self._icon.setPixmap(pixmap(self._icon_name, self._theme.tokens.accent_subtle_text, 26))


class Callout(QFrame):
    """A tinted note: tone is info | warning | good."""

    def __init__(self, theme: ThemeManager, icon_name: str, text: str, tone: str = "info") -> None:
        super().__init__()
        self.setObjectName("Callout")
        self.setProperty("tone", tone)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(10)
        self._icon = QLabel()
        self._icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        self._label = QLabel(text)
        self._label.setWordWrap(True)
        self._label.setTextFormat(Qt.TextFormat.RichText)
        layout.addWidget(self._icon)
        layout.addWidget(self._label, 1)

        def paint() -> None:
            t = theme.tokens
            colour = {"warning": t.warning, "good": t.good_text}.get(tone, t.text_2)
            self._icon.setPixmap(pixmap(icon_name, colour, 17))

        paint()
        theme.changed.connect(paint)

    def set_text(self, text: str) -> None:
        self._label.setText(text)


class Page(QWidget):
    """Standard page: a title row (title, subtitle, actions) above scrolling content."""

    def __init__(self, title: str, subtitle: str = "", actions: Sequence[QWidget] = ()) -> None:
        super().__init__()
        self.setObjectName("Page")
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        scroll = QScrollArea()
        scroll.setObjectName("PageScroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        outer.addWidget(scroll)
        body = QWidget()
        body.setObjectName("PageBody")
        scroll.setWidget(body)
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(28, 24, 28, 40)
        self.body.setSpacing(16)
        head = QHBoxLayout()
        head.setSpacing(12)
        titles = QVBoxLayout()
        titles.setSpacing(2)
        title_label = QLabel(title)
        title_label.setObjectName("PageTitle")
        titles.addWidget(title_label)
        self.subtitle = QLabel(subtitle)
        self.subtitle.setObjectName("PageSubtitle")
        self.subtitle.setVisible(bool(subtitle))
        titles.addWidget(self.subtitle)
        head.addLayout(titles, 1)
        for a in actions:
            head.addWidget(a, 0, Qt.AlignmentFlag.AlignBottom)
        self.body.addLayout(head)

    def add(self, widget: QWidget, stretch: int = 0) -> QWidget:
        self.body.addWidget(widget, stretch)
        return widget

    def finish(self) -> None:
        """Push content to the top."""
        spacer = QWidget()
        spacer.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding)
        self.body.addWidget(spacer, 1)
