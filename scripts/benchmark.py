"""Measure WildLife against the targets in the spec (docs/02, section 9).

Opens the real window on a library (normally the full stress library) and times each
thing the spec gives a target for, then prints a table with pass/fail.

    uv run python scripts/benchmark.py --data-dir local_data/demo13
    uv run python scripts/benchmark.py --data-dir local_data/demo13 --soak 40

--soak N also goes round every page and panel N times, reporting memory after each round,
to catch slow-downs or memory that keeps growing in long use. Nothing is saved to the
library except a few timing sightings (removed again) and one backup.
"""

from __future__ import annotations

import argparse
import ctypes
import ctypes.wintypes
import os
import statistics
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QEvent, QTimer
from PySide6.QtWidgets import QApplication, QScrollArea

STARTED = time.perf_counter()


class _Counters(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.wintypes.DWORD),
        ("PageFaultCount", ctypes.wintypes.DWORD),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
        ("PrivateWorkingSetSize", ctypes.c_size_t),  # PROCESS_MEMORY_COUNTERS_EX2
        ("SharedCommitUsage", ctypes.c_size_t),
    ]


class _Entry(ctypes.Structure):  # PROCESSENTRY32W
    _fields_ = [
        ("dwSize", ctypes.wintypes.DWORD),
        ("cntUsage", ctypes.wintypes.DWORD),
        ("th32ProcessID", ctypes.wintypes.DWORD),
        ("th32DefaultHeapID", ctypes.c_size_t),
        ("th32ModuleID", ctypes.wintypes.DWORD),
        ("cntThreads", ctypes.wintypes.DWORD),
        ("th32ParentProcessID", ctypes.wintypes.DWORD),
        ("pcPriClassBase", ctypes.c_long),
        ("dwFlags", ctypes.wintypes.DWORD),
        ("szExeFile", ctypes.c_wchar * 260),
    ]


def _private_mb(pid: int) -> float:
    kernel32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    handle = kernel32.OpenProcess(0x1000 | 0x0010, False, pid)  # query limited + read
    if not handle:
        return 0.0
    try:
        counters = _Counters()
        counters.cb = ctypes.sizeof(counters)
        psapi.GetProcessMemoryInfo(handle, ctypes.byref(counters), counters.cb)
        # Private memory in RAM: what Task Manager's Memory column shows. (Adding working
        # sets would count memory the browser-engine processes share once per process.)
        return counters.PrivateWorkingSetSize / 1e6
    finally:
        kernel32.CloseHandle(handle)


def own_memory_mb() -> float:
    return _private_mb(os.getpid())


