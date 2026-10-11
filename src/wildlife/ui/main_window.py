"""The application shell: sidebar navigation, top bar and the page area."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import QSettings, Qt
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.ui.components.common import button
from wildlife.ui.components.toast import ToastHost
from wildlife.ui.pages import simple
from wildlife.ui.pages.settings_page import SettingsPage
from wildlife.ui.theme.icons import icon, pixmap
from wildlife.ui.theme.manager import ThemeManager


@dataclass(frozen=True)
class NavEntry:
    key: str
    label: str
    icon: str


NAV = (
    NavEntry("dashboard", "Dashboard", "home"),
    NavEntry("sightings", "Sightings", "list"),
    NavEntry("calendar", "Calendar", "calendar"),
    NavEntry("map", "Map", "map"),
    NavEntry("photos", "Photos", "image"),
    NavEntry("statistics", "Statistics", "chart"),
    NavEntry("species", "Species", "leaf"),
    NavEntry("places", "Places", "pin"),
)
SETTINGS = NavEntry("settings", "Settings", "settings")
RAIL_BELOW = 900  # window width at which the sidebar shrinks to icons


class MainWindow(QMainWindow):
    def __init__(self, ctx: AppContext, theme: ThemeManager) -> None:
        super().__init__()
        self.ctx, self.theme = ctx, theme
        self.setWindowTitle("WildLife")
        self.setMinimumSize(1024, 640)
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(self._build_sidebar())
        main = QVBoxLayout()
        main.setContentsMargins(0, 0, 0, 0)
        main.setSpacing(0)
        main.addWidget(self._build_topbar())
        self.pages = QStackedWidget()
        main.addWidget(self.pages, 1)
        layout.addLayout(main, 1)
        self.toasts = ToastHost(root, theme)

        self._page_index: dict[str, int] = {}
        self._build_pages()
        self._install_shortcuts()
        self._paint_icons()
        theme.changed.connect(self._paint_icons)
        self.go(
            ctx.settings.current.start_page
            if ctx.settings.current.start_page in self._page_index
            else "dashboard"
        )
        self._restore_geometry()

    # ---- building -------------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        side = QWidget()
        side.setObjectName("Sidebar")
        side.setFixedWidth(228)
        v = QVBoxLayout(side)
        v.setContentsMargins(8, 12, 8, 12)
        v.setSpacing(2)
        brand = QHBoxLayout()
        brand.setContentsMargins(8, 4, 8, 16)
        brand.setSpacing(10)
        self._brand_mark = QLabel()
        self._brand_mark.setObjectName("BrandMark")
        self._brand_mark.setFixedSize(30, 30)
        self._brand_mark.setAlignment(Qt.AlignmentFlag.AlignCenter)
        brand.addWidget(self._brand_mark)
        names = QVBoxLayout()
        names.setSpacing(0)
        self._brand_name = QLabel("WildLife")
        self._brand_name.setObjectName("BrandName")
        self._brand_sub = QLabel("Your wildlife journal")
        self._brand_sub.setObjectName("BrandSub")
        names.addWidget(self._brand_name)
        names.addWidget(self._brand_sub)
        brand.addLayout(names, 1)
        v.addLayout(brand)

        self._nav_group = QButtonGroup(self)
        self._nav_buttons: dict[str, QPushButton] = {}
        for i, entry in enumerate((*NAV, SETTINGS)):
            if entry is SETTINGS:
                v.addStretch(1)
            btn = QPushButton(entry.label)
            btn.setObjectName("NavItem")
            btn.setCheckable(True)
            btn.setCursor(Qt.CursorShape.PointingHandCursor)
            btn.setToolTip(
                f"{entry.label} (Ctrl+{i + 1})" if entry is not SETTINGS else entry.label
            )
            btn.setAccessibleName(entry.label)
            btn.clicked.connect(lambda _=False, k=entry.key: self.go(k))
            self._nav_group.addButton(btn)
            self._nav_buttons[entry.key] = btn
            v.addWidget(btn)
        self._sidebar = side
        return side

    def _build_topbar(self) -> QWidget:
        bar = QWidget()
        bar.setObjectName("TopBar")
        h = QHBoxLayout(bar)
        h.setContentsMargins(24, 11, 24, 11)
        h.setSpacing(12)
        self.search = QLineEdit()
        self.search.setObjectName("GlobalSearch")
        self.search.setPlaceholderText("Search sightings, species, places…   (Ctrl+K)")
        self.search.setClearButtonEnabled(True)
        self.search.setAccessibleName("Search")
        self.search.setMaximumWidth(560)
        self._search_action = QAction(self.search)
        self.search.addAction(self._search_action, QLineEdit.ActionPosition.LeadingPosition)
        self.search.returnPressed.connect(
            lambda: self.toasts.show("Search arrives with sightings in the next phase")
        )
        h.addWidget(self.search, 1)
        h.addStretch()
        self.add_button = button("Add sighting", "primary", "plus", self.theme, self.add_sighting)
        self.add_button.setToolTip("Add sighting (Ctrl+N)")
        h.addWidget(self.add_button)
        return bar

    def _build_pages(self) -> None:
        t = self.theme
        later = {
            "sightings": (
                "list",
                "No sightings yet",
                "Sightings you add appear here. You'll be able to sort, filter and edit many at once.",
            ),
            "calendar": (
                "calendar",
                "Your calendar is empty",
                "Your sightings will appear here by date, in year, month, week and day views.",
            ),
            "map": (
                "map",
                "Nothing on the map yet",
                "Sightings with a location appear here as pins, a heat map or grid squares.",
            ),
            "photos": (
                "image",
                "No photos yet",
                "Import photos from your phone or camera. WildLife reads the date, time and place from "
                "each one, then you choose the species.",
            ),
            "statistics": (
                "chart",
                "Statistics appear once you have sightings",
                "Your species list, busiest months and best places will show here.",
            ),
            "species": (
                "leaf",
                "Your species list is empty",
                "Each species you record is added here, with when and where you first and last saw it.",
            ),
            "places": (
                "pin",
                "No places yet",
                "Save the spots you visit often, like your garden or a local reserve, to record faster.",
            ),
        }
        pages = {
            "dashboard": simple.dashboard(
                t, self.add_sighting, self._coming_soon, self._coming_soon
            )
        }
        for entry in NAV[1:]:
            ic, heading, text = later[entry.key]
            pages[entry.key] = simple.coming_soon(
                t, entry.label, ic, heading, text, self.add_sighting
            )
        pages["settings"] = SettingsPage(self.ctx, t)
        for key, page in pages.items():
            self._page_index[key] = self.pages.addWidget(page)

    def _install_shortcuts(self) -> None:
        for i, entry in enumerate(NAV):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self, activated=lambda k=entry.key: self.go(k))
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.add_sighting)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.focus_search)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._undo)

    # ---- behaviour ------------------------------------------------------
    def go(self, key: str) -> None:
        self.pages.setCurrentIndex(self._page_index[key])
        self._nav_buttons[key].setChecked(True)

    def current_page(self) -> str:
        index = self.pages.currentIndex()
        return next(k for k, i in self._page_index.items() if i == index)

    def focus_search(self) -> None:
        self.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search.selectAll()

    def add_sighting(self) -> None:
        self.toasts.show("Adding sightings arrives in the next phase")

    def _coming_soon(self) -> None:
        self.toasts.show("This arrives in a later phase")

    def _undo(self) -> None:
        if self.toasts.last_undo:
            undo, self.toasts.last_undo = self.toasts.last_undo, None
            undo()
            self.toasts.show("Undone")

    def _paint_icons(self) -> None:
        t = self.theme.tokens
        for entry in (*NAV, SETTINGS):
            self._nav_buttons[entry.key].setIcon(
                icon(entry.icon, t.text_2, 19, checked_colour=t.accent_subtle_text)
            )
        self._brand_mark.setPixmap(pixmap("leaf", t.accent_fg, 18, 2.0))
        self._search_action.setIcon(icon("search", t.text_3, 18))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        rail = self.width() < RAIL_BELOW
        self._sidebar.setFixedWidth(60 if rail else 228)
        self._brand_name.setVisible(not rail)
        self._brand_sub.setVisible(not rail)
        for entry in (*NAV, SETTINGS):
            self._nav_buttons[entry.key].setText("" if rail else entry.label)

    # ---- window state ---------------------------------------------------
    def _restore_geometry(self) -> None:
        geometry = QSettings().value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1280, 820)

    def closeEvent(self, event: QCloseEvent) -> None:
        QSettings().setValue("window/geometry", self.saveGeometry())
        super().closeEvent(event)
