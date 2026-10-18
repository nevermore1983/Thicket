"""Photos: the Library (photos on sightings) and the Inbox (photos waiting for a sighting)."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from pathlib import Path

import shiboken6
from PySide6.QtCore import QSettings, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.domain import geo
from wildlife.domain.dates import fmt_date
from wildlife.domain.filters import SightingFilter
from wildlife.domain.models import Photo
from wildlife.domain.photo_groups import Encounter, group_encounters
from wildlife.services.photos import ImportSummary
from wildlife.ui.components.common import Callout, EmptyState, Segmented, button, clear_layout
from wildlife.ui.components.filter_bar import FilterBar
from wildlife.ui.components.flow_layout import flow_box
from wildlife.ui.components.photo_grid import GridItem, PhotoGrid
from wildlife.ui.components.thumbnails import ThumbnailLoader
from wildlife.ui.components.visuals import plural
from wildlife.ui.photos.choose_sighting import ChooseSightingDialog
from wildlife.ui.photos.viewer import PhotoViewer
from wildlife.ui.theme.icons import pixmap
from wildlife.ui.theme.manager import ThemeManager
from wildlife.ui.workers import run_in_background


def _scroll(widget: QWidget) -> QScrollArea:
    area = QScrollArea()
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setObjectName("PageScroll")
    area.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    area.setWidget(widget)
    return area


def encounter_heading(ctx: AppContext, e: Encounter) -> str:
    """'Sun 11 Oct 2026 · 08:00–08:13 · near Rainham Marshes · 3 photos'."""
    parts = []
    if e.start:
        start = datetime.strptime(e.start, "%Y-%m-%d %H:%M:%S")
        end = datetime.strptime(e.end, "%Y-%m-%d %H:%M:%S")
        times = f"{start:%H:%M}" + (f"–{end:%H:%M}" if end != start else "")
        parts += [fmt_date(start.date()), times]
    else:
        parts.append("Date unknown")
    located = next((p for p in e.photos if p.gps_latitude is not None), None)
    if located:
        near = ctx.places.nearest(located.gps_latitude, located.gps_longitude)
        ref = geo.grid_ref_for(located.gps_latitude, located.gps_longitude, 100)
        lat, lon = located.gps_latitude, located.gps_longitude
        parts.append(f"near {near.name}" if near else (ref or f"{lat:.3f}, {lon:.3f}"))
    parts.append(plural(len(e.photos), "photo"))
    return " · ".join(parts)


class PhotosPage(QWidget):
    open_sighting = Signal(int)
    create_sighting = Signal(list)  # photo ids: open the add panel with them
    toast = Signal(str, object)  # message, undo callable or None

    def __init__(self, ctx: AppContext, theme: ThemeManager) -> None:
        super().__init__()
        self.setObjectName("Page")
        self.setAcceptDrops(True)
        self.ctx, self.theme = ctx, theme
        self.loader = ThumbnailLoader(ctx.photos, self)
        self.filter = SightingFilter()
        self._library: list = []
        self._inbox_grids: list[PhotoGrid] = []
        self._importing = False
        v = QVBoxLayout(self)
        v.setContentsMargins(28, 24, 28, 16)
        v.setSpacing(12)

        head = QHBoxLayout()
        title = QLabel("Photos")
        title.setObjectName("PageTitle")
        head.addWidget(title)
        head.addSpacing(12)
        self.tabs = Segmented([("library", "Library"), ("inbox", "Inbox")], "library")
        self.tabs.changed.connect(self.show_tab)
        head.addWidget(self.tabs)
        head.addStretch(1)
        self.import_button = button("Import photos…", "primary", "upload", theme, self._import_menu)
        self.import_button.setToolTip("Import photos or a whole folder (or drop them here)")
        head.addWidget(self.import_button)
        v.addLayout(head)

        self.progress_row = QWidget()
        pr = QHBoxLayout(self.progress_row)
        pr.setContentsMargins(0, 0, 0, 0)
        self.progress_label = QLabel()
        self.progress_label.setProperty("role", "muted")
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        pr.addWidget(self.progress_label)
        pr.addWidget(self.progress, 1)
        self.progress_row.hide()
        v.addWidget(self.progress_row)

        self.stack = QStackedWidget()
        self.stack.addWidget(self._build_library())
        self.stack.addWidget(self._build_inbox())
        v.addWidget(self.stack, 1)
        self.refresh()

    # ---- Library ---------------------------------------------------------------------
    def _build_library(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        row = QHBoxLayout()
        self.filter_bar = FilterBar(self.ctx, self.theme)
        self.filter_bar.changed.connect(self._filter_changed)
        row.addWidget(self.filter_bar, 1)
        self.size_slider = QSlider(Qt.Orientation.Horizontal)
        self.size_slider.setRange(110, 320)
        self.size_slider.setValue(int(QSettings().value("photos/tile", 168)))
        self.size_slider.setFixedWidth(120)
        self.size_slider.setToolTip("Thumbnail size")
        self.size_slider.setAccessibleName("Thumbnail size")
        self.size_slider.valueChanged.connect(self._tile_changed)
        small, large = QLabel(), QLabel()  # a small and a large picture: what the slider sizes

        def paint_size_icons() -> None:
            colour = self.theme.tokens.text_3
            small.setPixmap(pixmap("image", colour, 12))
            large.setPixmap(pixmap("image", colour, 18))

        paint_size_icons()
        self.theme.changed.connect(paint_size_icons)
        row.addWidget(small)
        row.addWidget(self.size_slider)
        row.addWidget(large)
        v.addLayout(row)
        self.missing_note = Callout(self.theme, "alert", "", "warning")
        self.missing_note.hide()
        v.addWidget(self.missing_note)
        self.find_missing = button(
            "Look in a folder…", "secondary", "folder", self.theme, self._find_missing
        )
        self.find_missing.setToolTip("Thicket looks through a folder for the missing files")
        self.find_missing.hide()
        v.addWidget(self.find_missing, 0, Qt.AlignmentFlag.AlignLeft)
        self.library_grid = PhotoGrid(self.loader, self.theme, tile=self.size_slider.value())
        self.library_grid.activated.connect(self._open_library_photo)
        self.library_stack = QStackedWidget()
        holder = QWidget()
        hv = QVBoxLayout(holder)
        hv.setContentsMargins(0, 0, 4, 0)
        hv.addWidget(self.library_grid)
        hv.addStretch(1)
        self.library_stack.addWidget(_scroll(holder))
        self.library_empty = QWidget()
        self._library_empty_layout = QVBoxLayout(self.library_empty)
        self._library_empty_layout.setContentsMargins(0, 0, 0, 0)
        self.library_stack.addWidget(self.library_empty)
        v.addWidget(self.library_stack, 1)
        self.library_footer = QLabel()
        self.library_footer.setProperty("role", "muted")
        v.addWidget(self.library_footer)
        return box

    def _refresh_library(self) -> None:
        self._library = self.ctx.photos.library(self.filter)
        items = [
            GridItem(
                i.photo,
                i.name,
                fmt_date(date.fromisoformat(i.observed_date), "medium"),
                tooltip=f"{i.name} · {fmt_date(date.fromisoformat(i.observed_date))}\n{i.photo.original_name}",
            )
            for i in self._library
        ]
        self.library_grid.set_items(items)
        clear_layout(self._library_empty_layout)
        if items:
            self.library_stack.setCurrentIndex(0)
        else:
            filtered = not self.filter.is_empty
            self._library_empty_layout.addWidget(
                EmptyState(
                    self.theme,
                    "image",
                    "No photos match these filters" if filtered else "No photos yet",
                    "Try fewer filters."
                    if filtered
                    else "Photos you attach to sightings appear here. Import photos from your "
                    "phone or camera: they wait in the Inbox until you say what they show.",
                    []
                    if filtered
                    else [
                        button("Import photos…", "primary", "upload", self.theme, self._import_menu)
                    ],
                )
            )
            self._library_empty_layout.addStretch(1)
            self.library_stack.setCurrentIndex(1)
        raw = sum(1 for i in self._library if i.photo.has_raw)
        self.library_footer.setText(
            plural(len(items), "photo")
            + (f" · {raw:,} with a RAW original" if raw else "")
            + ("  ·  Click a photo to view it full screen" if items else "")
        )
        run_in_background(self.ctx.photos.missing, on_done=self._show_missing)

    def _show_missing(self, missing: list[Photo]) -> None:
        if missing:
            self.missing_note.set_text(
                f"<b>{plural(len(missing), 'photo file')} {'is' if len(missing) == 1 else 'are'} "
                "missing</b> from your library folder (moved or deleted outside Thicket). "
                "If you moved them, let Thicket look in that folder; or open one to locate "
                "its file or remove the photo."
            )
        self.missing_note.setVisible(bool(missing))
        self.find_missing.setVisible(bool(missing))

    def _find_missing(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Where might the photos be?")
        if not folder:
            return
        self.find_missing.setEnabled(False)

        def done(found: int) -> None:
            if shiboken6.isValid(self):
                self.find_missing.setEnabled(True)
                self.toast.emit(
                    f"{plural(found, 'photo file')} found and put back"
                    if found
                    else "None of the missing photos are in that folder",
                    None,
                )
                self._refresh_library()

        run_in_background(lambda: self.ctx.photos.find_in_folder(Path(folder)), done)

    def _filter_changed(self, flt: SightingFilter) -> None:
        self.filter = flt
        self._refresh_library()

    def set_filter(self, flt: SightingFilter) -> None:
        self.show_tab("library")
        self.filter_bar.set_filter(flt)

    def _tile_changed(self, size: int) -> None:
        QSettings().setValue("photos/tile", size)
        self.library_grid.set_tile_size(size)
        for grid in self._inbox_grids:
            grid.set_tile_size(size)

    def _open_library_photo(self, index: int) -> None:
        self.open_viewer(
            [i.photo for i in self._library],
            index,
            titles=[
                f"{i.name} · {fmt_date(date.fromisoformat(i.observed_date))}" for i in self._library
            ],
        )

    # ---- Inbox -----------------------------------------------------------------------
    def _build_inbox(self) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(12)
        self.inbox_intro = Callout(
            self.theme,
            "info",
            "These photos aren't on a sighting yet. Select the photos of one sighting, then "
            "choose <b>Create sighting</b>: the date, time and position come from the photos. "
            "Photos taken within 10 minutes and 200 m of each other are grouped to help you.",
        )
        v.addWidget(self.inbox_intro)
        self.bulk = QFrame()
        self.bulk.setObjectName("BulkBar")
        bh = QHBoxLayout(self.bulk)
        bh.setContentsMargins(14, 6, 8, 6)
        self.bulk_label = QLabel()
        self.bulk_label.setObjectName("BulkLabel")
        bh.addWidget(self.bulk_label, 0, Qt.AlignmentFlag.AlignTop)
        buttons, flow = flow_box(6)  # wraps onto two lines when the side panel is open
        for text, slot in (
            ("Create sighting", self._create_sighting),
            ("Add to existing sighting…", self._add_to_existing),
            ("View", self._view_selected),
            ("Fix time…", self._fix_time),
            ("Delete", self._delete_selected),
            ("Clear selection", self._clear_inbox_selection),
        ):
            b = QPushButton(text)
            b.setProperty("variant", "bulk")
            b.clicked.connect(slot)
            flow.addWidget(b)
        bh.addWidget(buttons, 1)
        self.bulk.hide()
        v.addWidget(self.bulk)
        self.inbox_body = QWidget()
        self._inbox_layout = QVBoxLayout(self.inbox_body)
        self._inbox_layout.setContentsMargins(0, 0, 4, 0)
        self._inbox_layout.setSpacing(18)
        v.addWidget(_scroll(self.inbox_body), 1)
        return box

    def _refresh_inbox(self) -> None:
        clear_layout(self._inbox_layout)
        self._inbox_grids = []
        photos = self.ctx.photos.inbox()
        self.inbox_intro.setVisible(bool(photos))
        if not photos:
            self._inbox_layout.addWidget(
                EmptyState(
                    self.theme,
                    "inbox",
                    "The Inbox is empty",
                    "Import photos from your phone or camera, or drop them here. Thicket reads "
                    "the date, time and position from each photo; RAW files are kept with their "
                    "JPEGs. Then you say what each photo shows.",
                    [button("Import photos…", "primary", "upload", self.theme, self._import_menu)],
                )
            )
            self._inbox_layout.addStretch(1)
            self._selection_changed()
            return
        for encounter in group_encounters(photos):
            self._inbox_layout.addWidget(self._encounter_box(encounter))
        self._inbox_layout.addStretch(1)
        self._selection_changed()

    def _encounter_box(self, encounter: Encounter) -> QWidget:
        box = QWidget()
        v = QVBoxLayout(box)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(8)
        row = QHBoxLayout()
        heading = QLabel(encounter_heading(self.ctx, encounter))
        heading.setProperty("role", "sectionTitle")
        row.addWidget(heading)
        row.addStretch(1)
        grid = PhotoGrid(
            self.loader, self.theme, selectable=True, tile=self.size_slider.value(), captions=False
        )
        grid.set_items(
            [
                GridItem(
                    p,
                    overlay=(p.taken_at[11:16] if p.taken_at else "No date")
                    + (" · GPS" if p.gps_latitude is not None else ""),
                    tooltip=f"{p.original_name}" + (f"\nRAW: {p.raw_name}" if p.raw_name else ""),
                )
                for p in encounter.photos
            ]
        )
        grid.selection_changed.connect(self._selection_changed)
        grid.activated.connect(lambda index, g=grid: self._open_inbox_photo(g, index))
        select = QPushButton("Select group")
        select.setProperty("variant", "link")
        select.clicked.connect(grid.select_all)
        row.addWidget(select)
        v.addLayout(row)
        v.addWidget(grid)
        self._inbox_grids.append(grid)
        return box

    def selected_inbox_photos(self) -> list[Photo]:
        return [p for g in self._inbox_grids for p in g.selected_photos()]

    def _selection_changed(self) -> None:
        chosen = self.selected_inbox_photos()
        self.bulk.setVisible(bool(chosen))
        self.bulk_label.setText(f"{plural(len(chosen), 'photo')} selected")

    def _clear_inbox_selection(self) -> None:
        for grid in self._inbox_grids:
            grid.clear_selection()

    def _create_sighting(self) -> None:
        chosen = self.selected_inbox_photos()
        if chosen:
            self.create_sighting.emit([p.id for p in chosen])

    def _add_to_existing(self) -> None:
        chosen = self.selected_inbox_photos()
        if not chosen:
            return
        dated = sorted(p.taken_at for p in chosen if p.taken_at)
        around = date.fromisoformat(dated[0][:10]) if dated else None
        dialog = ChooseSightingDialog(self.ctx, self.theme, around, self.window())
        if dialog.exec() and dialog.chosen is not None:
            self.ctx.photos.attach(dialog.chosen, [p.id for p in chosen])
            name = self.ctx.sightings.get(dialog.chosen).display_name
            self.toast.emit(f"{plural(len(chosen), 'photo')} added to {name}", None)

    def _fix_time(self) -> None:
        """Move the selected photos' times, e.g. for a camera clock an hour out."""
        chosen = [p for p in self.selected_inbox_photos() if p.taken_at]
        if not chosen:
            self.toast.emit("These photos have no time to fix", None)
            return
        dialog = QDialog(self)
        dialog.setWindowTitle("Fix the time")
        dialog.setMinimumWidth(420)
        dv = QVBoxLayout(dialog)
        intro = QLabel(
            f"Move the time of {plural(len(chosen), 'photo')} by the same amount, for "
            "example if the camera's clock was an hour behind."
        )
        intro.setWordWrap(True)
        dv.addWidget(intro)
        row = QHBoxLayout()
        hours, minutes = QSpinBox(), QSpinBox()
        hours.setRange(-48, 48)
        minutes.setRange(-59, 59)
        hours.setSuffix(" h")
        minutes.setSuffix(" min")
        hours.setAccessibleName("Hours to add (negative to go back)")
        minutes.setAccessibleName("Minutes to add (negative to go back)")
        row.addWidget(hours)
        row.addWidget(minutes)
        row.addStretch(1)
        dv.addLayout(row)
        preview = QLabel()
        preview.setProperty("role", "help")
        dv.addWidget(preview)
        first = datetime.fromisoformat(chosen[0].taken_at)

        def update() -> None:
            moved = first + timedelta(hours=hours.value(), minutes=minutes.value())
            preview.setText(f"First photo: {first:%d %b %Y %H:%M} becomes {moved:%d %b %Y %H:%M}")

        hours.valueChanged.connect(update)
        minutes.valueChanged.connect(update)
        update()
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        dv.addWidget(buttons)
        if dialog.exec() and (shift := hours.value() * 60 + minutes.value()):
            undo = self.ctx.photos.shift_times([p.id for p in chosen], shift)
            self.toast.emit(f"Time of {plural(len(chosen), 'photo')} changed", undo.run)

    def _delete_selected(self) -> None:
        chosen = self.selected_inbox_photos()
        if chosen:
            undo = self.ctx.photos.delete([p.id for p in chosen])
            self.toast.emit(f"{plural(len(chosen), 'photo')} moved to the recycle bin", undo.run)

    def _view_selected(self) -> None:
        chosen = self.selected_inbox_photos()
        if chosen:
            self.open_viewer(chosen, 0)

    def _open_inbox_photo(self, grid: PhotoGrid, index: int) -> None:
        photos = [p for g in self._inbox_grids for p in (i.photo for i in g.items)]
        self.open_viewer(photos, photos.index(grid.items[index].photo))

    # ---- shared ----------------------------------------------------------------------
    def open_viewer(
        self, photos: list[Photo], index: int, titles: list[str] | None = None
    ) -> PhotoViewer:
        viewer = PhotoViewer(
            self.ctx, self.theme, photos, index, titles=titles, parent=self.window()
        )
        viewer.open_sighting.connect(self.open_sighting)
        viewer.changed.connect(self._photo_changed)
        viewer.open_full()
        return viewer

    def _photo_changed(self, photo_id: int) -> None:
        self.library_grid.refresh_photo(photo_id)
        for grid in self._inbox_grids:
            grid.refresh_photo(photo_id)

    def show_tab(self, key: str) -> None:
        self.tabs.set_current(key)
        self.stack.setCurrentIndex(0 if key == "library" else 1)
        self.refresh()

    def current_tab(self) -> str:
        return "library" if self.stack.currentIndex() == 0 else "inbox"

    def refresh(self) -> None:
        inbox = self.ctx.photos.inbox_count()
        self.tabs.button_for("inbox").setText(f"Inbox ({inbox:,})" if inbox else "Inbox")
        if self.current_tab() == "library":
            self._refresh_library()
        else:
            self._refresh_inbox()

    # ---- importing -------------------------------------------------------------------
    def _import_menu(self) -> None:
        menu = QMenu(self)
        menu.addAction("Choose photos…", self.choose_files)
        menu.addAction("Choose a folder…", self.choose_folder)
        menu.exec(self.import_button.mapToGlobal(self.import_button.rect().bottomLeft()))

    def choose_files(self) -> None:
        from wildlife.domain.photo_files import SUPPORTED_SUFFIXES

        patterns = " ".join(f"*{s}" for s in SUPPORTED_SUFFIXES)
        files, _ = QFileDialog.getOpenFileNames(
            self, "Import photos", "", f"Photos and RAW files ({patterns})"
        )
        if files:
            self.import_paths([Path(f) for f in files])

    def choose_folder(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Import a folder of photos")
        if folder:
            self.import_paths([Path(folder)])

    def import_paths(self, paths: list[Path]) -> None:
        """Import in the background; the page stays usable and shows progress."""
        if self._importing:
            self.toast.emit("An import is already running", None)
            return
        self._importing = True
        self.import_button.setEnabled(False)
        self.progress_row.show()
        self.progress_label.setText("Looking for photos…")
        self.progress.setRange(0, 0)

        def work(progress):
            return self.ctx.photos.import_files(
                paths, lambda done, total: progress(f"{done}/{total}", done / total if total else 1)
            )

        run_in_background(
            work,
            on_done=self._imported,
            on_error=self._import_failed,
            on_progress=self._import_progress,
        )

    def _import_progress(self, step: str, fraction: float) -> None:
        done, total = step.split("/")
        self.progress.setRange(0, 1000)
        self.progress.setValue(int(fraction * 1000))
        self.progress_label.setText(f"Importing {min(int(done) + 1, int(total))} of {total}…")

    def _import_finished(self) -> None:
        self._importing = False
        self.import_button.setEnabled(True)
        self.progress_row.hide()

    def _imported(self, summary: ImportSummary) -> None:
        self._import_finished()
        message = summary.describe()
        if summary.failed:
            message += f" ({', '.join(name for name, _ in summary.failed[:3])}{'…' if len(summary.failed) > 3 else ''})"
        self.toast.emit(message, None)
        if summary.imported:
            self.show_tab("inbox")
        else:
            self.refresh()

    def _import_failed(self, exc: BaseException) -> None:
        self._import_finished()
        self.toast.emit(f"The import stopped: {exc}", None)

    def dragEnterEvent(self, event) -> None:
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        paths = [Path(u.toLocalFile()) for u in event.mimeData().urls() if u.isLocalFile()]
        if paths:
            self.import_paths(paths)