def web_engine_memory_mb() -> float:
    """The map's browser engine runs in its own processes, started by this one (and
    those start more): add up every process descended from this one."""
    kernel32 = ctypes.windll.kernel32
    kernel32.CreateToolhelp32Snapshot.restype = ctypes.wintypes.HANDLE
    snap = kernel32.CreateToolhelp32Snapshot(0x2, 0)  # all processes
    parent_of: dict[int, int] = {}
    entry = _Entry()
    entry.dwSize = ctypes.sizeof(entry)
    ok = kernel32.Process32FirstW(snap, ctypes.byref(entry))
    while ok:
        parent_of[entry.th32ProcessID] = entry.th32ParentProcessID
        ok = kernel32.Process32NextW(snap, ctypes.byref(entry))
    kernel32.CloseHandle(snap)
    family, grew = {os.getpid()}, True
    while grew:
        children = {pid for pid, parent in parent_of.items() if parent in family} - family
        family |= children
        grew = bool(children)
    return sum(_private_mb(pid) for pid in family - {os.getpid()})


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--soak", type=int, default=0, help="rounds of every page and panel")
    args = parser.parse_args()
    sys.stdout.reconfigure(encoding="utf-8")

    from wildlife.config.paths import DataPaths
    from wildlife.context import AppContext
    from wildlife.logging_setup import setup_logging

    paths = DataPaths(args.data_dir)
    setup_logging(paths.logs)
    QCoreApplication.setOrganizationName("WildLife-Benchmark")
    from wildlife.ui.web import scheme

    scheme.prepare()
    app = QApplication(sys.argv[:1])
    from wildlife.domain.filters import SightingFilter
    from wildlife.domain.models import SightingDraft
    from wildlife.services.statistics import Period
    from wildlife.ui.main_window import MainWindow
    from wildlife.ui.theme.manager import ThemeManager

    ctx = AppContext.open(paths)
    theme = ThemeManager(app)
    theme.apply()
    window = MainWindow(ctx, theme)
    window.resize(1360, 860)
    window.show()
    results: list[tuple[str, str, str, bool]] = []  # what, measured, target, ok

    def pump(done=lambda: False, seconds: float = 0.0) -> None:
        end = time.perf_counter() + seconds
        while True:
            app.processEvents()
            # what returning to the event loop does: delete closed panels (deleteLater)
            QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
            if done() or time.perf_counter() >= end:
                return
            time.sleep(0.002)

    def timed(fn, until=lambda: True, limit: float = 30.0) -> float:
        t = time.perf_counter()
        fn()
        pump(until, limit)
        return time.perf_counter() - t

    def record(what: str, seconds: float, target: float, unit: str = "s") -> None:
        value = f"{seconds * 1000:.0f} ms" if unit == "ms" else f"{seconds:.2f} s"
        goal = f"≤ {target * 1000:.0f} ms" if unit == "ms" else f"≤ {target:g} s"
        results.append((what, value, goal, seconds <= target))
        print(f"  {what}: {value} (target {goal})", flush=True)

    def run() -> None:
        pump(seconds=0.3)
        record("Start-up (window usable)", time.perf_counter() - STARTED, 3.0)
        today = ctx.sightings._today()
        robin = ctx.catalogue.search("robin", 1)[0].taxon.id
        saves, made = [], []
        for _ in range(30):
            t = time.perf_counter()
            made.append(ctx.sightings.save(SightingDraft(robin, today)).sighting.id)
            saves.append(time.perf_counter() - t)
        with ctx.db.transaction() as conn:  # take the timing sightings out again
            conn.executemany("DELETE FROM sighting WHERE id = ?", [(i,) for i in made])
        record("Saving a sighting (median)", statistics.median(saves), 0.1, "ms")

        popup = window.search_popup
        window.search.setText("")
        t = time.perf_counter()
        window.search.setText("kingf")
        popup._refresh()
        record("Global search results", time.perf_counter() - t, 0.2, "ms")
        popup.hide()

        window.go("sightings")
        page = window.sightings_page
        some_place = ctx.places.all()[3].id
        record(
            "Sightings list: filter change",
            timed(lambda: page.set_filter(SightingFilter(place_ids=frozenset({some_place})))),
            0.3,
            "ms",
        )
        record(
            "Sightings list: back to all",
            timed(lambda: page.set_filter(SightingFilter())),
            0.3,
            "ms",
        )

        window.go("calendar")
        cal = window.calendar_page
        for view in ("year", "week", "day", "month"):
            record(f"Calendar: {view} view", timed(lambda v=view: cal.set_view(v)), 0.3, "ms")

        map_page = window.map_page
        t = time.perf_counter()
        window.go("map")
        pump(lambda: map_page.ready and "on the map" in map_page.status.text(), 30)
        record("Map: first load of all pins", time.perf_counter() - t, 2.0)

        window.go("statistics")
        st = window.statistics_page
        st.data = None
        record(
            "Statistics page (all time)",
            timed(lambda: st.set_period(Period.all_time()), lambda: st.data is not None),
            1.5,
        )

        mem = own_memory_mb() + web_engine_memory_mb()
        results.append(
            ("Memory in normal use (app + map engine)", f"{mem:.0f} MB", "≤ 600 MB", mem <= 600)
        )
        print(f"  Memory: {mem:.0f} MB", flush=True)

        window.go("photos")
        photos = window.photos_page
        photos.show_tab("library")
        pump(seconds=0.5)
        grid = photos.library_grid
        scroll = grid.parentWidget()
        while scroll is not None and not isinstance(scroll, QScrollArea):
            scroll = scroll.parentWidget()  # the grid sits in a scroll area
        bar = scroll.verticalScrollBar() if scroll is not None else None
        steps = []
        if bar is not None and bar.maximum() > 0:
            for i in range(60):
                t = time.perf_counter()
                bar.setValue(int(bar.maximum() * i / 60))
                grid.repaint()
                steps.append(time.perf_counter() - t)
            record(
                f"Photo grid scroll step ({len(photos._library):,} photos)",
                max(steps),
                1 / 30,
                "ms",
            )

        with tempfile.TemporaryDirectory() as tmp:
            from PIL import Image

            files = []
            for i in range(60):
                f = Path(tmp) / f"bench_{i}.jpg"
                Image.new("RGB", (1600, 1200), (i * 4 % 255, 120, 60)).save(f, quality=90)
                files.append(f)
            scratch = DataPaths(Path(tmp) / "lib")
            other = AppContext.open(scratch)
            try:
                t = time.perf_counter()
                other.photos.import_files(files)
                rate = len(files) / (time.perf_counter() - t)
            finally:
                other.close()
        results.append(("Photo import", f"{rate:.0f} photos/s", "≥ 5 photos/s", rate >= 5))
        print(f"  Photo import: {rate:.0f} photos/s", flush=True)

        t = time.perf_counter()
        ctx.backup.backup_now("manual")
        record("Backup (verified snapshot + photo mirror)", time.perf_counter() - t, 10.0)

        mem = own_memory_mb() + web_engine_memory_mb()
        results.append(
            ("Memory after scrolling through every photo", f"{mem:.0f} MB", "for information", True)
        )
        print(f"  Memory after the photo scroll: {mem:.0f} MB", flush=True)

        if args.soak:
            soak(args.soak)
        app.quit()

    def soak(rounds: int) -> None:
        first = None
        sighting = ctx.sightings.page(SightingFilter(), limit=1)[0]
        for r in range(1, rounds + 1):
            t = time.perf_counter()
            for key in (
                "dashboard",
                "sightings",
                "calendar",
                "map",
                "photos",
                "statistics",
                "species",
                "places",
                "settings",
            ):
                step = time.perf_counter()
                window.go(key)
                pump(seconds=0.05)
                if r == 1 and time.perf_counter() - step > 1:
                    print(f"    slow first visit: {key} {time.perf_counter() - step:.1f} s")
            window.open_sighting(sighting.id)
            window.edit_sighting(sighting.id)
            window.panel.current()._dirty = False
            window.open_species(sighting.taxon_id)
            window.open_day(sighting.observed_date, SightingFilter())
            window.panel.close_panel()
            pump(seconds=0.2)
            mem = own_memory_mb()
            first = first or mem
            print(
                f"  round {r:3d}: {time.perf_counter() - t:5.2f} s, app memory {mem:6.0f} MB "
                f"({mem - first:+.0f} MB since round 1)",
                flush=True,
            )
        results.append(
            (
                f"Long use: {rounds} rounds of every page",
                f"{mem - first:+.0f} MB",
                "no steady growth",
                mem - first < 60,
            )
        )

    QTimer.singleShot(0, run)
    app.exec()
    ctx.close()
    print("\n| Measure | Result | Target | |\n|---|---|---|---|")
    for what, value, goal, ok in results:
        print(f"| {what} | {value} | {goal} | {'✅' if ok else '❌'} |")
    return 0 if all(ok for *_, ok in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
