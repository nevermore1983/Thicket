"""Applies the light or dark theme, and follows Windows when set to System."""

from __future__ import annotations

from importlib import resources

from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from wildlife.config.settings import Theme
from wildlife.ui.theme.stylesheet import build_palette, build_qss
from wildlife.ui.theme.tokens import DARK, FONT_FALLBACK, FONT_UI, LIGHT, SIZE_BODY, Tokens


def load_bundled_fonts() -> list[str]:
    """Make the fonts shipped with WildLife available to Qt (once). Returns their families."""
    families: list[str] = []
    for font in resources.files("wildlife.resources.fonts").iterdir():
        if font.name.endswith((".ttf", ".otf")):
            with resources.as_file(font) as path:
                font_id = QFontDatabase.addApplicationFont(str(path))
            families += QFontDatabase.applicationFontFamilies(font_id) if font_id >= 0 else []
    return families


class ThemeManager(QObject):
    changed = Signal()  # widgets that draw their own colours (icons, charts) listen to this

    def __init__(self, app: QApplication, theme: Theme = Theme.SYSTEM) -> None:
        super().__init__(app)
        self._app, self._theme = app, theme
        self.tokens: Tokens = LIGHT
        app.setStyle("Fusion")  # a neutral base we fully control with the stylesheet
        load_bundled_fonts()
        font = QFont(FONT_UI)
        font.setFamilies([FONT_UI, FONT_FALLBACK])
        font.setPixelSize(SIZE_BODY)
        app.setFont(font)
        app.styleHints().colorSchemeChanged.connect(self._on_system_scheme_changed)

    @property
    def theme(self) -> Theme:
        return self._theme

    def set_theme(self, theme: Theme) -> None:
        self._theme = theme
        self.apply()

    def apply(self) -> None:
        hints = self._app.styleHints()
        if self._theme is Theme.SYSTEM:
            hints.unsetColorScheme()  # back to whatever Windows says
            dark = hints.colorScheme() == Qt.ColorScheme.Dark
        else:
            dark = self._theme is Theme.DARK
            # Also tells Windows to draw a matching (light/dark) title bar
            hints.setColorScheme(Qt.ColorScheme.Dark if dark else Qt.ColorScheme.Light)
        tokens = DARK if dark else LIGHT
        if tokens is self.tokens and self._app.styleSheet():
            return
        self.tokens = tokens
        self._app.setPalette(build_palette(tokens))
        self._app.setStyleSheet(build_qss(tokens))
        self.changed.emit()

    def _on_system_scheme_changed(self, _scheme: Qt.ColorScheme) -> None:
        if self._theme is Theme.SYSTEM:
            self.apply()
