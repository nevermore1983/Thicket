"""Starting WildLife: logging, data folder, database, theme, then the main window."""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QThread, QTimer, QUrl
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
    # Set when WildLife restarts itself (after choosing a backup to restore): wait for the
    # old window to close instead of handing over to it.
    parser.add_argument("--restarting", action="store_true", help=argparse.SUPPRESS)
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
    from wildlife.ui.web import scheme

    scheme.prepare()  # before QApplication: the map's web engine needs it
    app = QApplication(sys.argv[:1])

    # Imported after QApplication exists (these create Qt objects)
    from wildlife.ui import error_handler
    from wildlife.ui.main_window import MainWindow
    from wildlife.ui.single_instance import InstanceServer
    from wildlife.ui.theme.manager import ThemeManager

    if not args.smoke_test and _already_running(args.restarting):
        log.info("Already running; asked the existing window to come forward")
        return 0

    from wildlife.data.restore import apply_pending_restore

    restored = apply_pending_restore(paths)  # before anything opens the database

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
        ctx.settings.update(allow_online=False)  # a build check must not depend on the internet
        QTimer.singleShot(500, lambda: _run_smoke_checks(window, app))
    else:
        QTimer.singleShot(0, lambda: _after_start(ctx, theme, window, restored))
    try:
        return app.exec()
    finally:
        ctx.close()
        log.info("Closed")


def _run_smoke_checks(window, app) -> None:
    """A build check must never wait for a person: any error is logged and exits with 1."""
    try:
        _smoke_checks(window, app)
    except Exception:
        log.exception("Smoke test FAILED")
        app.exit(1)


def _smoke_checks(window, app) -> None:
    """Checks a packaged build can reach its bundled files and run the map
    (used by scripts/build_exe.py). Quits when done."""
    from wildlife.services.species_catalogue import bundled_catalogue, read_records

    path, info = bundled_catalogue()
    first = read_records(path)[0]
    log.info(
        "Smoke test: catalogue %s, %s taxa, first %s",
        info["version"],
        f"{info['taxa']:,}",
        first["k"],
    )
    _smoke_raw()
    window.go("map")
    waited = 0

    def check_map() -> None:
        nonlocal waited
        page = window.map_page
        if page.ready or page.failed or waited >= 20_000:
            log.info("Smoke test: map %s", "ready" if page.ready else "FAILED")
            if page.ready:
                log.info("Smoke test OK")
            app.quit()
            return
        waited += 250
        QTimer.singleShot(250, check_map)

    check_map()


def _smoke_raw() -> None:
    """Prove the RAW libraries (rawpy with LibRaw, and numpy) were bundled and load.
    Rendering RAW files is covered by the tests, against tests/fixtures/photos/sample.dng."""
    import numpy
    import rawpy

    version = ".".join(map(str, rawpy.libraw_version))
    log.info("Smoke test: RAW ok (LibRaw %s, numpy %s)", version, numpy.__version__)


def _already_running(restarting: bool) -> bool:
    from wildlife.ui.single_instance import another_instance_is_running

    if not restarting:
        return another_instance_is_running()
    for _ in range(40):  # the old window is closing: wait up to ~12 s for it to go
        if not another_instance_is_running(ask_to_show=False):
            return False
        QThread.msleep(300)
    return another_instance_is_running()


def _after_start(ctx: AppContext, theme, window, restored=None) -> None:
    """Jobs that run once the window is showing."""
    from wildlife.ui.dialogs import FirstRunDialog

    if restored is not None:
        window.show_restore_outcome(restored)

    if ctx.catalogue.needs_install():
        FirstRunDialog(ctx, theme, updating=ctx.catalogue.installed_version() is not None).exec()
    removed = ctx.sightings.purge_recycle_bin()
    if removed:
        log.info("Emptied %d old sightings from the recycle bin", removed)
    ctx.outings.purge_deleted()
    ctx.photos.purge_recycle_bin()  # after sightings: their unused photos go with them
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
