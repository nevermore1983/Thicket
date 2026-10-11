"""Settings page. Phase 5: appearance, data folder and about. More sections arrive later."""

from __future__ import annotations

from PySide6.QtCore import Qt, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from wildlife import __version__
from wildlife.config.settings import Theme
from wildlife.context import AppContext
from wildlife.ui.components.common import Callout, Page, Segmented, button
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


class SettingsPage(Page):
    def __init__(self, ctx: AppContext, theme: ThemeManager) -> None:
        super().__init__("Settings")
        self._ctx, self._theme = ctx, theme

        self.theme_choice = Segmented(
            [(Theme.SYSTEM, "System"), (Theme.LIGHT, "Light"), (Theme.DARK, "Dark")],
            ctx.settings.current.theme,
        )
        self.theme_choice.changed.connect(self._set_theme)
        self.add(
            _section(
                "Appearance",
                [
                    _row(
                        "Theme", "Follow Windows, or always use light or dark.", self.theme_choice
                    ),
                ],
            )
        )

        data_rows: list[QWidget] = []
        if ctx.paths.is_cloud_synced():
            data_rows.append(
                Callout(
                    theme,
                    "alert",
                    "Your data folder is inside a cloud-synced folder (such as OneDrive). Syncing a database "
                    "while WildLife is open can damage it. Keep live data on this PC and use the cloud folder "
                    "for backups instead.",
                    tone="warning",
                )
            )
        folder = QLabel(str(ctx.paths.root))
        folder.setProperty("role", "muted")
        folder.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        open_btn = button(
            "Open folder",
            "secondary",
            "folder",
            theme,
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ctx.paths.root))),
        )
        holder = QWidget()
        h = QHBoxLayout(holder)
        h.setContentsMargins(0, 0, 0, 0)
        h.addWidget(folder)
        h.addWidget(open_btn)
        data_rows.append(_row("Data folder", "Your database, photos and logs live here.", holder))
        self.add(_section("Data", data_rows))

        logs_btn = button(
            "Open log folder",
            "secondary",
            None,
            None,
            lambda: QDesktopServices.openUrl(QUrl.fromLocalFile(str(ctx.paths.logs))),
        )
        self.add(
            _section(
                "About",
                [
                    _row(
                        f"WildLife {__version__}",
                        f"Data format version {ctx.schema_version}. Species: UK Species Inventory, Natural History "
                        "Museum (CC BY 4.0). Map data © OpenStreetMap contributors.",
                        logs_btn,
                    ),
                ],
            )
        )
        self.finish()

    def _set_theme(self, key: str) -> None:
        theme = Theme(key)
        self._ctx.settings.update(theme=theme)
        self._theme.set_theme(theme)
