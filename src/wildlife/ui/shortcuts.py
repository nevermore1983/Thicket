"""The keyboard shortcuts sheet (press ? or F1): every shortcut in one place."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from wildlife.ui.components.common import button

SHEET: tuple[tuple[str, tuple[tuple[str, str], ...]], ...] = (
    (
        "Anywhere",
        (
            ("Ctrl+N", "Add a sighting"),
            ("Ctrl+K", "Search sightings, species, places and dates"),
            (
                "Ctrl+1 … Ctrl+8",
                "Dashboard, Sightings, Calendar, Map, Photos, Statistics, Species, Places",
            ),
            ("Ctrl+Z", "Undo the last change"),
            ("Esc", "Close the side panel"),
            ("Tab / Shift+Tab", "Move between controls"),
            ("Arrow keys", "Move between options in a row (e.g. Year · Month · Week · Day)"),
            ("? or F1", "This list"),
        ),
    ),
    (
        "Adding or editing a sighting",
        (
            ("Ctrl+S", "Save"),
            ("Ctrl+Enter", "Save and add another"),
            ("↑ ↓, Enter", "Choose a species from the suggestions"),
        ),
    ),
    (
        "Sightings list",
        (
            ("Enter", "Open the selected sighting"),
            ("Delete", "Move the selected sightings to the recycle bin"),
            ("E", "Edit the open sighting (in its side panel)"),
        ),
    ),
    (
        "Calendar",
        (
            ("← → ↑ ↓", "Choose a day (a week at a time with ↑ ↓)"),
            ("Enter", "Open the chosen day"),
            ("Page Up / Page Down", "Previous / next month, year, week or day"),
            ("T", "Today"),
            ("Y  M  W  D", "Year, month, week or day view"),
            ("N", "Add a sighting on the chosen day"),
        ),
    ),
    (
        "Photos",
        (
            ("Arrow keys, Home, End", "Move through the photos"),
            ("Space", "Select or unselect (Inbox)"),
            ("Ctrl+A", "Select all (Inbox)"),
            ("Enter", "View full screen"),
        ),
    ),
    (
        "Photo viewer",
        (
            ("← →, Home, End", "Previous / next, first / last photo"),
            ("Z", "Zoom to full size"),
            ("R", "Turn the photo"),
            ("I", "Show or hide the details"),
            ("Esc", "Close"),
        ),
    ),
    (
        "Charts",
        (
            ("Arrow keys", "Move between bars, columns or cells"),
            ("Enter", "Show those sightings"),
        ),
    ),
)


class ShortcutsDialog(QDialog):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setWindowTitle("Keyboard shortcuts")
        self.setMinimumSize(560, 560)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 18)
        v.setSpacing(10)
        title = QLabel("Keyboard shortcuts")
        title.setObjectName("EmptyStateTitle")
        v.addWidget(title)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        body = QWidget()
        b = QVBoxLayout(body)
        b.setContentsMargins(0, 0, 8, 0)
        b.setSpacing(14)
        for section, rows in SHEET:
            heading = QLabel(section)
            heading.setProperty("role", "sectionTitle")
            b.addWidget(heading)
            grid = QGridLayout()
            grid.setHorizontalSpacing(18)
            grid.setVerticalSpacing(6)
            for r, (keys, what) in enumerate(rows):
                key = QLabel(keys)
                key.setObjectName("KeyCap")
                key.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
                grid.addWidget(key, r, 0, Qt.AlignmentFlag.AlignTop)
                text = QLabel(what)
                text.setWordWrap(True)
                grid.addWidget(text, r, 1)
            grid.setColumnStretch(1, 1)
            grid.setColumnMinimumWidth(0, 170)
            b.addLayout(grid)
        b.addStretch(1)
        scroll.setWidget(body)
        v.addWidget(scroll, 1)
        foot = QHBoxLayout()
        foot.addStretch(1)
        close = button("Close", "primary", None, None, self.accept)
        close.setDefault(True)
        foot.addWidget(close)
        v.addLayout(foot)
