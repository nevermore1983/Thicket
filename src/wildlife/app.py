"""Starting Thicket: logging, data folder, database, theme, then the main window."""

from __future__ import annotations

import argparse
import logging
import sys
from importlib import resources
from pathlib import Path
from typing import TYPE_CHECKING

from PySide6.QtCore import QCoreApplication, Qt, QThread, QThreadPool, QTimer, QUrl
from PySide6.QtGui import QDesktopServices, QIcon
from PySide6.QtWidgets import QApplication, QMessageBox

from wildlife import __version__
from wildlife.config.paths import DataPaths, default_data_root
from wildlife.context import AppContext
from wildlife.domain.errors import WildlifeError
from wildlife.logging_setup import setup_logging

if TYPE_CHECKING:
    from wildlife.data.restore import RestoreOutcome

log = logging.getLogger("wildlife")
# Thicket was called WildLife up to 1.1.0. Names Windows remembers keep that first name,
# so upgrades find everything where it was (packaging/installer.iss lists them all).
APP_USER_MODEL_ID = "WildLife.WildLife"  # also in packaging/installer.iss
RUNNING_MUTEX = "WildLife.Running"  # the installer waits while this exists (AppMutex)
_running = None  # the mutex handle, kept open until Thicket exits


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="wildlife", description="Thicket wildlife journal")
    parser.add_argument("--data-dir", type=Path, help="use this data folder instead of the default")
    parser.add_argument("--debug", action="store_true", help="write detailed logs")
    # Used to check a packaged build: open the window, then close and exit 0.
    parser.add_argument("--smoke-test", action="store_true", help=argparse.SUPPRESS)
    # Set when Thicket restarts itself (after choosing a backup to restore): wait for the
    # old window to close instead of handing over to it.
    parser.add_argument("--restarting", action="store_true", help=argparse.SUPPRESS)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(sys.argv[1:] if argv is None else argv)
    paths = DataPaths(args.data_dir or default_data_root()).ensure()
    setup_logging(paths.logs, debug=args.debug)
    log.info("Starting Thicket %s", __version__)

    # Where QSettings keeps window and view choices (the registry): the first name, kept
    QCoreApplication.setOrganizationName("WildLife")
    QCoreApplication.setApplicationName("WildLife")
    QCoreApplication.setApplicationVersion(__version__)
    QApplication.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )
    from wildlife.ui.web import scheme

    scheme.prepare()  # before QApplication: the map's web engine needs it
    _set_app_id()
    app = QApplication(sys.argv[:1])
    app.setWindowIcon(QIcon(str(resources.files("wildlife.resources.icons") / "wildlife.ico")))

    # Imported after QApplication exists (these create Qt objects)
    from wildlife.ui import error_handler
    from wildlife.ui.main_window import MainWindow
    from wildlife.ui.single_instance import InstanceServer
    from wildlife.ui.theme.manager import ThemeManager

    if not args.smoke_test and _already_running(args.restarting):
        log.info("Already running; asked the existing window to come forward")
        return 0
    _mark_running()

    reporter = error_handler.ErrorReporter()
    error_handler.install(reporter)
    opened = open_data(paths)
    if opened is None:
        return 1
    ctx, restored = opened

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
        # Let background work (e.g. an automatic backup) finish before the data file is
        # closed: closing it under a running job could crash, or cut a backup short.
        QThreadPool.globalInstance().waitForDone(60_000)
        ctx.close()
        log.info("Closed")


def open_data(paths: DataPaths) -> tuple[AppContext, RestoreOutcome | None] | None:
    """Open the data folder: (context, outcome of a restore done just now, or None).

    A restore chosen earlier is applied first, before anything opens the database. If
    the data can't be opened, you're told why and offered the latest backup; choosing it
    restores it (keeping a safety copy) and tries again. None if Thicket can't start."""
    from wildlife.data.restore import apply_pending_restore

    restored = apply_pending_restore(paths)
    try:
        return AppContext.open(paths), restored
    except WildlifeError as exc:
        log.exception("Could not open data")
        if not _startup_failed(exc.user_message, paths):
            return None
    restored = apply_pending_restore(paths)  # the latest backup, chosen just now
    try:
        return AppContext.open(paths), restored
    except WildlifeError as again:
        log.exception("Could not open the restored data either")
        _startup_failed(again.user_message, paths, offer_restore=False)
        return None


def _set_app_id() -> None:
    """Tell Windows this is Thicket, not "Python": the taskbar then shows Thicket's icon
    and groups its windows with the Start-menu shortcut (the installer uses the same ID)."""
    if sys.platform == "win32":
        import ctypes

        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_USER_MODEL_ID)


def _mark_running() -> None:
    """Let the installer see Thicket is open, so it asks you to close it first instead
    of replacing files under a running app. Windows removes the mark when Thicket exits."""
    global _running
    if sys.platform == "win32":
        import ctypes

        _running = ctypes.windll.kernel32.CreateMutexW(None, False, RUNNING_MUTEX)


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
    if app.windowIcon().isNull():
        raise RuntimeError("The app icon wasn't bundled")
    log.info("Smoke test: icon ok")
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


def _startup_failed(message: str, paths: DataPaths, offer_restore: bool = True) -> bool:
    """Explain why the data can't be opened. Offers the latest good backup if there is
    one; returns True if it was chosen (it's then noted to be restored)."""
    from wildlife.data.restore import latest_backup, request_restore

    latest = latest_backup(paths) if offer_restore else None
    box = QMessageBox(QMessageBox.Icon.Critical, "Thicket", message)
    info = f"Data folder: {paths.root}"
    restore = None
    if latest is not None:
        when = latest.created.astimezone()
        info += (
            f"\n\nYour latest backup is from {when:%d %b %Y at %H:%M} "
            f"({latest.sightings:,} sightings). Restoring it keeps a safety copy of the "
            "current data file."
        )
        restore = box.addButton("Restore latest backup", QMessageBox.ButtonRole.AcceptRole)
    box.setInformativeText(info)
    open_folder = box.addButton("Open data folder", QMessageBox.ButtonRole.ActionRole)
    box.addButton(QMessageBox.StandardButton.Close)
    box.exec()
    if restore is not None and box.clickedButton() is restore:
        request_restore(paths, latest.path)
        return True
    if box.clickedButton() is open_folder:
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(paths.root)))
    return False


if __name__ == "__main__":
    raise SystemExit(main())
