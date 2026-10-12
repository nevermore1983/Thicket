"""Open the app off-screen, capture pages in light and dark, and save PNGs.

Used to check the real Qt UI after each change. Uses a throwaway data folder
unless --data-dir is given.

    uv run python scripts/screenshot.py --pages dashboard settings --out local_data/shots
"""

from __future__ import annotations

import argparse
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication, Qt, QTimer
from PySide6.QtWidgets import QApplication, QLabel, QScrollArea


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
    from wildlife.ui.web import scheme

    scheme.prepare()
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
        """'dashboard' etc. = a page; 'add' / 'detail' / 'edit' = the side panel over Sightings;
        'calendar-month' etc. = a calendar view; 'day-panel', 'outing', 'outing-edit', 'outings'."""
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
        elif target.startswith("calendar-"):  # calendar-year / -month / -week / -day
            window.go("calendar")
            window.calendar_page.selected = None
            window.calendar_page.go_to(ctx.sightings._today(), target.split("-", 1)[1])
        elif target == "day-panel":
            window.go("calendar")
            page = window.calendar_page
            page.set_view("month")
            busiest = max(page.month_view.days.values(), key=lambda s: s.sightings, default=None)
            if busiest:
                page.select(busiest.day)
        elif target in ("outing", "outing-edit"):
            outings = ctx.outings.page(0, 1)
            if outings:
                window.go("calendar")
                window.calendar_page.go_to(outings[0].outing_date, "day")
                if target == "outing":
                    window.open_outing(outings[0].id)
                else:
                    window.edit_outing(outings[0].id)
        elif target.startswith("map-"):  # map-pins / map-heat / map-squares
            window.go("map")
            wait(lambda: window.map_page.ready or window.map_page.failed, 15)
            window.map_page.set_mode(target.split("-", 1)[1])
            wait(lambda: window.map_page._bounds is not None, 5)
            window.map_page.fit()
            wait(lambda: False, 4)  # tiles, data and squares load in the background
        elif target.startswith("photos-"):  # photos-library / photos-inbox / photos-selected
            page = window.photos_page
            window.go("photos")
            page.show_tab("library" if target == "photos-library" else "inbox")
            if target == "photos-selected" and page._inbox_grids:
                page._inbox_grids[0].select_all()
            wait(lambda: False, 1)
            page.loader.wait_idle()
            wait(lambda: False, 0.5)
        elif target in ("viewer", "viewer-info", "add-from-photos"):
            page = window.photos_page
            window.go("photos")
            if target == "add-from-photos":
                page.show_tab("inbox")
                if page._inbox_grids:
                    page._inbox_grids[0].select_all()
                    page._create_sighting()
                return None
            page.show_tab("library")
            viewer = page.open_viewer(
                [i.photo for i in page._library], 0, [i.name for i in page._library]
            )
            viewer.resize(window.size())
            if target == "viewer-info":
                viewer.toggle_info()
            wait(lambda: False, 2)
            return viewer
        elif target.startswith("statistics"):  # statistics / statistics-all / statistics-last
            from wildlife.services.statistics import Period

            page = window.statistics_page
            window.go("statistics")
            today = ctx.statistics.today()
            period = {
                "statistics": Period.this_year(today),
                "statistics-all": Period.all_time(),
                "statistics-last": Period.last_year(today),
            }[target]
            page.data = None
            page.set_period(period)
            wait(lambda: page.data is not None and page.data.period == period, 10)
            wait(lambda: False, 0.5)
        elif target == "species-profile":  # this year's list, with the top species' profile
            page = window.species_page
            window.go("species")
            page._choose(ctx.statistics.today().year)
            page.table.sortItems(2, Qt.SortOrder.DescendingOrder)
            page.table.selectRow(0)
        elif target.startswith("inat"):  # inat-start / inat-check / inat-done (invented rows)
            return import_dialog(target)
        elif target == "csv-map":  # a spreadsheet's columns being matched (invented rows)
            window.go("settings")
            sheet = Path(tempfile.mkdtemp(prefix="wildlife-csv-")) / "Garden list 2025.csv"
            sheet.write_text(
                "Bird,Date seen,Time,Site,How many,Comments\n"
                "Robin,03/05/2025,07:40,Garden,2,Singing from the fence\n"
                "Blackbird,04/05/2025,18:15,Garden,c. 3,\n",
                encoding="utf-8",
            )
            dialog = window.import_data("csv")
            dialog.resize(640, 640)
            dialog.open_file(sheet)
            wait(lambda: dialog.pages.currentIndex() == 1, 10)
            return dialog
        elif target == "settings-exchange":  # Settings, scrolled to Import & export
            window.go("settings")
            page = window.settings_page
            heading = next(w for w in page.findChildren(QLabel) if w.text() == "Import & export")
            scroll = page.findChild(QScrollArea)
            scroll.ensureWidgetVisible(heading, 0, 0)
            scroll.verticalScrollBar().setValue(heading.parentWidget().y() - 8)
        elif target == "export":
            window.go("settings")
            dialog = window.export_data(None)
            dialog.formats["dwc"].setChecked(True)
            dialog.with_photos.setChecked(True)
            dialog.blur.set_current("1000")
            dialog.blur.changed.emit("1000")
            wait(lambda: False, 0.3)
            return dialog
        elif target == "shortcuts":
            dialog = window.show_shortcuts()
            dialog.resize(620, 720)
            wait(lambda: False, 0.3)
            return dialog
        elif target == "health":
            window.go("settings")
            dialog = window.health_check()
            dialog.resize(620, 560)
            wait(lambda: dialog.report is not None, 30)
            return dialog
        elif target == "restore":
            window.go("settings")
            dialog = window.restore_backup()
            wait(lambda: False, 0.3)
            return dialog
        elif target == "outings":
            window.go("sightings")
            window.sightings_page.show_tab("outings")
        else:
            window.go(target)
            if target == "sightings":
                window.sightings_page.show_tab("sightings")

    def import_dialog(target: str):
        if ctx.catalogue.needs_install():
            ctx.catalogue.install()
        window.go("settings")
        dialog = window.import_data("inaturalist")
        dialog.resize(640, 560)
        if target != "inat-start":
            export = Path(tempfile.mkdtemp(prefix="wildlife-inat-")) / "observations-12345.csv"
            write_invented_export(export)
            dialog.open_file(export)
            wait(lambda: dialog.pages.currentIndex() == 2, 10)
        if target == "inat-done":
            dialog.photos_box.setChecked(False)  # never download in a screenshot
            dialog._import()
            wait(lambda: dialog.outcome is not None, 10)
        wait(lambda: False, 0.3)
        return dialog

    def wait(done, seconds: float) -> None:
        """Keep the app running (so the map can load) until done() or the time is up."""
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline and not done():
            app.processEvents()
            time.sleep(0.02)

    def capture() -> None:
        for theme_name in args.themes:
            theme.set_theme(Theme(theme_name))
            for target in args.pages:
                extra = show(target)  # a separate window to capture instead (the viewer)
                for _ in range(3):
                    app.processEvents()
                path = args.out / f"{target}-{theme_name}.png"
                (extra or window).grab().save(str(path))
                print(path)
                if extra is not None:
                    if getattr(extra, "outcome", None) is not None:
                        extra.outcome.undo.run()  # leave the demo library as it was
                    extra.close()
                if window.panel.current() is not None:
                    window.panel.current()._dirty = False
        window.panel.close_panel()
        app.quit()

    QTimer.singleShot(500, capture)
    app.exec()
    ctx.close()
    return 0


