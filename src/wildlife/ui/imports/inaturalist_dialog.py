"""Import from iNaturalist: choose the export → check what will happen → import (+ photos).

Nothing changes until "Import" is pressed, and the whole import can be undone in one go.
Reading the file, importing and fetching photos all run in the background.
"""

from __future__ import annotations

import threading
from pathlib import Path

import shiboken6
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QFileDialog,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QProgressBar,
    QScrollArea,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.domain.errors import WildlifeError
from wildlife.domain.filters import SightingFilter
from wildlife.services.inaturalist import ADD, SAME, SKIP, UPDATE, ImportPlan, ImportResult
from wildlife.ui.components.common import Callout, button
from wildlife.ui.components.species_picker import SpeciesPicker
from wildlife.ui.components.visuals import plural
from wildlife.ui.theme.manager import ThemeManager
from wildlife.ui.workers import run_in_background

HOW_TO = (
    "1. On <b>inaturalist.org</b>, open <b>Your observations › Export</b>.<br>"
    "2. Leave the filters as they are to export everything, then press <b>Create export</b>.<br>"
    "3. When it's ready, download it. WildLife opens the <b>.zip</b> as it comes, "
    "or the <b>.csv</b> inside it."
)


class InatImportDialog(QDialog):
    imported = Signal(object)  # ImportResult, for the main window's "Undo" toast
    show_sightings = Signal(object)  # SightingFilter

    def __init__(self, ctx: AppContext, theme: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx, self.theme = ctx, theme
        self.plan: ImportPlan | None = None
        self.result: ImportResult | None = None
        self.choices: dict[str, int] = {}
        self._cancel = threading.Event()
        self._busy = False
        self.setWindowTitle("Import from iNaturalist")
        self.setMinimumSize(560, 460)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 18)
        v.setSpacing(14)
        self.pages = QStackedWidget()
        v.addWidget(self.pages, 1)
        foot = QHBoxLayout()
        foot.addStretch(1)
        self.back_btn = button("Back", "secondary", None, None, self._back)
        self.close_btn = button("Cancel", "secondary", None, None, self.reject)
        self.go_btn = button("Import", "primary", None, None, self._import)
        for b in (self.back_btn, self.close_btn, self.go_btn):
            foot.addWidget(b)
        v.addLayout(foot)
        self.pages.addWidget(self._choose_page())
        self.pages.addWidget(self._check_page())
        self.pages.addWidget(self._done_page())
        self._show(0)

    # ---- pages ------------------------------------------------------------------------
    def _heading(self, layout: QVBoxLayout, title: str, text: str = "") -> QLabel:
        heading = QLabel(title)
        heading.setObjectName("EmptyStateTitle")
        layout.addWidget(heading)
        body = QLabel(text)
        body.setWordWrap(True)
        body.setTextFormat(Qt.TextFormat.RichText)
        body.setProperty("role", "muted")
        layout.addWidget(body)
        return body

    def _choose_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        self._heading(
            v,
            "Bring in your iNaturalist observations",
            "Your observations become WildLife sightings, matched to the UK species list. "
            "Research-grade IDs are marked <b>certain</b>; the rest <b>probable</b>. "
            "Importing the same export again later only adds what's new or changed.",
        )
        steps = QLabel(HOW_TO)
        steps.setWordWrap(True)
        steps.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(steps)
        row = QHBoxLayout()
        self.choose_btn = button(
            "Choose export file…", "primary", "upload", self.theme, self._pick_file
        )
        row.addWidget(self.choose_btn)
        row.addStretch(1)
        v.addLayout(row)
        self.choose_status = QLabel()
        self.choose_status.setWordWrap(True)
        v.addWidget(self.choose_status)
        v.addStretch(1)
        return page

    def _check_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        self.check_title = QLabel()
        self.check_title.setObjectName("EmptyStateTitle")
        v.addWidget(self.check_title)
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        self.summary.setTextFormat(Qt.TextFormat.RichText)
        v.addWidget(self.summary)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        self.check_body = QVBoxLayout(body)
        self.check_body.setContentsMargins(0, 0, 8, 0)
        self.check_body.setSpacing(10)
        scroll.setWidget(body)
        scroll.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        v.addWidget(scroll, 1)
        self.photos_box = QCheckBox("Also download the photos from iNaturalist")
        v.addWidget(self.photos_box)
        self.photos_note = QLabel()
        self.photos_note.setWordWrap(True)
        self.photos_note.setProperty("role", "caption")
        v.addWidget(self.photos_note)
        return page

    def _done_page(self) -> QWidget:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        self.done_title = QLabel("Importing…")
        self.done_title.setObjectName("EmptyStateTitle")
        v.addWidget(self.done_title)
        self.done_text = QLabel()
        self.done_text.setWordWrap(True)
        self.done_text.setProperty("role", "muted")
        v.addWidget(self.done_text)
        self.photo_progress = QProgressBar()
        self.photo_progress.setTextVisible(False)
        self.photo_progress.setFixedHeight(8)
        self.photo_progress.hide()
        v.addWidget(self.photo_progress)
        self.photo_text = QLabel()
        self.photo_text.setWordWrap(True)
        self.photo_text.setProperty("role", "muted")
        v.addWidget(self.photo_text)
        row = QHBoxLayout()
        self.stop_btn = button("Stop downloading", "secondary", None, None, self._cancel.set)
        self.stop_btn.hide()
        self.view_btn = button(
            "Show imported sightings", "secondary", "list", self.theme, self._view
        )
        self.undo_btn = button("Undo import", "ghost", None, None, self._undo)
        for b in (self.stop_btn, self.view_btn, self.undo_btn):
            row.addWidget(b)
        row.addStretch(1)
        v.addLayout(row)
        v.addStretch(1)
        return page

    def _show(self, index: int) -> None:
        self.pages.setCurrentIndex(index)
        self.back_btn.setVisible(index == 1)
        self.go_btn.setVisible(index == 1)
        self.close_btn.setText("Close" if index == 2 else "Cancel")
        if index == 1:
            self._update_go()

    # ---- step 1: read the file ----------------------------------------------------------
    def _pick_file(self) -> None:
        start = str(Path.home() / "Downloads")
        path, _ = QFileDialog.getOpenFileName(
            self, "Choose your iNaturalist export", start, "iNaturalist export (*.csv *.zip)"
        )
        if path:
            self.open_file(Path(path))

    def open_file(self, path: Path) -> None:
        """Read `path` in the background, then show what importing it would do."""
        self.choose_btn.setEnabled(False)
        self.choose_status.setProperty("role", "muted")
        self.choose_status.setText(f"Reading {path.name}…")
        self._busy = True

        def done(plan: ImportPlan) -> None:
            if not shiboken6.isValid(self):
                return
            self._busy = False
            self.choose_btn.setEnabled(True)
            self.choose_status.setText("")
            self._fill_check(plan)
            self._show(1)

        def failed(exc: BaseException) -> None:
            if not shiboken6.isValid(self):
                return
            self._busy = False
            self.choose_btn.setEnabled(True)
            self.choose_status.setProperty("role", "error")
            self.choose_status.setText(
                exc.user_message if isinstance(exc, WildlifeError) else "The file couldn't be read."
            )
            self.choose_status.style().polish(self.choose_status)

        run_in_background(lambda: self.ctx.inaturalist.preview(path), done, failed)

    # ---- step 2: check -------------------------------------------------------------------
    def _fill_check(self, plan: ImportPlan) -> None:
        self.plan, self.choices = plan, {}
        while self.check_body.count():
            item = self.check_body.takeAt(0)
            if item.widget():
                item.widget().hide()
                item.widget().deleteLater()
        self.check_title.setText(f"Check before importing: {plan.file_name}")
        parts = [f"<b>{plan.count(ADD):,}</b> new"]
        if plan.count(UPDATE):
            parts.append(f"<b>{plan.count(UPDATE):,}</b> changed on iNaturalist since last time")
        if plan.count(SAME):
            parts.append(f"{plan.count(SAME):,} already in WildLife")
        if plan.count(SKIP):
            parts.append(f"{plan.count(SKIP):,} can't be imported")
        self.summary.setText(" · ".join(parts))

        unmatched = plan.unmatched
        if unmatched:
            self.check_body.addWidget(
                Callout(
                    self.theme,
                    "info",
                    f"{plural(len(unmatched), 'name')} {'isn' if len(unmatched) == 1 else 'aren'}'t "
                    "in the UK species list as written. Choose the species (or a broader group) for "
                    "each, and WildLife will remember it next time. Anything left empty isn't imported.",
                )
            )
            grid_box = QWidget()
            grid = QGridLayout(grid_box)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(8)
            for row, (name, rows) in enumerate(unmatched.items()):
                common = rows[0].record.common_name
                label = QLabel(
                    f"<b>{name}</b><br><span>{plural(len(rows), 'record')}"
                    f"{' · ' + common if common and common != name else ''}</span>"
                )
                label.setTextFormat(Qt.TextFormat.RichText)
                label.setWordWrap(True)
                picker = SpeciesPicker(self.ctx.catalogue, self.theme)
                picker.edit.setPlaceholderText("Choose a species…")
                picker.chosen.connect(lambda taxon, n=name: self._choose(n, taxon))
                grid.addWidget(label, row, 0, Qt.AlignmentFlag.AlignTop)
                grid.addWidget(picker, row, 1)
            grid.setColumnStretch(1, 1)
            self.check_body.addWidget(grid_box)

        if plan.skipped:
            toggle = button(
                f"Show the {plural(len(plan.skipped), 'row')} that can't be imported", "link"
            )
            listing = QListWidget()
            listing.setMinimumHeight(120)
            for r in plan.skipped:
                listing.addItem(f"Line {r.record.line} · {r.record.name}: {r.reason}")
            listing.hide()
            toggle.clicked.connect(lambda: listing.setVisible(not listing.isVisible()))
            self.check_body.addWidget(toggle, 0, Qt.AlignmentFlag.AlignLeft)
            self.check_body.addWidget(listing)
        self.check_body.addStretch(1)

        online = self.ctx.settings.current.allow_online
        self.photos_box.setEnabled(online)
        self.photos_box.setChecked(online)
        self.photos_note.setText(
            "Downloads each observation's photos (original size, usually 1–3 MB each) into your "
            "photo library, in the background. Photos already here aren't downloaded again."
            if online
            else "Photos need the internet: turn on “Allow online features” in Settings to download them."
        )

    def _choose(self, name: str, taxon) -> None:
        if taxon is None:
            self.choices.pop(name, None)
        else:
            self.choices[name] = taxon.id
        self._update_go()

    def to_import(self) -> int:
        """Sightings that pressing Import would add or update."""
        if self.plan is None:
            return 0
        return sum(
            1
            for r in self.plan.rows
            if r.action in (ADD, UPDATE) and (r.taxon_id or r.record.name in self.choices)
        )

    def _update_go(self) -> None:
        n = self.to_import()
        self.go_btn.setText(f"Import {plural(n, 'sighting')}" if n else "Nothing to import")
        self.go_btn.setEnabled(n > 0 and not self._busy)

    def _back(self) -> None:
        self._show(0)

    # ---- step 3: import ------------------------------------------------------------------
    def _import(self) -> None:
        if self.plan is None or self._busy:
            return
        self._busy = True
        fetch_photos = self.photos_box.isChecked() and self.photos_box.isEnabled()
        self.done_title.setText("Importing…")
        self.done_text.setText("")
        self.view_btn.hide()
        self.undo_btn.hide()
        self._show(2)
        self.close_btn.setEnabled(False)
        plan, choices = self.plan, dict(self.choices)

        def done(result: ImportResult) -> None:
            if not shiboken6.isValid(self):
                return
            self.result = result
            self._busy = False
            self.close_btn.setEnabled(True)
            self.done_title.setText("Imported")
            self.done_text.setText(f"{result.describe()}. They're in your sightings now.")
            self.view_btn.setVisible(bool(result.added or result.updated))
            self.undo_btn.setVisible(bool(result.added or result.updated))
            self.imported.emit(result)
            if fetch_photos and (result.added or result.updated):
                self._fetch_photos(result)

        def failed(exc: BaseException) -> None:
            if not shiboken6.isValid(self):
                return
            self._busy = False
            self.close_btn.setEnabled(True)
            self.done_title.setText("Nothing was imported")
            self.done_text.setText(
                exc.user_message
                if isinstance(exc, WildlifeError)
                else "Something went wrong, so no changes were made. Details are in the log."
            )

        run_in_background(lambda: self.ctx.inaturalist.run(plan, choices), done, failed)

    def _fetch_photos(self, result: ImportResult) -> None:
        self._busy = True
        self._cancel.clear()
        self.undo_btn.setEnabled(False)  # not while photos are arriving
        self.photo_progress.show()
        self.photo_progress.setRange(0, 0)
        self.photo_text.setText("Finding the photos on iNaturalist…")
        self.stop_btn.show()

        def progress(step: str, fraction: float) -> None:
            if not shiboken6.isValid(self):
                return
            self.photo_progress.setRange(0, 100)
            self.photo_progress.setValue(int(fraction * 100))
            self.photo_text.setText(f"Downloading photos: {step}")

        def work(report):
            return self.ctx.inaturalist.fetch_photos(
                result,
                lambda done, total: report(f"{done:,} of {total:,}", done / total if total else 1),
                self._cancel.is_set,
            )

        def finished(outcome) -> None:
            if not shiboken6.isValid(self):
                return
            self._busy = False
            self.stop_btn.hide()
            self.photo_progress.hide()
            self.undo_btn.setEnabled(True)
            text = outcome.describe()
            if outcome.cancelled:
                text += ". Stopped: the rest can be fetched by importing the same file again."
            elif outcome.failed:
                text += ". Try again later by importing the same file again."
            self.photo_text.setText(f"Photos: {text}")

        def failed(exc: BaseException) -> None:
            if not shiboken6.isValid(self):
                return
            self._busy = False
            self.stop_btn.hide()
            self.photo_progress.hide()
            self.undo_btn.setEnabled(True)
            self.photo_text.setText(
                exc.user_message
                if isinstance(exc, WildlifeError)
                else "Photos couldn't be downloaded."
            )

        run_in_background(work, finished, failed, progress)

    def _view(self) -> None:
        if self.result:
            self.show_sightings.emit(SightingFilter(import_batch_id=self.result.batch_id))
            self.accept()

    def _undo(self) -> None:
        if self.result and self.result.undo and not self._busy:
            self.result.undo.run()
            self.done_title.setText("Import undone")
            self.done_text.setText("The imported sightings were removed.")
            self.view_btn.hide()
            self.undo_btn.hide()
            self.photo_text.setText("")
            self.result = None

    def reject(self) -> None:
        self._cancel.set()  # photos stop after the current one; what arrived is kept
        super().reject()
