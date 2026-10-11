"""Build the Windows app folder with PyInstaller, trim it, and smoke-test it.

    uv run --with "pyinstaller>=6.16" python scripts/build_exe.py

Output: build/dist/WildLife/WildLife.exe (a folder app; Phase 14 wraps it in an
installer). The smoke test starts the built .exe against a temporary data
folder and checks it opens and exits cleanly.
"""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
DIST = BUILD / "dist" / "WildLife"

# Qt modules WildLife never uses. Excluding them keeps the download smaller.
EXCLUDE = [
    "PySide6.Qt3DAnimation",
    "PySide6.Qt3DCore",
    "PySide6.Qt3DExtras",
    "PySide6.Qt3DInput",
    "PySide6.Qt3DLogic",
    "PySide6.Qt3DRender",
    "PySide6.QtBluetooth",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtGraphs",
    "PySide6.QtGraphsWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtMultimediaWidgets",
    "PySide6.QtNfc",
    "PySide6.QtQuick3D",
    "PySide6.QtRemoteObjects",
    "PySide6.QtScxml",
    "PySide6.QtSensors",
    "PySide6.QtSerialBus",
    "PySide6.QtSerialPort",
    "PySide6.QtSpatialAudio",
    "PySide6.QtSql",
    "PySide6.QtStateMachine",
    "PySide6.QtTest",
    "PySide6.QtTextToSpeech",
    "PySide6.QtUiTools",
    "PySide6.QtDesigner",
    "PySide6.QtHelp",
    "PySide6.QtHttpServer",
    "PySide6.QtLocation",
    "PySide6.QtWebSockets",
    "PySide6.QtAxContainer",
    "tkinter",
    "unittest",
    "pydoc",
]
KEEP_LOCALES = {"en-GB.pak", "en-US.pak"}  # browser-engine translations we keep


def run_pyinstaller() -> None:
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onedir",
        "--windowed",
        "--name",
        "WildLife",
        "--distpath",
        str(BUILD / "dist"),
        "--workpath",
        str(BUILD / "work"),
        "--specpath",
        str(BUILD),
        "--collect-data",
        "wildlife",  # migrations (.sql) and future resources
        *[arg for mod in EXCLUDE for arg in ("--exclude-module", mod)],
        str(ROOT / "src" / "wildlife" / "__main__.py"),
    ]
    subprocess.run(cmd, check=True, cwd=ROOT)


def trim() -> int:
    """Remove files the app can't use. Returns bytes saved."""
    saved = 0
    qt = DIST / "_internal" / "PySide6"
    for path in [qt / "qml", qt / "opengl32sw.dll"]:
        if path.exists():
            saved += size_of(path)
            shutil.rmtree(path) if path.is_dir() else path.unlink()
    locales = qt / "translations" / "qtwebengine_locales"
    for pak in locales.glob("*.pak") if locales.exists() else []:
        if pak.name not in KEEP_LOCALES:
            saved += pak.stat().st_size
            pak.unlink()
    for qm in (qt / "translations").glob("*.qm"):
        if not qm.name.endswith(("_en.qm", "_en_GB.qm")):
            saved += qm.stat().st_size
            qm.unlink()
    return saved


def size_of(path: Path) -> int:
    return (
        path.stat().st_size
        if path.is_file()
        else sum(p.stat().st_size for p in path.rglob("*") if p.is_file())
    )


def smoke_test() -> None:
    exe = DIST / "WildLife.exe"
    with tempfile.TemporaryDirectory() as tmp:
        start = time.perf_counter()
        result = subprocess.run([str(exe), "--smoke-test", "--data-dir", tmp], timeout=60)
        elapsed = time.perf_counter() - start
        log = (Path(tmp) / "logs" / "wildlife.log").read_text(encoding="utf-8")
    ok = result.returncode == 0 and "Smoke test OK" in log and "Smoke test: catalogue" in log
    print(
        f"Smoke test: {'PASS' if ok else 'FAIL'} (exit {result.returncode}, {elapsed:.1f} s incl. 1.5 s wait)"
    )
    if not ok:
        print(log[-2000:])
        raise SystemExit(1)


def main() -> None:
    run_pyinstaller()
    saved = trim()
    print(f"Trimmed {saved / 1e6:.0f} MB. App folder: {size_of(DIST) / 1e6:.0f} MB at {DIST}")
    smoke_test()


if __name__ == "__main__":
    main()
