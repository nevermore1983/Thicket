"""Smoke tests for the application shell (pytest-qt drives a real window)."""

import pytest
from PySide6.QtCore import QSettings, Qt
from PySide6.QtWidgets import QApplication, QLabel

from wildlife.config.settings import Theme
from wildlife.context import AppContext
from wildlife.ui.components.common import EmptyState
from wildlife.ui.main_window import NAV, MainWindow
from wildlife.ui.theme.manager import ThemeManager
from wildlife.ui.theme.tokens import DARK, LIGHT


@pytest.fixture
def window(qtbot, paths, tmp_path):
    QSettings.setPath(
        QSettings.Format.IniFormat, QSettings.Scope.UserScope, str(tmp_path / "qsettings")
    )
    QSettings.setDefaultFormat(QSettings.Format.IniFormat)
    ctx = AppContext.open(paths)
    theme = ThemeManager(QApplication.instance(), ctx.settings.current.theme)
    theme.apply()
    win = MainWindow(ctx, theme)
    qtbot.addWidget(win)
    win.show()
    qtbot.waitExposed(win)
    yield win
    ctx.close()


def test_opens_on_dashboard_with_welcome(window):
    assert window.current_page() == "dashboard"
    titles = [
        w.text() for w in window.pages.currentWidget().findChildren(QLabel, "EmptyStateTitle")
    ]
    assert titles == ["Start your wildlife journal"]


def test_every_page_opens_and_has_content(window, qtbot):
    for entry in NAV:
        qtbot.mouseClick(window._nav_buttons[entry.key], Qt.MouseButton.LeftButton)
        assert window.current_page() == entry.key
        page = window.pages.currentWidget()
        assert page.findChildren(EmptyState), f"{entry.key} has no empty state"


def test_keyboard_shortcuts(window, qtbot):
    qtbot.keyClick(window, Qt.Key.Key_3, Qt.KeyboardModifier.ControlModifier)
    assert window.current_page() == "calendar"
    qtbot.keyClick(window, Qt.Key.Key_K, Qt.KeyboardModifier.ControlModifier)
    assert window.search.hasFocus()
    qtbot.keyClick(window, Qt.Key.Key_N, Qt.KeyboardModifier.ControlModifier)
    assert window.toasts.messages() == ["Adding sightings arrives in the next phase"]


def test_theme_switch_from_settings_is_saved(window, qtbot):
    window.go("settings")
    page = window.pages.currentWidget()
    qtbot.mouseClick(page.theme_choice.button_for(Theme.DARK), Qt.MouseButton.LeftButton)
    assert window.theme.tokens is DARK
    assert DARK.bg in QApplication.instance().styleSheet()
    assert window.ctx.settings.current.theme is Theme.DARK
    qtbot.mouseClick(page.theme_choice.button_for(Theme.LIGHT), Qt.MouseButton.LeftButton)
    assert window.theme.tokens is LIGHT


def test_sidebar_collapses_to_icons_when_narrow(window):
    window.setMinimumSize(0, 0)
    window.resize(820, 700)
    assert window._sidebar.width() == 60
    assert window._nav_buttons["map"].text() == ""
    window.resize(1280, 800)
    assert window._nav_buttons["map"].text() == "Map"


def test_toast_undo_runs_the_undo(window, qtbot):
    undone = []
    window.toasts.show("Robin saved", undo=lambda: undone.append(True))
    qtbot.keyClick(window, Qt.Key.Key_Z, Qt.KeyboardModifier.ControlModifier)
    assert undone == [True]
    assert "Undone" in window.toasts.messages()
