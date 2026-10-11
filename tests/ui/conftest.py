"""Shared UI fixtures: a real main window over a temp data folder and the mini species list."""

import pytest
from PySide6.QtCore import QSettings
from PySide6.QtWidgets import QApplication

from wildlife.config.settings import Theme
from wildlife.ui.main_window import MainWindow
from wildlife.ui.theme.manager import ThemeManager
from wildlife.ui.web import scheme

scheme.prepare()  # imported before pytest-qt creates the QApplication


@pytest.fixture
def window(qtbot, ctx, tmp_path):
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "qsettings")
    )
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    theme = ThemeManager(QApplication.instance(), Theme.LIGHT)
    theme.apply()
    win = MainWindow(ctx, theme)
    # Not qtbot.addWidget(): pytest-qt would close the window before this fixture's cleanup,
    # and closing with unsaved changes rightly asks "Discard changes?", which no one can answer.
    win.resize(1360, 860)
    win.show()
    qtbot.waitExposed(win)
    win.activateWindow()
    yield win
    while (view := win.panel.current()) is not None:
        view._dirty = False
        win.panel.back()
    win.close()
    win.deleteLater()
