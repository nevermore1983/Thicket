"""The restore window: pick a backup (from the backup folder, or any file), confirm,
and WildLife restarts to put it in place."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.data.restore import BackupInfo, describe
from wildlife.domain.errors import WildlifeError
from wildlife.ui.components.common import button
from wildlife.ui.components.visuals import fmt_date, plural
from wildlife.ui.theme.manager import ThemeManager

KINDS = {"auto": "daily", "exit": "on closing", "manual": "made by you"}


def backup_text(info: BackupInfo) -> str:
    when = info.created.astimezone()
    kind = KINDS.get(info.kind, info.kind)
    return (
        f"{fmt_date(when.date(), 'medium')} at {when:%H:%M}  ·  {kind}  ·  "
        f"{plural(info.sightings, 'sighting')}, {plural(info.photos, 'photo')}"
    )


class RestoreDialog(QDialog):
    restart_requested = Signal()  # the backup is checked and noted: restart to restore

    def __init__(self, ctx: AppContext, theme: ThemeManager, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.chosen: BackupInfo | None = None
        self.setWindowTitle("Restore a backup")
        self.setMinimumSize(560, 440)
        v = QVBoxLayout(self)
        v.setContentsMargins(24, 22, 24, 18)
        v.setSpacing(10)
        title = QLabel("Restore a backup")
        title.setObjectName("EmptyStateTitle")
        v.addWidget(title)
        note = QLabel(
            "Your data goes back to how it was when the backup was made; anything added "
            "since is replaced. Your current data is kept as a safety copy first, and photo "
            "files the library is missing are brought back from the backup. WildLife restarts "
            "to do this."
        )
        note.setWordWrap(True)
        note.setProperty("role", "muted")
        v.addWidget(note)
        self.list = QListWidget()
        self.list.setAccessibleName("Backups")
        for info in ctx.backup.backups():
            item = QListWidgetItem(backup_text(info))
            item.setData(Qt.ItemDataRole.UserRole, info)
            self.list.addItem(item)
        if self.list.count():
            self.list.setCurrentRow(0)
        else:
            self.list.addItem(f"No backups in {ctx.backup.folder()}")
            self.list.setEnabled(False)
        self.list.itemDoubleClicked.connect(lambda _: self._restore_selected())
        v.addWidget(self.list, 1)
        self.status = QLabel()
        self.status.setWordWrap(True)
        v.addWidget(self.status)
        foot = QHBoxLayout()
        foot.addWidget(button("Choose a backup file…", "secondary", "folder", theme, self._pick))
        foot.addStretch(1)
        foot.addWidget(button("Cancel", "secondary", None, None, self.reject))
        self.go_btn = button("Restore…", "primary", "rotate", theme, self._restore_selected)
        self.go_btn.setEnabled(self.list.isEnabled())
        foot.addWidget(self.go_btn)
        v.addLayout(foot)

    def _pick(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Choose a WildLife backup",
            str(self.ctx.backup.folder()),
            "WildLife backup (*.db)",
        )
        if path:
            self.restore(describe(Path(path)))

    def _restore_selected(self) -> None:
        item = self.list.currentItem()
        info = item.data(Qt.ItemDataRole.UserRole) if item else None
        if info is not None:
            self.restore(info)

    def restore(self, info: BackupInfo, confirm: bool = True) -> None:
        if confirm:
            answer = QMessageBox.question(
                self,
                "Restore this backup?",
                f"WildLife will restart and bring back your data as it was on "
                f"{backup_text(info)}.\n\nYour current data is kept as a safety copy.",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        try:
            self.chosen = self.ctx.backup.request_restore(info.path)
        except WildlifeError as exc:
            self.status.setProperty("role", "error")
            self.status.setText(exc.user_message)
            self.status.style().polish(self.status)
            return
        self.restart_requested.emit()
        self.accept()
