"""The export window: what to export → which format → sharing options → save.

Sharing formats (spreadsheet, Darwin Core, map data) can blur locations and include
photos with where they were taken removed. The complete formats (Thicket data, or
everything with photos) are always exact, so Thicket can import them again.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import shiboken6
from PySide6.QtCore import QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QRadioButton,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.domain.errors import WildlifeError
from wildlife.domain.filters import SightingFilter
from wildlife.services.export import FORMATS, ExportOptions, ExportSummary
from wildlife.ui.components.common import Segmented, button
from wildlife.ui.theme.manager import ThemeManager
from wildlife.ui.workers import run_in_background

BLUR = (("0", "Exact"), ("1000", "1 km square"), ("10000", "10 km square"))


class ExportDialog(QDialog):
    exported = Signal(object)  # ExportSummary

    def __init__(
        self,
        ctx: AppContext,
        theme: ThemeManager,
        flt: SightingFilter | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self.ctx, self.theme = ctx, theme
        self.flt = flt if flt is not None and not flt.is_empty else None
        self.summary: ExportSummary | None = None
        self.blur_m = 0
        self.setWindowTitle("Export sightings")
        self.setMinimumWidth(560)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 18)
        v.setSpacing(12)
        heading = QLabel("Export sightings")
        heading.setObjectName("EmptyStateTitle")
        v.addWidget(heading)

        # what
        self.scope_all = QRadioButton(f"All sightings ({ctx.export.count(SightingFilter()):,})")
        self.scope_shown = QRadioButton(
            f"The sightings shown now ({ctx.export.count(self.flt):,})" if self.flt else ""
        )
        scope = QButtonGroup(self)
        for b in (self.scope_all, self.scope_shown):
            scope.addButton(b)
        if self.flt:
            v.addWidget(self._section("Which sightings"))
            v.addWidget(self.scope_shown)
            v.addWidget(self.scope_all)
            self.scope_shown.setChecked(True)
        else:
            self.scope_all.setChecked(True)

        # format
        v.addWidget(self._section("Format"))
        self.formats: dict[str, QRadioButton] = {}
        group = QButtonGroup(self)
        for fmt in FORMATS.values():
            radio = QRadioButton(fmt.label)
            radio.setToolTip(fmt.description)
            group.addButton(radio)
            self.formats[fmt.key] = radio
            v.addWidget(radio)
            hint = QLabel(fmt.description)
            hint.setWordWrap(True)
            hint.setProperty("role", "caption")
            hint.setContentsMargins(26, 0, 0, 4)
            v.addWidget(hint)
            radio.toggled.connect(self._update)

        # sharing options
        self.sharing = QWidget()
        s = QVBoxLayout(self.sharing)
        s.setContentsMargins(0, 0, 0, 0)
        s.setSpacing(8)
        s.addWidget(self._section("Sharing"))
        row = QHBoxLayout()
        row.addWidget(QLabel("Locations"))
        self.blur = Segmented(BLUR, "0")
        self.blur.changed.connect(self._set_blur)
        row.addWidget(self.blur)
        row.addStretch(1)
        s.addLayout(row)
        self.blur_note = QLabel()
        self.blur_note.setWordWrap(True)
        self.blur_note.setProperty("role", "caption")
        s.addWidget(self.blur_note)
        self.with_photos = QCheckBox("Include photos (saves a .zip)")
        self.strip_gps = QCheckBox("Remove where the photos were taken (GPS)")
        self.strip_gps.setChecked(True)
        self.with_photos.toggled.connect(self._update)
        s.addWidget(self.with_photos)
        s.addWidget(self.strip_gps)
        v.addWidget(self.sharing)

        # progress and result
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        self.progress.hide()
        v.addWidget(self.progress)
        self.status = QLabel()
        self.status.setWordWrap(True)
        v.addWidget(self.status)
        v.addStretch(1)

        foot = QHBoxLayout()
        self.open_btn = button("Show in folder", "secondary", "folder", theme, self._open_folder)
        self.open_btn.hide()
        foot.addWidget(self.open_btn)
        foot.addStretch(1)
        self.close_btn = button("Close", "secondary", None, None, self.reject)
        self.go_btn = button("Export…", "primary", "download", theme, self._export)
        foot.addWidget(self.close_btn)
        foot.addWidget(self.go_btn)
        v.addLayout(foot)
        self._set_blur("0")
        self.formats["csv"].setChecked(True)
        self._update()

    @staticmethod
    def _section(text: str) -> QLabel:
        label = QLabel(text)
        label.setProperty("role", "sectionTitle")
        return label

    def _set_blur(self, key: str) -> None:
        self.blur_m = int(key)
        self.blur_note.setText(
            "Exact positions, place names and location descriptions are included."
            if not self.blur_m
            else f"Positions become the centre of their {dict(BLUR)[key]} (with a grid "
            "reference); place names and location descriptions are left out. Your records "
            "in Thicket don't change."
        )

    def format_key(self) -> str:
        return next(k for k, r in self.formats.items() if r.isChecked())

    def options(self) -> ExportOptions:
        fmt = FORMATS[self.format_key()]
        shown = self.flt if (self.flt and self.scope_shown.isChecked()) else SightingFilter()
        return ExportOptions(
            fmt.key,
            shown,
            self.blur_m if fmt.for_sharing else 0,
            fmt.for_sharing and self.with_photos.isChecked(),
            self.strip_gps.isChecked(),
        )

    def _update(self) -> None:
        sharing = FORMATS[self.format_key()].for_sharing
        self.sharing.setEnabled(sharing)
        self.strip_gps.setEnabled(sharing and self.with_photos.isChecked())

    # ---- doing it ------------------------------------------------------------------------
    def _export(self) -> None:
        options = self.options()
        fmt = FORMATS[options.format]
        stamp = date.today().isoformat()
        name = {
            "dwc": f"Thicket Darwin Core {stamp}",
            "geojson": f"Thicket map {stamp}",
            "archive": f"Thicket export {stamp}",
            "json": f"Thicket export {stamp}",
        }.get(fmt.key, f"Thicket sightings {stamp}")
        start = Path.home() / "Documents" / (name + options.suffix)
        path, _ = QFileDialog.getSaveFileName(
            self, "Export sightings", str(start), f"{fmt.label} (*{options.suffix})"
        )
        if path:
            self.export_to(Path(path), options)

    def export_to(self, path: Path, options: ExportOptions) -> None:
        self.go_btn.setEnabled(False)
        self.open_btn.hide()
        self.progress.show()
        self.progress.setRange(0, 0)
        self.status.setProperty("role", "muted")
        self.status.setText("Exporting…")

        def progress(step: str, fraction: float) -> None:
            if shiboken6.isValid(self):
                self.progress.setRange(0, 100)
                self.progress.setValue(int(fraction * 100))
                self.status.setText(step)

        def work(report):
            return self.ctx.export.export(
                options, path, lambda d, t: report(f"Photos: {d:,} of {t:,}", d / t if t else 1)
            )

        def done(summary: ExportSummary) -> None:
            if not shiboken6.isValid(self):
                return
            self.summary = summary
            self.go_btn.setEnabled(True)
            self.progress.hide()
            self.status.setText(f"Saved {summary.path.name}: {summary.describe()}.")
            self.open_btn.show()
            self.exported.emit(summary)

        def failed(exc: BaseException) -> None:
            if not shiboken6.isValid(self):
                return
            self.go_btn.setEnabled(True)
            self.progress.hide()
            self.status.setProperty("role", "error")
            self.status.setText(
                exc.user_message
                if isinstance(exc, WildlifeError)
                else "The export couldn't be saved. Is there space, and can Thicket write there?"
            )
            self.status.style().polish(self.status)

        run_in_background(work, done, failed, progress)

    def _open_folder(self) -> None:
        if self.summary:
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.summary.path.parent)))
