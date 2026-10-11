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
    window = MainWindow(ctx, theme)
    w, h = (int(v) for v in args.size.split("x"))
    window.resize(w, h)
    window.show()
    args.out.mkdir(parents=True, exist_ok=True)

    def capture() -> None:
        for theme_name in args.themes:
            theme.set_theme(Theme(theme_name))
            for page in args.pages:
                window.go(page)
                app.processEvents()
                target = args.out / f"{page}-{theme_name}.png"
                window.grab().save(str(target))
                print(target)
        app.quit()

    QTimer.singleShot(500, capture)
    app.exec()
    ctx.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
