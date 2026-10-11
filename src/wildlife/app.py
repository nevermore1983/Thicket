"""Starting WildLife: logging, data folder, database, theme, then the main window."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QTimer, QUrl
from PySide6.QtGui import QDesktopServices
from PySide6.QtWidgets import QApplication, QMessageBox

from wildlife import __version__
from wildlife.config.paths import DataPaths, default_data_root
from wildlife.context import AppContext
from wildlife.domain.errors import WildlifeError
from wildlife.logging_setup import setup_logging

log = logging.getLogger("wildlife")


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="wildlife", description="WildLife wildlife journal")
    parser.add_argument("--data-dir", type=Path, help="use this data folder instead of the default")
    parser.add_argument("--debug", action="store_true", help="write detailed logs")
    # Used to check a packaged build: open the window, then close and exit 0.
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    paths = DataPaths(args.data_dir or default_data_root()).ensure()
    setup_logging(paths.logs, debug=args.debug)
    log.info("Starting WildLife %s", __version__)

    QCoreApplication.setOrganizationName("WildLife")
    QCoreApplication.setApplicationName("WildLife")
    QCoreApplication.setApplicationVersion(__version__)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    app = QApplication(sys.argv[:1])

    # Imported after QApplication exists (these create Qt objects)
    from wildlife.ui import error_handler
    from wildlife.ui.main_window import MainWindow
    from wildlife.ui.single_instance import InstanceServer, another_instance_is_running
    from wildlife.ui.theme.manager import ThemeManager

    if not args.smoke_test and another_instance_is_running():
        log.info("Already running; asked the existing window to come forward")
        return 0

    reporter = error_handler.ErrorReporter()
    error_handler.install(reporter)
    try:
        ctx = AppContext.open(paths)
    except WildlifeError as exc:
        log.exception("Could not open data")
        _startup_failed(exc.user_message, paths)
        return 1

    theme = ThemeManager(app, ctx.settings.current.theme)
    theme.apply()
    window = MainWindow(ctx, theme)
    reporter.set_window(window)
    if not args.smoke_test:
        InstanceServer(lambda: (window.showNormal(), window.raise_(), window.activateWindow()), app)
    window.show()
    if args.smoke_test:
        QTimer.singleShot(1500, lambda: (_smoke_checks(), app.quit()))
    else:
        QTimer.singleShot(0, lambda: _after_start(ctx, theme, window))
    try:
        return app.exec()
    finally:
        ctx.close()
        log.info("Closed")


def _smoke_checks() -> None:
    """Checks a packaged build can reach its bundled files (used by scripts/build_exe.py)."""
    from wildlife.services.species_catalogue import bundled_catalogue, read_records

    path, info = bundled_catalogue()
    first = read_records(path)[0]
    log.info(
        "Smoke test: catalogue %s, %s taxa, first %s",
        info["version"],
        f"{info['taxa']:,}",
        first["k"],
    )
    log.info("Smoke test OK")


def _after_start(ctx: AppContext, theme, window) -> None:
    """Jobs that run once the window is showing."""
    from wildlife.ui.dialogs import FirstRunDialog

    if ctx.catalogue.needs_install():
        FirstRunDialog(ctx, theme, updating=ctx.catalogue.installed_version() is not None).exec()
    removed = ctx.sightings.purge_recycle_bin()
    if removed:
        log.info("Emptied %d old sightings from the recycle bin", removed)
    ctx.outings.purge_deleted()
    if ctx.backup.is_due():
        window.backup_now("auto")


def _startup_failed(message: str, paths: DataPaths) -> None:
    box = QMessageBox(QMessageBox.Icon.Critical, "WildLife", message)
    box.setInformativeText(f"Data folder: {paths.root}")
    open_folder = box.addButton("Open data folder", QMessageBox.ButtonRole.ActionRole)
    box.addButton(QMessageBox.StandardButton.Close)
    box.exec()
    if box.clickedButton() is open_folder:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.root)))


if __name__ == "__main__":
    raise SystemExit(main())
