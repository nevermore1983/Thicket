"""Settings: only options that matter, each explained in a line."""

from __future__ import annotations

from datetime import date, datetime

from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wildlife import __version__
from wildlife.config.settings import Theme
from wildlife.context import AppContext
from wildlife.domain.filters import SightingFilter
from wildlife.services.import_history import SOURCE_NAMES
from wildlife.ui.components.common import Callout, Page, Segmented, button
from wildlife.ui.components.visuals import fmt_date, plural
from wildlife.ui.regions import AddPackDialog, region_name
from wildlife.ui.theme.manager import ThemeManager


def _row(title: str, explanation: str, control: QWidget) -> QFrame:
    row = QFrame()
    row.setObjectName("SettingsRow")
    layout = QHBoxLayout(row)
    layout.setContentsMargins(0, 12, 0, 12)
    text = QVBoxLayout()
    text.setSpacing(2)
    name = QLabel(title)
    name.setProperty("role", "rowTitle")
    sub = QLabel(explanation)
    sub.setProperty("role", "muted")
    sub.setWordWrap(True)
    text.addWidget(name)
    text.addWidget(sub)
    layout.addLayout(text, 1)
    layout.addWidget(control, 0, Qt.AlignmentFlag.AlignVCenter)
    # A text box or menu is named after its row ("Your name"), with the explanation read too
    for field in [control, *control.findChildren(QWidget)]:
        if isinstance(field, (QLineEdit, QComboBox)) and not field.accessibleName():
            field.setAccessibleName(title)
            field.setAccessibleDescription(explanation)
    return row


def _section(title: str, rows: list[QWidget]) -> QFrame:
    card = QFrame()
    card.setObjectName("Card")
    layout = QVBoxLayout(card)
    layout.setContentsMargins(18, 16, 18, 8)
    layout.setSpacing(0)
    heading = QLabel(title)
    heading.setProperty("role", "sectionTitle")
    layout.addWidget(heading)
    layout.addSpacing(4)
    for i, r in enumerate(rows):
        r.setProperty("first", i == 0)  # no divider directly under the heading
        layout.addWidget(r)
    return card


def _pair(*widgets: QWidget) -> QWidget:
    holder = QWidget()
    h = QHBoxLayout(holder)
    h.setContentsMargins(0, 0, 0, 0)
    h.setSpacing(8)
    for w in widgets:
        h.addWidget(w)
    return holder


