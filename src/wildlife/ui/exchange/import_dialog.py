"""The import window: choose a file → (match columns) → check what will happen → import.

One window for every kind of import:
* iNaturalist exports (with optional photo download),
* any spreadsheet saved as CSV (with a step to say which column is which),
* WildLife's own export (.zip with photos, or .json).

Nothing changes until "Import" is pressed, and the whole import can be undone in one
go. Reading, importing and downloading all run in the background.
"""

from __future__ import annotations

import html
import threading
from dataclasses import dataclass
from pathlib import Path

import shiboken6
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
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
from wildlife.domain.csv_import import FIELDS, Table, describe_date_columns, guess_mapping
from wildlife.domain.errors import WildlifeError
from wildlife.domain.filters import SightingFilter
from wildlife.domain.regions import region
from wildlife.services.importer import ADD, SAME, SKIP, UPDATE, ImportPlan
from wildlife.services.wildlife_import import WildlifePlan
from wildlife.ui.components.common import Callout, Segmented, button, clear_layout
from wildlife.ui.components.species_picker import SpeciesPicker
from wildlife.ui.components.visuals import plural
from wildlife.ui.theme.manager import ThemeManager
from wildlife.ui.workers import run_in_background

CHOOSE, MAP, CHECK, DONE = range(4)


@dataclass(frozen=True, slots=True)
class Kind:
    key: str
    window_title: str
    heading: str
    intro: str
    how_to: str
    file_filter: str
    file_label: str


KINDS = {
    k.key: k
    for k in (
        Kind(
            "inaturalist",
            "Import from iNaturalist",
            "Bring in your iNaturalist observations",
            "Your observations become WildLife sightings, matched to your species list. "
            "Research-grade IDs are marked <b>certain</b>; the rest <b>probable</b>. "
            "Importing the same export again later only adds what's new or changed.",
            "1. On <b>inaturalist.org</b>, open <b>Your observations › Export</b>.<br>"
            "2. Leave the filters as they are to export everything, then press "
            "<b>Create export</b>.<br>"
            "3. When it's ready, download it. WildLife opens the <b>.zip</b> as it comes, "
            "or the <b>.csv</b> inside it.",
            "iNaturalist export (*.csv *.zip)",
            "Choose export file…",
        ),
        Kind(
            "csv",
            "Import a spreadsheet",
            "Bring in sightings from a spreadsheet",
            "Any table of sightings saved as CSV: from Excel, Google Sheets, another app, or "
            "a WildLife or Darwin Core export. Before anything is imported, you'll check which "
            "column is which, and see what will happen to every row.",
            "In Excel, choose <b>File › Save As › CSV UTF-8</b>. Each row should be one sighting "
            "with at least a species and a date. Next, you can say how its dates are written "
            "(day/month or month/day).",
            "Spreadsheet (*.csv *.txt)",
            "Choose spreadsheet…",
        ),
        Kind(
            "wildlife",
            "Import a WildLife export",
            "Bring back a WildLife export",
            "An export from WildLife on this PC or another: the <b>.zip</b> with photos, or "
            "the <b>.json</b>. Places, outings and photos come with the sightings. Anything "
            "already here is left as it is, so importing the same export twice is safe.",
            "",
            "WildLife export (*.zip *.json)",
            "Choose export…",
        ),
    )
}


