"""Open the app off-screen, capture pages in light and dark, and save PNGs.

Used to check the real Qt UI after each change. Uses a throwaway data folder
unless --data-dir is given.

    uv run python scripts/screenshot.py --pages dashboard settings --out local_data/shots
"""

from __future__ import annotations

import argparse
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QTimer
from PySide6.QtWidgets import QApplication


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--pages", nargs="+", default=["dashboard", "settings"])
    parser.add_argument("--themes", nargs="+", default=["light", "dark"])
    parser.add_argument("--size", default="1280x820")
    parser.add_argument("--out", type=Path, default=Path("local_data/shots"))
    parser.add_argument("--data-dir", type=Path)
    args = parser.parse_args()

    from wildlife.config.paths import DataPaths
    from wildlife.config.settings import Theme
    from wildlife.context import AppContext
    from wildlife.logging_setup import setup_logging

    data_dir = args.data_dir or Path(tempfile.mkdtemp(prefix="wildlife-shot-"))
    paths = DataPaths(data_dir).ensure()
    setup_logging(paths.logs)
    QCoreApplication.setOrganizationName("WildLife-Screenshots")  # don't touch real window state
    app = QApplication(sys.argv[:1])

    from wildlife.ui.main_window import MainWindow
    from wildlife.ui.theme.manager import ThemeManager

    ctx = AppContext.open(paths)
    theme = ThemeManager(app)
    theme.apply()  # as the real app does, before any window exists
    window = MainWindow(ctx, theme)
    w, h = (int(v) for v in args.size.split("x"))
    window.resize(w, h)
    window.show()
    args.out.mkdir(parents=True, exist_ok=True)

    def show(target: str) -> None:
        """'dashboard' etc. = a page; 'add' / 'detail' / 'edit' = the side panel over Sightings."""
        window.panel.close_panel()
        if target in ("add", "detail", "edit"):
            window.go("sightings")
            first = (
                window.sightings_page.model.rows[0].id if window.sightings_page.model.rows else None
            )
            if target == "add":
                window.add_sighting()
                window.panel.current().picker.edit.setText("gold")
                window.panel.current().picker._refresh()
            elif first and target == "detail":
                window.open_sighting(first)
            elif first:
                window.edit_sighting(first)
        else:
            window.go(target)

    def capture() -> None:
        for theme_name in args.themes:
            theme.set_theme(Theme(theme_name))
            for target in args.pages:
                show(target)
                for _ in range(3):
                    app.processEvents()
                path = args.out / f"{target}-{theme_name}.png"
                window.grab().save(str(path))
                print(path)
                if window.panel.current() is not None:
                    window.panel.current()._dirty = False
        window.panel.close_panel()
        app.quit()

    QTimer.singleShot(500, capture)
    app.exec()
    ctx.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