class SettingsPage(QWidget):
    backup_requested = Signal()
    import_requested = Signal(str)  # 'inaturalist', 'csv' or 'wildlife'
    export_requested = Signal()
    health_requested = Signal()
    restore_requested = Signal()
    show_sightings = Signal(object)  # SightingFilter
    shortcuts_requested = Signal()
    toast = Signal(str, object)

    def __init__(self, ctx: AppContext, theme: ThemeManager) -> None:
        super().__init__()
        self.ctx, self.theme = ctx, theme
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._page: Page | None = None
        self.refresh()

    def refresh(self) -> None:
        if self._page is not None:
            scroll = self._page.findChild(QWidget, "PageScroll")
            position = scroll.verticalScrollBar().value() if scroll else 0
            self._layout.removeWidget(self._page)
            self._page.deleteLater()
        else:
            position = 0
        self._page = self._build()
        self._layout.addWidget(self._page)
        scroll = self._page.findChild(QWidget, "PageScroll")
        if scroll:
            scroll.verticalScrollBar().setValue(position)

    def _build(self) -> Page:
        ctx, theme, s = self.ctx, self.theme, self.ctx.settings.current
        page = Page("Settings")

        # general
        name = QLineEdit(s.recorder_name)
        name.setPlaceholderText("e.g. Sam Recorder")
        name.setMinimumWidth(240)
        name.editingFinished.connect(lambda: ctx.settings.update(recorder_name=name.text().strip()))
        page.add(
            _section(
                "General", [_row("Your name", "Added to exports as the recorder. Optional.", name)]
            )
        )
        page.add(_section("Region", self._region_rows()))

        # appearance
        self.theme_choice = Segmented(
            [(Theme.SYSTEM, "System"), (Theme.LIGHT, "Light"), (Theme.DARK, "Dark")], s.theme
        )
        self.theme_choice.changed.connect(self._set_theme)
        page.add(
            _section(
                "Appearance",
                [_row("Theme", "Follow Windows, or always use light or dark.", self.theme_choice)],
            )
        )

        # recording
        remember = QComboBox()
        for label, hours in (("1 hour", 1), ("3 hours", 3), ("12 hours", 12), ("Never", 0)):
            remember.addItem(label, hours)
        remember.setCurrentIndex(max(0, remember.findData(s.remember_place_hours)))
        remember.activated.connect(
            lambda i: ctx.settings.update(remember_place_hours=remember.itemData(i))
        )
        probable = QCheckBox("Count them")
        probable.setChecked(s.count_probable_ids)
        probable.toggled.connect(lambda on: ctx.settings.update(count_probable_ids=on))
        page.add(
            _section(
                "Recording",
                [
                    _row(
                        "Remember the last place for",
                        "New sightings start at the place you used last, for this long.",
                        remember,
                    ),
                    _row(
                        "Probable identifications",
                        "When off, only certain identifications add to your life and year lists.",
                        probable,
                    ),
                ],
            )
        )

        # online
        online = QCheckBox("Allow")
        online.setChecked(s.allow_online)
        online.toggled.connect(lambda on: ctx.settings.update(allow_online=on))
        page.add(
            _section(
                "Online features",
                [
                    _row(
                        "Online background map",
                        "Map tiles come from OpenFreeMap. Only the map areas you view are "
                        "requested; your sightings never leave this PC. When off, the map "
                        "shows a plain outline.",
                        online,
                    ),
                ],
            )
        )

        # backup
        page.add(_section("Backup", self._backup_rows()))

        # import & export
        page.add(_section("Import & export", self._exchange_rows()))

        # data
        binned, loose_photos = self._bin_contents()
        open_bin = button("Open…", "secondary", "trash", theme, self._open_bin)
        open_bin.setEnabled(bool(binned or loose_photos))
        empty_bin = _pair(open_bin, button("Empty now", "secondary", None, None, self._empty_bin))
        empty_bin.setEnabled(bool(binned or loose_photos))
        folder = QLabel(str(ctx.paths.root))
        folder.setProperty("role", "muted")
        folder.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        data_rows: list[QWidget] = []
        if ctx.paths.is_cloud_synced():
            data_rows.append(
                Callout(
                    theme,
                    "alert",
                    "Your data folder is inside a cloud-synced folder (such as OneDrive). Syncing a "
                    "database while WildLife is open can damage it. Keep live data on this PC and "
                    "use the cloud folder for backups instead.",
                    tone="warning",
                )
            )
        data_rows += [
            _row(
                "Data folder",
                "Your database, photos and logs live here.",
                _pair(
                    folder,
                    button(
                        "Open folder",
                        "secondary",
                        "folder",
                        theme,
                        lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ctx.paths.root))),
                    ),
                ),
            ),
            _row(
                "Recycle bin",
                f"{plural(binned, 'sighting')} · {plural(loose_photos, 'photo')} · "
                "emptied automatically after "
                f"{s.recycle_bin_days} days",
                empty_bin,
            ),
            _row(
                "Health check",
                "Checks your data file, every photo file, backups and the species list.",
                button("Check now", "secondary", "shield", theme, self.health_requested.emit),
            ),
            _row(
                "Species list",
                f"UK Species Inventory, version {ctx.catalogue.installed_version() or 'not installed'}"
                " · Natural History Museum, CC BY 4.0",
                QLabel(""),
            ),
        ]
        page.add(_section("Data", data_rows))

        # about
        page.add(
            _section(
                "About",
                [
                    _row(
                        f"WildLife {__version__}",
                        f"Data format version {ctx.schema_version}. Species names: UK Species Inventory, Natural History "
                        "Museum (CC BY 4.0). Map data © OpenStreetMap contributors.",
                        _pair(
                            button(
                                "Keyboard shortcuts",
                                "secondary",
                                None,
                                None,
                                self.shortcuts_requested.emit,
                            ),
                            button(
                                "Open log folder",
                                "secondary",
                                None,
                                None,
                                lambda: QDesktopServices.openUrl(
                                    QUrl.fromLocalFile(str(ctx.paths.logs))
                                ),
                            ),
                        ),
                    ),
                ],
            )
        )
        page.finish()
        return page

    def _backup_rows(self) -> list[QWidget]:
        ctx, theme = self.ctx, self.theme
        rows: list[QWidget] = []
        last = ctx.backup.last_result()
        if last is None:
            rows.append(
                Callout(
                    theme, "shield", "No backup yet. One is made automatically each day.", "warning"
                )
            )
        else:
            when = datetime.fromisoformat(last.when).astimezone()
            stamp = f"{fmt_date(when.date(), 'medium')} at {when:%H:%M}"
            if last.ok:
                rows.append(
                    Callout(
                        theme,
                        "shield",
                        f"<b>Last backup: {stamp}, verified.</b> "
                        f"{plural(len(ctx.backup.snapshots()), 'snapshot')} kept.",
                        "good",
                    )
                )
            else:
                rows.append(
                    Callout(
                        theme,
                        "alert",
                        f"<b>Last backup failed ({stamp}).</b> {last.message}",
                        "warning",
                    )
                )
        if ctx.backup.uses_default_folder():
            rows.append(
                Callout(
                    theme,
                    "alert",
                    "Backups are on the same drive as your data, which won't help if the "
                    "drive fails. Choose another drive or a cloud-synced folder.",
                    "warning",
                )
            )
        where = QLabel(str(ctx.backup.folder()))
        where.setProperty("role", "muted")
        where.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        change = button("Change…", "secondary", "folder", theme, self._choose_folder)
        rows.append(
            _row(
                "Backup folder",
                "Best on another drive or a cloud-synced folder.",
                _pair(where, change),
            )
        )
        auto = QCheckBox("On")
        auto.setChecked(ctx.settings.current.auto_backup)
        auto.toggled.connect(lambda on: ctx.settings.update(auto_backup=on))
        rows.append(
            _row(
                "Automatic backups",
                "Daily, and when you close WildLife after making changes.",
                auto,
            )
        )
        rows.append(
            _row(
                "Back up now",
                "Takes a few seconds. You can keep working.",
                button("Back up now", "primary", "shield", theme, self.backup_requested.emit),
            )
        )
        rows.append(
            _row(
                "Restore",
                "Bring back your data as it was in an earlier backup. Your current data is "
                "kept as a safety copy.",
                button("Restore…", "secondary", "rotate", theme, self.restore_requested.emit),
            )
        )
        return rows

    def _exchange_rows(self) -> list[QWidget]:
        theme = self.theme

        def importer(kind: str) -> QPushButton:
            return button(
                "Import…", "secondary", "upload", theme, lambda: self.import_requested.emit(kind)
            )

        rows: list[QWidget] = [
            _row(
                "From iNaturalist",
                "Your observations from an iNaturalist export. Importing again later only adds "
                "what's new or changed.",
                importer("inaturalist"),
            ),
            _row(
                "From a spreadsheet",
                "Any table of sightings saved as CSV (Excel, Google Sheets, other apps).",
                importer("csv"),
            ),
            _row(
                "From a WildLife export",
                "Sightings (and photos) exported from WildLife on this or another PC.",
                importer("wildlife"),
            ),
            _row(
                "Export",
                "A spreadsheet, Darwin Core for iRecord / NBN Atlas, map data, or everything "
                "with photos.",
                button("Export…", "secondary", "download", theme, self.export_requested.emit),
            ),
        ]
        for batch in self.ctx.import_history.batches()[:5]:
            rows.append(self._batch_row(batch))
        return rows

    def _batch_row(self, batch) -> QWidget:
        when = datetime.fromisoformat(batch.imported_at).astimezone()
        source = SOURCE_NAMES.get(batch.source, batch.source)
        title = f"Imported {fmt_date(when.date(), 'medium')} · {source}"
        if batch.live:
            detail = f"{batch.file_name or ''} · {plural(batch.live, 'sighting')}"
        else:
            detail = f"{batch.file_name or ''} · removed"
        show = button(
            "Show",
            "link",
            None,
            None,
            lambda: self.show_sightings.emit(SightingFilter(import_batch_id=batch.id)),
        )
        remove = button("Remove…", "ghost", None, None, lambda: self._remove_batch(batch))
        show.setEnabled(bool(batch.live))
        remove.setEnabled(bool(batch.live))
        return _row(title, detail, _pair(show, remove))

    def _remove_batch(self, batch) -> None:
        answer = QMessageBox.question(
            self,
            "Remove this import?",
            f"Move the {plural(batch.live, 'sighting')} from this import to the recycle bin? "
            "You can undo this, or restore them from the bin for "
            f"{self.ctx.settings.current.recycle_bin_days} days.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            undo = self.ctx.import_history.remove(batch.id)
            self.toast.emit(
                f"Import removed ({plural(batch.live, 'sighting')} in the recycle bin)",
                undo.run if undo else None,
            )
            self.refresh()

    # ---- actions --------------------------------------------------------------
    def _set_theme(self, key: str) -> None:
        theme = Theme(key)
        self.ctx.settings.update(theme=theme)
        self.theme.set_theme(theme)

    def _choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Choose where backups go")
        if folder:
            self.ctx.settings.update(backup_folder=folder)
            self.toast.emit("Backup folder changed. Making a backup there now.", None)
            self.backup_requested.emit()

    def _open_bin(self) -> None:
        dialog = RecycleBinDialog(self.ctx, self)
        dialog.exec()
        if dialog.restored:
            self.toast.emit(f"Restored {plural(dialog.restored, 'sighting')}", None)
        self.refresh()

    # ---- region (docs/16-regions-plan.md) ---------------------------------------
    def _region_rows(self) -> list[QWidget]:
        region = QComboBox()
        current = self.ctx.catalogue.region()
        for pack in self.ctx.catalogue.packs():
            region.addItem(pack["name"], pack["region"])
        region.setCurrentIndex(max(0, region.findData(current)))
        region.activated.connect(lambda i: self._choose_region(region.itemData(i)))
        add = button("Add a US state…", "secondary", "plus", self.theme, self._add_pack)
        packs = len(self.ctx.catalogue.packs())
        return [
            _row(
                "Where you record",
                "Species suggestions and common names follow it. Your sightings stay as they are.",
                region,
            ),
            _row(
                "Species packs",
                f"{plural(packs, 'region')} added. A US state's species come from GBIF; "
                "adding one needs the internet once.",
                add,
            ),
        ]

    def _choose_region(self, region: str) -> None:
        if region == self.ctx.catalogue.region():
            return
        self.ctx.catalogue.set_region(region)
        self.toast.emit(
            f"Showing {region_name(self.ctx, region)}'s species names and suggestions", None
        )
        self.refresh()

    def _add_pack(self) -> None:
        dialog = AddPackDialog(self.ctx, self)
        if dialog.exec() and dialog.installed_region:
            name = region_name(self.ctx, dialog.installed_region)
            shown = self.ctx.catalogue.region() == dialog.installed_region
            self.toast.emit(
                f"{name} added" + (": its names and suggestions are shown" if shown else ""), None
            )
            self.refresh()

    def _bin_contents(self) -> tuple[int, int]:
        """(sightings, photos deleted on their own) in the recycle bin. Photos of deleted
        sightings are in the bin with their sighting, so they aren't counted twice."""
        loose = [p for p in self.ctx.photos.recycle_bin() if not p.sighting_ids]
        return len(self.ctx.sightings.recycle_bin()), len(loose)

    def _empty_bin(self) -> None:
        sightings, photos = self._bin_contents()
        what = " and ".join(
            plural(n, word) for n, word in ((sightings, "sighting"), (photos, "photo")) if n
        )
        answer = QMessageBox.question(
            self,
            "Empty the recycle bin?",
            f"Permanently delete {what}, with their photo files? This can't be undone.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
        )
        if answer == QMessageBox.StandardButton.Yes:
            removed = self.ctx.sightings.purge_recycle_bin(0)
            files = self.ctx.photos.purge_recycle_bin(0)  # theirs too, and loose photos
            self.toast.emit(
                f"Recycle bin emptied ({plural(removed, 'sighting')}, {plural(files, 'photo')})",
                None,
            )
            self.refresh()


class RecycleBinDialog(QDialog):
    """Deleted sightings and photos, kept for 30 days: select and restore."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx, self.restored = ctx, 0
        self.setWindowTitle("Recycle bin")
        self.setMinimumSize(520, 420)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        note = QLabel(
            f"Deleted sightings and photos are kept for {ctx.settings.current.recycle_bin_days} days. "
            "Select any to restore."
        )
        note.setProperty("role", "muted")
        note.setWordWrap(True)
        v.addWidget(note)
        self.list = QListWidget()
        self.list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        for sid, name, observed, deleted in ctx.sightings.recycle_bin():
            item = QListWidgetItem(
                f"{name}  ·  seen {fmt_date(date.fromisoformat(observed), 'medium')}"
                f"  ·  deleted {deleted[:10]}"
            )
            item.setData(Qt.ItemDataRole.UserRole, ("sighting", sid))
            self.list.addItem(item)
        for photo in ctx.photos.recycle_bin():
            if photo.sighting_ids:
                continue  # in the bin with its sighting: restoring the sighting brings it back
            item = QListWidgetItem(f"Photo: {photo.original_name}")
            item.setData(Qt.ItemDataRole.UserRole, ("photo", photo.id))
            self.list.addItem(item)
        v.addWidget(self.list, 1)
        buttons = QDialogButtonBox()
        restore = buttons.addButton("Restore selected", QDialogButtonBox.ButtonRole.AcceptRole)
        restore.setProperty("variant", "primary")
        buttons.addButton(QDialogButtonBox.StandardButton.Close)
        restore.clicked.connect(self._restore)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)

    def _restore(self) -> None:
        chosen = [i.data(Qt.ItemDataRole.UserRole) for i in self.list.selectedItems()]
        sightings = [i for kind, i in chosen if kind == "sighting"]
        photos = [i for kind, i in chosen if kind == "photo"]
        if sightings:
            self.ctx.sightings.restore(sightings)
        if photos:
            self.ctx.photos.restore(photos)  # back to the Photo Inbox
        self.restored += len(chosen)
        self.accept()