def write_invented_export(path: Path) -> None:
    """A small iNaturalist-style export with made-up observations (never real records)."""
    import csv

    rows = [
        ("Erithacus rubecula", "European Robin", "Aves", "research", "2026-05-03 07:40:12"),
        ("Rubus fruticosus", "", "Plantae", "needs_id", "2026-05-03 08:02:40"),
        ("Amanita muscaria", "Fly Agaric", "Fungi", "research", "2025-10-19 14:11:05"),
        ("Zootoca vivipara", "Common Lizard", "Reptilia", "research", "2026-06-14 11:30:00"),
        ("Aglais io", "Peacock", "Insecta", "research", "2026-04-02 12:45:31"),
        ("Argynnis aglaja", "Dark Green Fritillary", "Insecta", "research", "2025-07-08 13:05:00"),
        ("Sphecodogastra", "", "Insecta", "needs_id", "2026-07-21 10:15:00"),
        ("Apioideae", "", "Plantae", "needs_id", "2026-07-21 10:20:00"),
        ("Bombus terrestris", "Buff-tailed Bumblebee", "Insecta", "research", ""),
    ]
    cols = [
        "id",
        "observed_on_string",
        "observed_on",
        "time_observed_at",
        "time_zone",
        "updated_at",
        "quality_grade",
        "url",
        "image_url",
        "place_guess",
        "latitude",
        "longitude",
        "positional_accuracy",
        "scientific_name",
        "common_name",
        "iconic_taxon_name",
        "captive_cultivated",
        "coordinates_obscured",
    ]
    with path.open("w", encoding="utf-8", newline="") as f:
        out = csv.DictWriter(f, cols)
        out.writeheader()
        for i, (sci, common, iconic, grade, when) in enumerate(rows):
            out.writerow(
                {
                    "id": 90000 + i,
                    "observed_on_string": when,
                    "observed_on": when[:10],
                    "time_zone": "London",
                    "updated_at": "2026-08-01 10:00:00 UTC",
                    "quality_grade": grade,
                    "place_guess": "Example Common, Exampleshire, UK",
                    "latitude": 51.48 + i / 1000,
                    "longitude": -0.61,
                    "positional_accuracy": 15,
                    "scientific_name": sci,
                    "common_name": common,
                    "iconic_taxon_name": iconic,
                    "captive_cultivated": "false",
                    "coordinates_obscured": "false",
                }
            )


if __name__ == "__main__":
    raise SystemExit(main())