class ImportDialog(QDialog):
    imported = Signal(object)  # the result, for the main window's "Undo" toast
    show_sightings = Signal(object)  # SightingFilter

    def __init__(
        self, ctx: AppContext, theme: ThemeManager, kind: str, parent: QWidget | None = None
    ) -> None:
        super().__init__(parent)
        self.ctx, self.theme, self.kind = ctx, theme, KINDS[kind]
        self.table: Table | None = None
        self.plan: ImportPlan | WildlifePlan | None = None
        self.outcome = None
        self.choices: dict[str, int] = {}
        self.combos: dict[str, QComboBox] = {}
        self._cancel = threading.Event()
        self._busy = False
        self.setWindowTitle(self.kind.window_title)
        self.setMinimumSize(580, 500)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 18)
        v.setSpacing(14)
        self.pages = QStackedWidget()
        v.addWidget(self.pages, 1)
        foot = QHBoxLayout()
        foot.addStretch(1)
        self.back_btn = button("Back", "secondary", None, None, self._back)
        self.close_btn = button("Cancel", "secondary", None, None, self.reject)
        self.go_btn = button("Import", "primary", None, None, self._go)
        for b in (self.back_btn, self.close_btn, self.go_btn):
            foot.addWidget(b)
        v.addLayout(foot)
        for build in (self._choose_page, self._map_page, self._check_page, self._done_page):
            self.pages.addWidget(build())
        self._show(CHOOSE)

    # ---- page building ------------------------------------------------------------------
    @staticmethod
    def _page() -> tuple[QWidget, QVBoxLayout]:
        page = QWidget()
        v = QVBoxLayout(page)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(10)
        return page, v

    @staticmethod
    def _title(text: str = "") -> QLabel:
        label = QLabel(text)
        label.setObjectName("EmptyStateTitle")
        label.setWordWrap(True)
        return label

    @staticmethod
    def _text(text: str = "", role: str | None = "muted") -> QLabel:
        label = QLabel(text)
        label.setWordWrap(True)
        label.setTextFormat(Qt.TextFormat.RichText)
        if role:
            label.setProperty("role", role)
        return label

    @staticmethod
    def _scroll() -> tuple[QScrollArea, QVBoxLayout]:
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        body = QWidget()
        layout = QVBoxLayout(body)
        layout.setContentsMargins(0, 0, 8, 0)
        layout.setSpacing(10)
        scroll.setWidget(body)
        return scroll, layout

    def _choose_page(self) -> QWidget:
        page, v = self._page()
        v.addWidget(self._title(self.kind.heading))
        v.addWidget(self._text(self.kind.intro))
        if self.kind.how_to:
            v.addWidget(self._text(self.kind.how_to, None))
        row = QHBoxLayout()
        self.choose_btn = button(self.kind.file_label, "primary", "upload", self.theme, self._pick)
        row.addWidget(self.choose_btn)
        row.addStretch(1)
        v.addLayout(row)
        self.choose_status = QLabel()
        self.choose_status.setWordWrap(True)
        v.addWidget(self.choose_status)
        v.addStretch(1)
        return page

    def _map_page(self) -> QWidget:
        page, v = self._page()
        self.map_title = self._title()
        v.addWidget(self.map_title)
        v.addWidget(
            self._text(
                "WildLife has guessed which column holds what. Check each one, and change it "
                "if needed. You need a <b>date</b>, and a <b>species</b> (English or "
                "scientific name)."
            )
        )
        # How numeric dates are written: the region's way to start with (US month/day)
        order = QHBoxLayout()
        order.addWidget(self._text("Dates like 3/5/2026 are", role=None))
        month_first = region(self.ctx.catalogue.region()).month_first
        self.date_order = Segmented(
            [("dmy", "day/month (3 May)"), ("mdy", "month/day (March 5)")],
            "mdy" if month_first else "dmy",
        )
        self.date_order.setAccessibleName("Date order")
        self.date_order.changed.connect(lambda _key: self._update_map())
        order.addWidget(self.date_order)
        order.addStretch(1)
        v.addLayout(order)
        self.map_warning = Callout(self.theme, "alert", "", tone="warning")
        self.map_warning.hide()
        v.addWidget(self.map_warning)
        scroll, self.map_body = self._scroll()
        v.addWidget(scroll, 1)
        return page

    def _check_page(self) -> QWidget:
        page, v = self._page()
        self.check_title = self._title()
        v.addWidget(self.check_title)
        self.summary = self._text(role=None)
        v.addWidget(self.summary)
        scroll, self.check_body = self._scroll()
        v.addWidget(scroll, 1)
        self.photos_box = QCheckBox("Also download the photos from iNaturalist")
        v.addWidget(self.photos_box)
        self.photos_note = self._text(role="caption")
        v.addWidget(self.photos_note)
        return page

    def _done_page(self) -> QWidget:
        page, v = self._page()
        self.done_title = self._title("Importing…")
        v.addWidget(self.done_title)
        self.done_text = self._text()
        v.addWidget(self.done_text)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.hide()
        v.addWidget(self.progress)
        self.progress_text = self._text()
        v.addWidget(self.progress_text)
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
        self.back_btn.setVisible(index in (MAP, CHECK))
        self.go_btn.setVisible(index in (MAP, CHECK))
        self.close_btn.setText("Close" if index == DONE else "Cancel")
        if index == MAP:
            self.go_btn.setText("Check")
            self._update_map()
        elif index == CHECK:
            self._update_go()

    def _back(self) -> None:
        self._show(MAP if self.pages.currentIndex() == CHECK and self.table else CHOOSE)

    def _go(self) -> None:
        if self.pages.currentIndex() == MAP:
            self._preview_table()
        else:
            self._import()

    def _error(self, label: QLabel, exc: BaseException, fallback: str) -> None:
        label.setProperty("role", "error")
        label.setText(exc.user_message if isinstance(exc, WildlifeError) else fallback)
        label.style().polish(label)

    # ---- step 1: read the file ----------------------------------------------------------
    def _pick(self) -> None:
        start = str(Path.home() / "Downloads")
        path, _ = QFileDialog.getOpenFileName(
            self, self.kind.window_title, start, self.kind.file_filter
        )
        if path:
            self.open_file(Path(path))

    def open_file(self, path: Path) -> None:
        """Read `path` in the background, then go on to the next step."""
        self.choose_btn.setEnabled(False)
        self.choose_status.setProperty("role", "muted")
        self.choose_status.setText(f"Reading {path.name}…")
        self._busy = True
        reader = {
            "inaturalist": lambda: self.ctx.inaturalist.preview(path),
            "csv": lambda: self.ctx.spreadsheet.read(path),
            "wildlife": lambda: self.ctx.wildlife_import.preview(path),
        }[self.kind.key]

        def done(found) -> None:
            if not shiboken6.isValid(self):
                return
            self._busy = False
            self.choose_btn.setEnabled(True)
            self.choose_status.setText("")
            if isinstance(found, Table):
                self._fill_map(found)
                self._show(MAP)
            else:
                self._fill_check(found)
                self._show(CHECK)

        def failed(exc: BaseException) -> None:
            if not shiboken6.isValid(self):
                return
            self._busy = False
            self.choose_btn.setEnabled(True)
            self._error(self.choose_status, exc, "The file couldn't be read.")

        run_in_background(reader, done, failed)

    # ---- step 2 (spreadsheets): which column is which -------------------------------------
    def _fill_map(self, table: Table) -> None:
        self.table, self.combos = table, {}
        clear_layout(self.map_body)
        self.map_title.setText(f"Match the columns: {table.name}")
        guess = guess_mapping(table.header)
        grid_box = QWidget()
        grid = QGridLayout(grid_box)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(12)
        grid.setVerticalSpacing(6)
        for row, field in enumerate(FIELDS):
            label = QLabel(field.label)
            combo = QComboBox()
            combo.addItem("— not in the file —", None)
            for i, heading in enumerate(table.header):
                samples = ", ".join(table.samples(i))
                combo.addItem(
                    f"{heading or f'Column {i + 1}'}" + (f"  ·  e.g. {samples}" if samples else ""),
                    i,
                )
            if field.key in guess:
                combo.setCurrentIndex(guess[field.key] + 1)
            combo.currentIndexChanged.connect(lambda _: self._update_map())
            self.combos[field.key] = combo
            grid.addWidget(label, row, 0)
            grid.addWidget(combo, row, 1)
        grid.setColumnStretch(1, 1)
        self.map_body.addWidget(grid_box)
        self.map_body.addStretch(1)

    def mapping(self) -> dict[str, int]:
        return {k: c.currentData() for k, c in self.combos.items() if c.currentData() is not None}

    def _update_map(self) -> None:
        if self.table is None:
            return
        mapping = self.mapping()
        ready = "date" in mapping and bool({"species", "scientific", "uksi_key"} & set(mapping))
        warning = describe_date_columns(self.table, mapping, self.month_first())
        self.map_warning.setVisible(bool(warning))
        if warning:
            self.map_warning.set_text(warning)
        self.go_btn.setEnabled(ready and not self._busy)

    def month_first(self) -> bool:
        return self.date_order.current() == "mdy"

    def _preview_table(self) -> None:
        table, mapping, month_first = self.table, self.mapping(), self.month_first()
        self._busy = True
        self.go_btn.setEnabled(False)

        def done(plan: ImportPlan) -> None:
            if not shiboken6.isValid(self):
                return
            self._busy = False
            self._fill_check(plan)
            self._show(CHECK)

        def failed(exc: BaseException) -> None:
            if not shiboken6.isValid(self):
                return
            self._busy = False
            self.map_warning.show()
            self.map_warning.set_text(
                exc.user_message if isinstance(exc, WildlifeError) else "The rows couldn't be read."
            )
            self._update_map()

        run_in_background(
            lambda: self.ctx.spreadsheet.preview(table, mapping, month_first=month_first),
            done,
            failed,
        )

    # ---- step 3: check -------------------------------------------------------------------
    def _fill_check(self, plan) -> None:
        self.plan, self.choices = plan, {}
        clear_layout(self.check_body)
        self.check_title.setText(f"Check before importing: {plan.file_name}")
        online = self.ctx.settings.current.allow_online
        self.photos_box.setVisible(self.kind.key == "inaturalist")
        self.photos_note.setVisible(self.kind.key == "inaturalist")
        if isinstance(plan, WildlifePlan):
            self._fill_wildlife_check(plan)
        else:
            self._fill_record_check(plan)
        self.check_body.addStretch(1)
        self.photos_box.setEnabled(online)
        self.photos_box.setChecked(online)
        self.photos_note.setText(
            "Downloads each observation's photos (original size, usually 1–3 MB each) into your "
            "photo library, in the background. Photos already here aren't downloaded again."
            if online
            else "Photos need the internet: turn on “Allow online features” in Settings to "
            "download them."
        )

    def _fill_wildlife_check(self, plan: WildlifePlan) -> None:
        self.summary.setText(plan.describe())
        if plan.new_species:
            names = ", ".join(plan.new_species[:12]) + ("…" if len(plan.new_species) > 12 else "")
            self.check_body.addWidget(
                Callout(
                    self.theme,
                    "info",
                    f"{plural(len(plan.new_species), 'species')} {'isn' if len(plan.new_species) == 1 else 'aren'}'t "
                    f"in this library's species list, so {'it' if len(plan.new_species) == 1 else 'they'} "
                    f"will be added as your own: {names}.",
                )
            )
        if plan.photos_missing:
            self.check_body.addWidget(
                Callout(
                    self.theme,
                    "alert",
                    f"{plural(plan.photos_missing, 'photo')} {'isn' if plan.photos_missing == 1 else 'aren'}'t in this "
                    "file. To bring photos too, import the .zip export instead of the .json.",
                    tone="warning",
                )
            )

    def _fill_record_check(self, plan: ImportPlan) -> None:
        changed_where = "on iNaturalist" if self.kind.key == "inaturalist" else "in the file"
        parts = [f"<b>{plan.count(ADD):,}</b> new"]
        if plan.count(UPDATE):
            parts.append(f"<b>{plan.count(UPDATE):,}</b> changed {changed_where} since last time")
        if plan.count(SAME):
            parts.append(f"{plan.count(SAME):,} already in WildLife")
        if plan.count(SKIP):
            parts.append(f"{plan.count(SKIP):,} can't be imported")
        self.summary.setText(" · ".join(parts))
        unmatched = plan.unmatched
        if unmatched:
            n = len(unmatched)
            self.check_body.addWidget(
                Callout(
                    self.theme,
                    "info",
                    f"{plural(n, 'name')} {'isn' if n == 1 else 'aren'}'t in your species list "
                    "as written. Choose the species (or a broader group) for each, and WildLife "
                    "will remember it next time. Anything left empty isn't imported.",
                )
            )
            grid_box = QWidget()
            grid = QGridLayout(grid_box)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setHorizontalSpacing(12)
            grid.setVerticalSpacing(8)
            for row, (name, rows) in enumerate(unmatched.items()):
                common = rows[0].record.common_name
                also = f" · {html.escape(common)}" if common and common != name else ""
                label = QLabel(  # names come from the file: shown as text, never markup
                    f"<b>{html.escape(name)}</b><br><span>{plural(len(rows), 'record')}{also}</span>"
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
        left_out = [r for r in plan.rows if r.action in (SKIP, SAME) and r.reason]
        if left_out:
            toggle = button(f"Show the {plural(len(left_out), 'row')} left out, and why", "link")
            listing = QListWidget()
            listing.setMinimumHeight(140)
            for r in left_out:
                listing.addItem(f"Line {r.record.line} · {r.record.name}: {r.reason}")
            listing.hide()
            save = button(
                "Save this list…", "link", None, None, lambda: self._save_report(left_out)
            )
            save.hide()

            def show_or_hide() -> None:
                listing.setVisible(not listing.isVisible())
                save.setVisible(listing.isVisible())

            toggle.clicked.connect(show_or_hide)
            self.check_body.addWidget(toggle, 0, Qt.AlignmentFlag.AlignLeft)
            self.check_body.addWidget(listing)
            self.check_body.addWidget(save, 0, Qt.AlignmentFlag.AlignLeft)

    def _save_report(self, rows) -> None:
        start = str(Path.home() / "Documents" / f"{Path(self.plan.file_name).stem} - left out.txt")
        path, _ = QFileDialog.getSaveFileName(self, "Save the list", start, "Text (*.txt)")
        if path:
            self.write_report(Path(path), rows)

    def write_report(self, path: Path, rows) -> None:
        """The rows left out of an import, and why, as a text file (one per line)."""
        lines = [f"Rows left out of {self.plan.file_name}", ""]
        lines += [f"Line {r.record.line}: {r.record.name}: {r.reason}" for r in rows]
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _choose(self, name: str, taxon) -> None:
        if taxon is None:
            self.choices.pop(name, None)
        else:
            self.choices[name] = taxon.id
        self._update_go()

    def to_import(self) -> int:
        """Sightings that pressing Import would add or update."""
        if isinstance(self.plan, WildlifePlan):
            return self.plan.new_sightings
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

    # ---- step 4: import ------------------------------------------------------------------
    def _import(self) -> None:
        if self.plan is None or self._busy:
            return
        self._busy = True
        fetch_photos = (
            self.kind.key == "inaturalist"
            and self.photos_box.isChecked()
            and self.photos_box.isEnabled()
        )
        self.done_title.setText("Importing…")
        self.done_text.setText("")
        self.view_btn.hide()
        self.undo_btn.hide()
        self._show(DONE)
        self.close_btn.setEnabled(False)
        plan, choices = self.plan, dict(self.choices)
        if isinstance(plan, WildlifePlan):
            self.progress.show()
            self.progress.setRange(0, 0)

            def work(report):
                return self.ctx.wildlife_import.run(
                    plan, lambda d, t: report(f"Photos: {d:,} of {t:,}", d / t if t else 1)
                )

            progress = self._on_progress
        else:
            service = (
                self.ctx.inaturalist if self.kind.key == "inaturalist" else self.ctx.spreadsheet
            )

            def work():
                return service.run(plan, choices)

            progress = None

        def done(result) -> None:
            if not shiboken6.isValid(self):
                return
            self.outcome = result
            self._busy = False
            self.progress.hide()
            self.progress_text.setText("")
            self.close_btn.setEnabled(True)
            self.done_title.setText("Imported")
            self.done_text.setText(f"{result.describe()}.")
            changed = bool(result.added or getattr(result, "updated", None))
            self.view_btn.setVisible(changed)
            self.undo_btn.setVisible(changed)
            self.imported.emit(result)
            if fetch_photos and changed:
                self._fetch_photos(result)

        def failed(exc: BaseException) -> None:
            if not shiboken6.isValid(self):
                return
            self._busy = False
            self.progress.hide()
            self.close_btn.setEnabled(True)
            self.done_title.setText("Nothing was imported")
            self.done_text.setText(
                exc.user_message
                if isinstance(exc, WildlifeError)
                else "Something went wrong, so no changes were made. Details are in the log."
            )

        run_in_background(work, done, failed, progress)

    def _on_progress(self, step: str, fraction: float) -> None:
        if not shiboken6.isValid(self):
            return
        self.progress.setRange(0, 100)
        self.progress.setValue(int(fraction * 100))
        self.progress_text.setText(step)

    def _fetch_photos(self, result) -> None:
        self._busy = True
        self._cancel.clear()
        self.undo_btn.setEnabled(False)  # not while photos are arriving
        self.progress.show()
        self.progress.setRange(0, 0)
        self.progress_text.setText("Finding the photos on iNaturalist…")
        self.stop_btn.show()

        def work(report):
            return self.ctx.inaturalist.fetch_photos(
                result,
                lambda d, t: report(f"Downloading photos: {d:,} of {t:,}", d / t if t else 1),
                self._cancel.is_set,
            )

        def finished(outcome) -> None:
            if not shiboken6.isValid(self):
                return
            self._busy = False
            self.stop_btn.hide()
            self.progress.hide()
            self.undo_btn.setEnabled(True)
            text = outcome.describe()
            if outcome.cancelled:
                text += ". Stopped: the rest can be fetched by importing the same file again."
            elif outcome.failed:
                text += ". Try again later by importing the same file again."
            self.progress_text.setText(f"Photos: {text}")

        def failed(exc: BaseException) -> None:
            if not shiboken6.isValid(self):
                return
            self._busy = False
            self.stop_btn.hide()
            self.progress.hide()
            self.undo_btn.setEnabled(True)
            self.progress_text.setText(
                exc.user_message
                if isinstance(exc, WildlifeError)
                else "Photos couldn't be downloaded."
            )

        run_in_background(work, finished, failed, self._on_progress)

    def _view(self) -> None:
        if self.outcome:
            self.show_sightings.emit(SightingFilter(import_batch_id=self.outcome.batch_id))
            self.accept()

    def _undo(self) -> None:
        if self.outcome and self.outcome.undo and not self._busy:
            self.outcome.undo.run()
            self.done_title.setText("Import undone")
            self.done_text.setText("The imported sightings were removed.")
            self.view_btn.hide()
            self.undo_btn.hide()
            self.progress_text.setText("")
            self.outcome = None

    def reject(self) -> None:
        self._cancel.set()  # photos stop after the current one; what arrived is kept
        super().reject()
