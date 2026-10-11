"""The application shell: sidebar, top bar, pages and the side panel, and the flows between them."""

from __future__ import annotations

import logging
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
from wildlife.domain.errors import BackupError, NotFoundError
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import SightingDraft
from wildlife.services.sightings import SaveResult
from wildlife.ui.components.common import button
from wildlife.ui.components.side_panel import SidePanel
from wildlife.ui.components.toast import ToastHost
from wildlife.ui.dialogs import SearchPopup
from wildlife.ui.pages import simple
from wildlife.ui.pages.dashboard_page import DashboardPage
from wildlife.ui.pages.list_pages import PlacesPage, SpeciesPage
from wildlife.ui.pages.settings_page import SettingsPage
from wildlife.ui.pages.sightings_page import SightingsPage
from wildlife.ui.panels.place_editor import PlaceEditor
from wildlife.ui.panels.sighting_detail import SightingDetail
from wildlife.ui.panels.sighting_editor import SightingEditor
from wildlife.ui.qt_events import QtEvents
from wildlife.ui.theme.icons import icon, pixmap
from wildlife.ui.theme.manager import ThemeManager
from wildlife.ui.workers import run_in_background

log = logging.getLogger(__name__)


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
REFRESH_ON = {  # which data changes each page cares about
    "dashboard": {"sightings", "places", "photos", "backup", "settings", "taxa"},
    "sightings": {"sightings", "places", "taxa", "settings"},
    "species": {"sightings", "taxa", "settings"},
    "places": {"places", "sightings"},
    "settings": {"backup", "settings", "sightings", "taxa"},
}


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
        self.panel = SidePanel(theme)
        layout.addWidget(self.panel)
        self.toasts = ToastHost(root, theme)

        self._page_index: dict[str, int] = {}
        self._stale: set[str] = set()
        self._build_pages()
        self._install_shortcuts()
        self._paint_icons()
        theme.changed.connect(self._paint_icons)
        self.events = QtEvents(ctx.events, self)
        self.events.changed.connect(self._on_data_changed)
        self.search_popup = SearchPopup(ctx, theme, self.search)
        self.search_popup.chosen.connect(self.show_sightings)
        start = ctx.settings.current.start_page
        self.go(start if start in self._page_index else "dashboard")
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
        h.addWidget(self.search, 1)
        h.addStretch()
        self.add_button = button("Add sighting", "primary", "plus", self.theme, self.add_sighting)
        self.add_button.setToolTip("Add sighting (Ctrl+N)")
        h.addWidget(self.add_button)
        return bar

    def _build_pages(self) -> None:
        t, ctx = self.theme, self.ctx
        self.dashboard = DashboardPage(ctx, t)
        self.dashboard.open_sighting.connect(self.open_sighting)
        self.dashboard.add_requested.connect(self.add_sighting)
        self.dashboard.show_sightings.connect(self.show_sightings)
        self.dashboard.backup_requested.connect(self.backup_now)
        self.sightings_page = SightingsPage(ctx, t)
        self.sightings_page.open_sighting.connect(self.open_sighting)
        self.sightings_page.add_requested.connect(self.add_sighting)
        self.sightings_page.toast.connect(self._toast)
        self.species_page = SpeciesPage(ctx, t)
        self.species_page.show_sightings.connect(self.show_sightings)
        self.places_page = PlacesPage(ctx, t)
        self.places_page.new_place.connect(lambda: self.edit_place(None))
        self.places_page.edit_place.connect(self.edit_place)
        self.settings_page = SettingsPage(ctx, t)
        self.settings_page.backup_requested.connect(self.backup_now)
        self.settings_page.toast.connect(self._toast)
        later = {
            "calendar": (
                "calendar",
                "Calendar arrives in Phase 7",
                "Your sightings will appear here by date, in year, month, week and day views.",
            ),
            "map": (
                "map",
                "The map arrives in Phase 8",
                "Sightings with a location will appear as pins, a heat map or grid squares.",
            ),
            "photos": (
                "image",
                "The photo library arrives in Phase 9",
                "You can already attach photos to sightings. The gallery, viewer and Photo Inbox come next.",
            ),
            "statistics": (
                "chart",
                "Statistics arrive in Phase 10",
                "Your species growth, busiest months and best places will show here.",
            ),
        }
        pages = {
            "dashboard": self.dashboard,
            "sightings": self.sightings_page,
            "species": self.species_page,
            "places": self.places_page,
            "settings": self.settings_page,
        }
        for key, (ic, heading, text) in later.items():
            pages[key] = simple.coming_soon(
                t, next(e.label for e in NAV if e.key == key), ic, heading, text, self.add_sighting
            )
        for key in [e.key for e in NAV] + ["settings"]:
            self._page_index[key] = self.pages.addWidget(pages[key])

    def _install_shortcuts(self) -> None:
        for i, entry in enumerate(NAV):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self, activated=lambda k=entry.key: self.go(k))
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.add_sighting)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.focus_search)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._undo)
        QShortcut(
            QKeySequence(Qt.Key.Key_Escape),
            self.panel,
            activated=self._escape,
            context=Qt.ShortcutContext.WidgetWithChildrenShortcut,
        )

    # ---- navigation ---------------------------------------------------------
    def go(self, key: str) -> None:
        self.pages.setCurrentIndex(self._page_index[key])
        self._nav_buttons[key].setChecked(True)
        if key in self._stale:
            self._stale.discard(key)
            getattr(self.pages.currentWidget(), "refresh", lambda: None)()

    def current_page(self) -> str:
        index = self.pages.currentIndex()
        return next(k for k, i in self._page_index.items() if i == index)

    def show_sightings(self, flt: SightingFilter) -> None:
        self.search.clear()
        self.go("sightings")
        self.sightings_page.set_filter(flt)

    def focus_search(self) -> None:
        self.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search.selectAll()

    def _on_data_changed(self, topic: str, _ids: tuple) -> None:
        """Refresh the visible page now; mark the others to refresh when next shown."""
        current = self.current_page()
        for key, topics in REFRESH_ON.items():
            if topic in topics:
                if key == current:
                    getattr(self.pages.widget(self._page_index[key]), "refresh", lambda: None)()
                else:
                    self._stale.add(key)
        view = self.panel.current()
        if topic in ("sightings", "taxa") and isinstance(view, SightingDetail):
            try:
                view.reload()
            except NotFoundError:
                self.panel.close_panel()

    # ---- sightings ------------------------------------------------------------
    def add_sighting(self, prefill: SightingDraft | None = None) -> None:
        editor = SightingEditor(
            self.ctx, self.theme, prefill=prefill if isinstance(prefill, SightingDraft) else None
        )
        self._wire_editor(editor)
        self.panel.show_view(editor)

    def open_sighting(self, sighting_id: int) -> None:
        detail = SightingDetail(self.ctx, self.theme, sighting_id)
        detail.edit_requested.connect(self.edit_sighting)
        detail.delete_requested.connect(self.delete_sighting)
        self.panel.show_view(detail)

    def edit_sighting(self, sighting_id: int) -> None:
        editor = SightingEditor(self.ctx, self.theme, existing=self.ctx.sightings.get(sighting_id))
        self._wire_editor(editor)
        self.panel.show_view(editor, push=isinstance(self.panel.current(), SightingDetail))

    def _wire_editor(self, editor: SightingEditor) -> None:
        editor.saved.connect(lambda result, another: self._saved(editor, result, another))
        editor.cancelled.connect(self._close_or_back)

    def _saved(self, editor: SightingEditor, result: SaveResult, another: bool) -> None:
        s = result.sighting
        verb = "saved" if result.created else "updated"
        message = f"{s.display_name} {verb}" + (
            " · ★ new species for your life list!" if result.is_lifer else ""
        )
        self._toast(
            message,
            result.undo.run,
            open_=(lambda: self.open_sighting(s.id)) if result.created else None,
        )
        if another:
            prefill = SightingDraft(
                taxon_id=None,
                observed_date=s.observed_date,
                observed_time=s.observed_time,
                place_id=s.place_id,
            )
            fresh = SightingEditor(self.ctx, self.theme, prefill=prefill)
            self._wire_editor(fresh)
            self.panel.replace_top(fresh)
        else:
            self._close_or_back()

    def _close_or_back(self) -> None:
        view = self.panel.current()
        if view is not None:
            view._dirty = False  # already saved or deliberately cancelled
        self.panel.back()

    def delete_sighting(self, sighting_id: int) -> None:
        s = self.ctx.sightings.get(sighting_id)
        undo = self.ctx.sightings.delete([sighting_id])
        self.panel.close_panel()
        self._toast(f"{s.display_name} moved to the recycle bin", undo.run)

    # ---- places -----------------------------------------------------------------
    def edit_place(self, place_id: int | None) -> None:
        editor = PlaceEditor(
            self.ctx, self.theme, self.ctx.places.get(place_id) if place_id else None
        )
        editor.saved.connect(
            lambda place: (self._toast(f"{place.name} saved", None), self.panel.close_panel())
        )
        editor.removed.connect(
            lambda message: (self._toast(message, None), self.panel.close_panel())
        )
        editor.cancelled.connect(self.panel.close_panel)
        self.panel.show_view(editor)

    # ---- backups ------------------------------------------------------------------
    def backup_now(self, kind: str = "manual") -> None:
        if kind == "manual":
            self._toast("Backing up…", None)

        def done(result) -> None:
            if kind == "manual":
                self._toast(
                    f"Backed up and verified · {result.sightings:,} sightings, "
                    f"{result.photos_copied} new photos copied",
                    None,
                )

        def failed(exc: BaseException) -> None:
            message = (
                exc.user_message if isinstance(exc, BackupError) else "The backup didn't complete."
            )
            self._toast(f"Backup failed: {message}", None)

        run_in_background(
            lambda: self.ctx.backup.backup_now(kind if isinstance(kind, str) else "manual"),
            on_done=done,
            on_error=failed,
        )

    # ---- helpers ------------------------------------------------------------------
    def _toast(self, message: str, undo, open_=None) -> None:
        self.toasts.show(message, undo=undo, open_=open_)

    def _undo(self) -> None:
        if self.toasts.last_undo:
            undo, self.toasts.last_undo = self.toasts.last_undo, None
            undo()
            self.toasts.show("Undone")

    def _escape(self) -> None:
        if self.panel.isVisible():
            self.panel.back()

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

    def _restore_geometry(self) -> None:
        geometry = QSettings().value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)
        else:
            self.resize(1360, 860)

    def closeEvent(self, event: QCloseEvent) -> None:
        if self.panel.isVisible() and not self.panel.close_panel():
            event.ignore()  # unsaved changes and the user chose to keep editing
            return
        QSettings().setValue("window/geometry", self.saveGeometry())
        if self.ctx.backup.needed_on_exit():
            try:
                self.ctx.backup.backup_now("exit")
            except BackupError as exc:
                log.warning("Backup on exit failed: %s", exc.user_message)
        super().closeEvent(event)
