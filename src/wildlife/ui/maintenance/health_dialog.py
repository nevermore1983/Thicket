"""The health check window: runs the check in the background and lists what it found,
with a button for each fix Thicket can make."""

from __future__ import annotations

from pathlib import Path

import shiboken6
from PySide6.QtCore import Qt, QUrl, Signal
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.services.health import OK, PROBLEM, Finding, HealthReport
from wildlife.ui.components.common import button, clear_layout
from wildlife.ui.theme.icons import pixmap
from wildlife.ui.theme.manager import ThemeManager
from wildlife.ui.workers import run_in_background

ICONS = {OK: "check", "warning": "alert", PROBLEM: "alert"}


class HealthDialog(QDialog):
    """Signals ask the main window for fixes that live elsewhere."""

    backup_requested = Signal()
    restore_requested = Signal()
    choose_backup_folder = Signal()

    def __init__(self, ctx: AppContext, theme: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx, self.theme = ctx, theme
        self.report: HealthReport | None = None
        self.setWindowTitle("Health check")
        self.setMinimumSize(560, 480)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 18)
        v.setSpacing(12)
        self.title = QLabel("Checking…")
        self.title.setObjectName("EmptyStateTitle")
        v.addWidget(self.title)
        self.progress = QProgressBar()
        self.progress.setTextVisible(False)
        self.progress.setFixedHeight(8)
        v.addWidget(self.progress)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setStyleSheet(
            "QScrollArea, QScrollArea > QWidget > QWidget { background: transparent; }"
        )
        body = QWidget()
        self.body = QVBoxLayout(body)
        self.body.setContentsMargins(0, 0, 8, 0)
        self.body.setSpacing(4)
        scroll.setWidget(body)
        v.addWidget(scroll, 1)
        foot = QHBoxLayout()
        self.again_btn = button("Check again", "secondary", "rotate", theme, self.run)
        foot.addWidget(self.again_btn)
        foot.addStretch(1)
        foot.addWidget(button("Close", "secondary", None, None, self.reject))
        v.addLayout(foot)
        self.run()

    def run(self) -> None:
        self.again_btn.setEnabled(False)
        self.progress.show()
        self.progress.setRange(0, 0)
        self.title.setText("Checking…")

        def progress(_step: str, fraction: float) -> None:
            if shiboken6.isValid(self):
                self.progress.setRange(0, 100)
                self.progress.setValue(int(fraction * 100))

        def done(report: HealthReport) -> None:
            if shiboken6.isValid(self):
                self.show_report(report)

        def failed(_exc: BaseException) -> None:
            if shiboken6.isValid(self):
                self.progress.hide()
                self.again_btn.setEnabled(True)
                self.title.setText("The check couldn't finish. Details are in the log.")

        run_in_background(
            lambda report: self.ctx.health.check(lambda d, t: report("", d / t if t else 1)),
            done,
            failed,
            progress,
        )

    def show_report(self, report: HealthReport) -> None:
        self.report = report
        self.progress.hide()
        self.again_btn.setEnabled(True)
        self.title.setText(
            {
                OK: "Everything looks healthy",
                "warning": "Mostly healthy, with a few things to look at",
                PROBLEM: "Some things need attention",
            }[report.worst]
        )
        clear_layout(self.body)
        order = {PROBLEM: 0, "warning": 1, OK: 2}
        for finding in sorted(report.findings, key=lambda f: order[f.level]):
            self.body.addWidget(self._row(finding))
        self.body.addStretch(1)

    def _row(self, f: Finding) -> QWidget:
        t = self.theme.tokens
        row = QFrame()
        row.setObjectName("SettingsRow")
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 10, 0, 10)
        mark = QLabel()
        colour = {OK: t.good_text, "warning": t.warning, PROBLEM: t.danger}[f.level]
        mark.setPixmap(pixmap(ICONS[f.level], colour, 18))
        mark.setAlignment(Qt.AlignmentFlag.AlignTop)
        h.addWidget(mark)
        text = QVBoxLayout()
        text.setSpacing(2)
        title = QLabel(f.title)
        title.setProperty("role", "rowTitle")
        title.setWordWrap(True)
        text.addWidget(title)
        if f.detail:
            detail = QLabel(f.detail)
            detail.setProperty("role", "muted")
            detail.setWordWrap(True)
            text.addWidget(detail)
        if f.items:
            items = QLabel("\n".join(f.items[:5]) + ("\n…" if len(f.items) > 5 else ""))
            items.setProperty("role", "caption")
            items.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            text.addWidget(items)
        h.addLayout(text, 1)
        if f.action:
            h.addWidget(
                button(f.action_label, "secondary", None, None, lambda: self._fix(f.action)),
                0,
                Qt.AlignmentFlag.AlignTop,
            )
        return row

    def _fix(self, action: str) -> None:
        health = self.ctx.health
        if action == "restore_photos":
            self._run_fix(health.bring_back_photos, "photo files brought back")
        elif action == "find_photos":
            folder = QFileDialog.getExistingDirectory(self, "Where might the photos be?")
            if folder:
                self._run_fix(
                    lambda: self.ctx.photos.find_in_folder(Path(folder)), "photo files found"
                )
        elif action == "remove_partial":
            self._run_fix(health.remove_partial, "unfinished copies removed")
        elif action == "clear_thumbnails":
            self._run_fix(health.clear_thumbnails, "thumbnails cleared")
        elif action == "open_photos_folder":
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.ctx.paths.photos)))
        elif action == "backup_now":
            self.backup_requested.emit()
        elif action == "restore":
            self.restore_requested.emit()
        elif action == "choose_backup_folder":
            self.choose_backup_folder.emit()

    def _run_fix(self, fix, what: str) -> None:
        self.again_btn.setEnabled(False)

        def done(n: int) -> None:
            if shiboken6.isValid(self):
                self.title.setText(f"{n:,} {what}")
                self.run()

        run_in_background(fix, done)
