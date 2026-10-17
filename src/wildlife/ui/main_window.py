"""The application shell: sidebar, top bar, pages and the side panel, and the flows between them."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta

from PySide6.QtCore import QSettings, Qt, QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.domain.codes import LocationMethod
from wildlife.domain.dates import DateQuery
from wildlife.domain.errors import BackupError, NotFoundError
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import Outing, SightingDraft
from wildlife.services.sightings import SaveResult
from wildlife.ui.components.common import button
from wildlife.ui.components.side_panel import SidePanel
from wildlife.ui.components.toast import ToastHost
from wildlife.ui.dialogs import SearchPopup
from wildlife.ui.exchange.export_dialog import ExportDialog
from wildlife.ui.exchange.import_dialog import ImportDialog
from wildlife.ui.maintenance.health_dialog import HealthDialog
from wildlife.ui.maintenance.restore_dialog import RestoreDialog
from wildlife.ui.pages.calendar_page import CalendarPage
from wildlife.ui.pages.dashboard_page import DashboardPage
from wildlife.ui.pages.list_pages import PlacesPage, SpeciesPage
from wildlife.ui.pages.map_page import MapPage
from wildlife.ui.pages.photos_page import PhotosPage
from wildlife.ui.pages.settings_page import SettingsPage
from wildlife.ui.pages.sightings_page import SightingsPage
from wildlife.ui.pages.statistics_page import StatisticsPage
from wildlife.ui.panels.day_panel import DayPanel
from wildlife.ui.panels.outing_detail import OutingDetail
from wildlife.ui.panels.outing_editor import OutingEditor
from wildlife.ui.panels.place_editor import PlaceEditor
from wildlife.ui.panels.sighting_detail import SightingDetail
from wildlife.ui.panels.sighting_editor import SightingEditor
from wildlife.ui.panels.sighting_list import SightingListPanel
from wildlife.ui.panels.species_profile import SpeciesProfile
from wildlife.ui.photos.viewer import PhotoViewer
from wildlife.ui.qt_events import QtEvents
from wildlife.ui.shortcuts import ShortcutsDialog
from wildlife.ui.single_instance import restart_wildlife
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
    "sightings": {"sightings", "outings", "places", "taxa", "settings"},
    "calendar": {"sightings", "outings", "taxa", "settings"},
    "map": {"sightings", "taxa", "settings"},
    "photos": {"photos", "sightings", "taxa", "places"},
    "statistics": {"sightings", "outings", "places", "taxa", "settings"},
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
        self._refresh_timer = QTimer(self, singleShot=True, interval=0)
        self._refresh_timer.timeout.connect(self._refresh_visible)
        self._day_timer = QTimer(self, singleShot=True)
        self._day_timer.timeout.connect(self._new_day)
        self._schedule_new_day()
        self._build_pages()
        self._install_shortcuts()
        self._paint_icons()
        theme.changed.connect(self._paint_icons)
        self.events = QtEvents(ctx.events, self)
        self.events.changed.connect(self._on_data_changed)
        self.search_popup = SearchPopup(ctx, theme, self.search)
        self.search_popup.chosen.connect(self.show_sightings)
        self.search_popup.date_chosen.connect(self.show_date)
        self._update_outing_chip()
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
        # No QButtonGroup: Qt would let Tab reach only the current page's link. go() keeps
        # exactly one link checked instead.
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
        self.outing_chip = QPushButton()
        self.outing_chip.setObjectName("OutingChip")
        self.outing_chip.setCursor(Qt.CursorShape.PointingHandCursor)
        self.outing_chip.setToolTip("Open the outing in progress")
        self.outing_chip.clicked.connect(
            lambda: self.open_outing(self._live_outing) if self._live_outing else None
        )
        self.outing_chip.hide()
        self._live_outing: int | None = None
        h.addWidget(self.outing_chip)
        self.add_button = button("Add sighting", "primary", "plus", self.theme, self.add_sighting)
        self.add_button.setToolTip("Add sighting (Ctrl+N)")
        h.addWidget(self.add_button)
        return bar

    def _build_pages(self) -> None:
        t, ctx = self.theme, self.ctx
        self.dashboard = DashboardPage(ctx, t)
        self.dashboard.open_sighting.connect(self.open_sighting)
        self.dashboard.add_requested.connect(self.add_sighting)
        self.dashboard.import_requested.connect(self.import_data)
        self.dashboard.show_sightings.connect(self.show_sightings)
        self.dashboard.backup_requested.connect(self.backup_now)
        self.sightings_page = SightingsPage(ctx, t)
        self.sightings_page.open_sighting.connect(self.open_sighting)
        self.sightings_page.add_requested.connect(self.add_sighting)
        self.sightings_page.export_requested.connect(self.export_data)
        self.sightings_page.toast.connect(self._toast)
        self.sightings_page.outings.open_outing.connect(self.open_outing)
        self.sightings_page.outings.new_outing.connect(lambda: self.new_outing(None))
        self.sightings_page.outings.start_outing.connect(self.start_outing)
        self.calendar_page = CalendarPage(ctx, t)
        self.calendar_page.open_sighting.connect(self.open_sighting)
        self.calendar_page.add_on.connect(self.add_on_date)
        self.calendar_page.open_day.connect(self.open_day)
        self.calendar_page.open_outing.connect(self.open_outing)
        self.calendar_page.new_outing.connect(self.new_outing)
        self.species_page = SpeciesPage(ctx, t)
        self.species_page.show_sightings.connect(self.show_sightings)
        self.species_page.open_profile.connect(self.open_species)
        self.species_page.add_requested.connect(self.add_sighting)
        self.places_page = PlacesPage(ctx, t)
        self.places_page.new_place.connect(lambda: self.edit_place(None))
        self.places_page.edit_place.connect(self.edit_place)
        self.settings_page = SettingsPage(ctx, t)
        self.settings_page.backup_requested.connect(self.backup_now)
        self.settings_page.toast.connect(self._toast)
        self.settings_page.import_requested.connect(self.import_data)
        self.settings_page.export_requested.connect(self.export_data)
        self.settings_page.health_requested.connect(self.health_check)
        self.settings_page.restore_requested.connect(self.restore_backup)
        self.settings_page.show_sightings.connect(self.show_sightings)
        self.settings_page.shortcuts_requested.connect(self.show_shortcuts)
        self.map_page = MapPage(ctx, t)
        self.map_page.open_sighting.connect(lambda sid: self.open_sighting(sid))
        self.map_page.show_ids.connect(self.show_sighting_list)
        self.map_page.add_at.connect(self.add_at)
        self.map_page.new_place_at.connect(lambda lat, lon: self.edit_place(None, at=(lat, lon)))
        self.map_page.show_sightings.connect(self.show_sightings)
        self.calendar_page.show_map.connect(self.show_map)
        self.photos_page = PhotosPage(ctx, t)
        self.photos_page.open_sighting.connect(lambda sid: self.open_sighting(sid))
        self.photos_page.create_sighting.connect(self.add_from_photos)
        self.photos_page.toast.connect(self._toast)
        self.dashboard.open_inbox.connect(
            lambda: (self.go("photos"), self.photos_page.show_tab("inbox"))
        )
        self.dashboard.open_day.connect(
            lambda d: (self.go("calendar"), self.calendar_page.go_to(d, "day"))
        )
        self.statistics_page = StatisticsPage(ctx, t)
        self.statistics_page.show_sightings.connect(self.show_sightings)
        self.statistics_page.add_requested.connect(self.add_sighting)
        self.statistics_page.import_requested.connect(self.import_data)
        self.statistics_page.open_sighting.connect(lambda sid: self.open_sighting(sid))
        pages = {
            "dashboard": self.dashboard,
            "sightings": self.sightings_page,
            "calendar": self.calendar_page,
            "map": self.map_page,
            "photos": self.photos_page,
            "statistics": self.statistics_page,
            "species": self.species_page,
            "places": self.places_page,
            "settings": self.settings_page,
        }
        for key in [e.key for e in NAV] + ["settings"]:
            self._page_index[key] = self.pages.addWidget(pages[key])

    def _install_shortcuts(self) -> None:
        for i, entry in enumerate(NAV):
            QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self, activated=lambda k=entry.key: self.go(k))
        QShortcut(QKeySequence("Ctrl+N"), self, activated=self.add_sighting)
        QShortcut(QKeySequence("Ctrl+K"), self, activated=self.focus_search)
        QShortcut(QKeySequence("Ctrl+Z"), self, activated=self._undo)
        QShortcut(QKeySequence("F1"), self, activated=self.show_shortcuts)
        QShortcut(
            QKeySequence(Qt.Key.Key_Escape),
            self.panel,
            activated=self._escape,
            context=Qt.ShortcutContext.WidgetWithChildrenShortcut,
        )

    # ---- navigation ---------------------------------------------------------
    def go(self, key: str) -> None:
        self.pages.setCurrentIndex(self._page_index[key])
        for k, b in self._nav_buttons.items():
            b.setChecked(k == key)
        if key in self._stale:
            self._stale.discard(key)
            getattr(self.pages.currentWidget(), "refresh", lambda: None)()

    def current_page(self) -> str:
        index = self.pages.currentIndex()
        return next(k for k, i in self._page_index.items() if i == index)

    def import_data(self, kind: str = "inaturalist") -> ImportDialog:
        """Open the import window for 'inaturalist', 'csv' or 'wildlife'."""
        dialog = ImportDialog(self.ctx, self.theme, kind, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        title = dialog.windowTitle().removeprefix("Import from ").removeprefix("Import a ")
        dialog.imported.connect(
            lambda r: self._toast(
                f"Import ({title}): {r.describe()}", r.undo.run if r.undo else None
            )
        )
        dialog.show_sightings.connect(self.show_sightings)
        dialog.open()
        return dialog

    def export_data(self, flt: SightingFilter | None = None) -> ExportDialog:
        dialog = ExportDialog(self.ctx, self.theme, flt, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.open()
        return dialog

    def health_check(self) -> HealthDialog:
        dialog = HealthDialog(self.ctx, self.theme, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.backup_requested.connect(lambda: self.backup_now("manual"))
        dialog.restore_requested.connect(self.restore_backup)
        dialog.choose_backup_folder.connect(self.settings_page._choose_folder)
        dialog.open()
        return dialog

    def restore_backup(self) -> RestoreDialog:
        dialog = RestoreDialog(self.ctx, self.theme, self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.restart_requested.connect(self.restart_to_restore)
        dialog.open()
        return dialog

    def restart_to_restore(self) -> None:
        """A backup is waiting to be restored: start a fresh WildLife, then close this one."""
        if self.panel.isVisible() and not self.panel.close_panel():
            self._toast("The backup will be restored next time WildLife starts.", None)
            return
        if not restart_wildlife(str(self.ctx.paths.root)):
            QMessageBox.information(
                self,
                "Restore",
                "Please close WildLife and open it again to finish restoring the backup.",
            )
            return
        self.close()

    def show_restore_outcome(self, outcome) -> None:
        if outcome.ok:
            when = outcome.created.astimezone()
            extra = (
                f" · {outcome.photos_copied:,} photo files brought back"
                if outcome.photos_copied
                else ""
            )
            self._toast(
                f"Backup from {when:%d %b %Y at %H:%M} restored{extra}. "
                "Your previous data is in the safety-copies folder.",
                None,
            )
        else:
            QMessageBox.warning(self, "Restore", outcome.message)

    def show_sightings(self, flt: SightingFilter) -> None:
        self.search.clear()
        self.go("sightings")
        self.sightings_page.set_filter(flt)

    def focus_search(self) -> None:
        self.search.setFocus(Qt.FocusReason.ShortcutFocusReason)
        self.search.selectAll()

    def _on_data_changed(self, topic: str, _ids: tuple) -> None:
        """Refresh the visible page straight after the change; mark the others to refresh
        when next shown. The refresh waits for the next turn of the event loop, so the
        save itself (and its panel and message) finishes first, and several changes in a
        row (an import, a bulk edit) give one refresh, not one each."""
        for key, topics in REFRESH_ON.items():
            if topic in topics:
                self._stale.add(key)
        if any(topic in topics for topics in REFRESH_ON.values()):
            self._refresh_timer.start()
        if topic in ("outings", "sightings"):
            self._update_outing_chip()
        if topic == "places":
            self.map_page.places_changed()
        if topic == "settings":
            self.map_page.settings_changed()
        view = self.panel.current()
        reload_on = {
            SightingDetail: ("sightings", "taxa"),
            DayPanel: ("sightings", "outings", "taxa", "settings"),
            OutingDetail: ("sightings", "outings", "taxa", "settings"),
        }
        if view is not None and topic in reload_on.get(type(view), ()):
            try:
                view.reload()
            except NotFoundError:
                self.panel.close_panel()

    def _refresh_visible(self) -> None:
        current = self.current_page()
        if current in self._stale:
            self._stale.discard(current)
            getattr(self.pages.currentWidget(), "refresh", lambda: None)()

    def _schedule_new_day(self) -> None:
        """Wake just after midnight. (If the PC is asleep then, on waking instead.)"""
        now = datetime.now()
        midnight = datetime.combine(now.date() + timedelta(days=1), time(0, 0, 5))
        self._day_timer.start(int((midnight - now).total_seconds() * 1000))

    def _new_day(self) -> None:
        """A new day: pages showing "today" (the dashboard's week, the calendar's
        highlight, "this year") were drawn yesterday. Redraw the one on screen now and
        the others when they're next shown."""
        self._stale.update(REFRESH_ON)
        self._refresh_visible()
        self._schedule_new_day()

    def show_date(self, q: DateQuery) -> None:
        """A date chosen in search ("May 2025"): open it in the calendar."""
        self.search.clear()
        self.go("calendar")
        self.calendar_page.jump(q)

    def open_day(self, day: date, flt: SightingFilter) -> None:
        panel = DayPanel(self.ctx, self.theme, day, flt)
        panel.open_sighting.connect(lambda sid: self.open_sighting(sid, push=True))
        panel.add_on.connect(self.add_on_date)
        panel.open_day_view.connect(
            lambda d: (self.panel.close_panel(), self.calendar_page.go_to(d, "day"))
        )
        panel.open_outing.connect(lambda oid: self.open_outing(oid, push=True))
        self.panel.show_view(panel)

    def add_on_date(self, day: date) -> None:
        self.add_sighting(SightingDraft(taxon_id=None, observed_date=day))

    # ---- sightings ------------------------------------------------------------
    def add_sighting(self, prefill: SightingDraft | None = None) -> None:
        editor = SightingEditor(
            self.ctx, self.theme, prefill=prefill if isinstance(prefill, SightingDraft) else None
        )
        self._wire_editor(editor)
        self.panel.show_view(editor)

    def open_sighting(self, sighting_id: int, push: bool = False) -> None:
        detail = SightingDetail(self.ctx, self.theme, sighting_id)
        detail.edit_requested.connect(self.edit_sighting)
        detail.delete_requested.connect(self.delete_sighting)
        detail.show_on_map.connect(self.show_sighting_on_map)
        detail.view_photo.connect(self.view_sighting_photos)
        self.panel.show_view(detail, push=push and self.panel.isVisible())

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
                outing_id=s.outing_id,
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

    # ---- outings ------------------------------------------------------------------
    def open_outing(self, outing_id: int, push: bool = False) -> None:
        detail = OutingDetail(self.ctx, self.theme, outing_id)
        detail.open_sighting.connect(lambda sid: self.open_sighting(sid, push=True))
        detail.edit_requested.connect(self.edit_outing)
        detail.delete_requested.connect(self.delete_outing)
        detail.end_requested.connect(self.end_outing)
        detail.add_requested.connect(self.add_to_outing)
        detail.show_list.connect(lambda flt: (self.panel.close_panel(), self.show_sightings(flt)))
        detail.show_map.connect(lambda flt: (self.panel.close_panel(), self.show_map(flt)))
        self.panel.show_view(detail, push=push and self.panel.isVisible())

    def new_outing(self, day: date | None) -> None:
        editor = OutingEditor(self.ctx, self.theme, on_date=day)
        self._wire_outing_editor(editor)
        self.panel.show_view(editor)

    def edit_outing(self, outing_id: int) -> None:
        editor = OutingEditor(self.ctx, self.theme, existing=self.ctx.outings.get(outing_id))
        self._wire_outing_editor(editor)
        self.panel.show_view(editor, push=isinstance(self.panel.current(), OutingDetail))

    def _wire_outing_editor(self, editor: OutingEditor) -> None:
        def saved(outing: Outing, undo) -> None:
            created = editor.existing is None
            self._toast(f"{outing.display_title} {'saved' if created else 'updated'}", undo.run)
            if created:
                self.panel.close_panel()
                self.open_outing(outing.id)
            else:
                self._close_or_back()

        editor.saved.connect(saved)
        editor.cancelled.connect(self._close_or_back)

    def start_outing(self) -> None:
        place = self.ctx.sightings.default_place()
        outing = self.ctx.outings.start(place_id=place)
        self._toast(f"Outing started at {outing.start_time}. New sightings today join it.", None)
        self.open_outing(outing.id)

    def end_outing(self, outing_id: int) -> None:
        outing = self.ctx.outings.end(outing_id)
        self._toast(f"{outing.display_title} ended at {outing.end_time}", None)
        self.panel.close_panel()

    def add_to_outing(self, outing: Outing) -> None:
        self.add_sighting(
            SightingDraft(
                taxon_id=None,
                observed_date=outing.outing_date,
                place_id=outing.place_id,
                outing_id=outing.id,
            )
        )

    def delete_outing(self, outing_id: int) -> None:
        title = self.ctx.outings.get(outing_id).display_title
        undo = self.ctx.outings.delete(outing_id)
        self.panel.close_panel()
        self._toast(f"{title} deleted · its sightings are kept", undo.run)

    def _update_outing_chip(self) -> None:
        live = self.ctx.outings.in_progress()
        self._live_outing = live.id if live else None
        self.outing_chip.setVisible(live is not None)
        if live:
            where = live.place_name or live.title or "Outing"
            self.outing_chip.setText(
                f"●  {where} · since {live.start_time} · {live.sightings:,} seen"
            )

    # ---- species -----------------------------------------------------------------
    def open_species(self, taxon_id: int) -> None:
        profile = SpeciesProfile(self.ctx, self.theme, taxon_id)
        profile.show_sightings.connect(
            lambda flt: (self.panel.close_panel(), self.show_sightings(flt))
        )
        profile.show_map.connect(lambda flt: (self.panel.close_panel(), self.show_map(flt)))
        profile.view_photos.connect(self._view_photos)
        self.panel.show_view(profile)

    def _view_photos(self, photo_ids: list[int], index: int) -> None:
        photos = [self.ctx.photos.get(i) for i in photo_ids]
        PhotoViewer(self.ctx, self.theme, photos, index, parent=self).open_full()

    # ---- photos ------------------------------------------------------------------
    def add_from_photos(self, photo_ids: list[int]) -> None:
        """'Create sighting' from Inbox photos: date, time and position come from them."""
        editor = SightingEditor(self.ctx, self.theme, photo_ids=photo_ids)
        self._wire_editor(editor)
        self.panel.show_view(editor)

    def view_sighting_photos(self, sighting_id: int, index: int) -> None:
        s = self.ctx.sightings.get(sighting_id)
        photos = self.ctx.photos.for_sighting(sighting_id)
        viewer = PhotoViewer(
            self.ctx,
            self.theme,
            photos,
            index,
            sighting_id=sighting_id,
            titles=[s.display_name] * len(photos),
            parent=self,
        )
        viewer.open_full()

    # ---- map ---------------------------------------------------------------------
    def show_map(self, flt: SightingFilter) -> None:
        """Open the map showing these sightings (e.g. one day or one outing)."""
        self.go("map")
        self.map_page.set_filter(flt)

    def show_sighting_on_map(self, s) -> None:
        self.panel.close_panel()
        self.go("map")
        self.map_page.show_location(s.eff_latitude, s.eff_longitude)

    def show_sighting_list(self, ids: list[int]) -> None:
        panel = SightingListPanel(self.ctx, self.theme, ids, "Sightings here")
        panel.open_sighting.connect(lambda sid: self.open_sighting(sid, push=True))
        self.panel.show_view(panel)

    def add_at(self, lat: float, lon: float, uncertainty_m: int) -> None:
        self.add_sighting(
            SightingDraft(
                taxon_id=None,
                observed_date=None,
                latitude=round(lat, 6),
                longitude=round(lon, 6),
                uncertainty_m=uncertainty_m,
                location_method=LocationMethod.MAP,
            )
        )

    # ---- places -----------------------------------------------------------------
    def edit_place(self, place_id: int | None, at: tuple[float, float] | None = None) -> None:
        editor = PlaceEditor(
            self.ctx, self.theme, self.ctx.places.get(place_id) if place_id else None, at=at
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

    def show_shortcuts(self) -> ShortcutsDialog:
        dialog = ShortcutsDialog(self)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.open()
        return dialog

    def keyPressEvent(self, event) -> None:
        # "?" opens the shortcuts list. Text boxes take the key first, so typing "?" in
        # a note still types it.
        if event.text() == "?":
            self.show_shortcuts()
            return
        super().keyPressEvent(event)

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
