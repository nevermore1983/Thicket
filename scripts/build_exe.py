"""Build the Windows app folder with PyInstaller, trim it, and smoke-test it.

    uv run --with "pyinstaller==6.22.3" python scripts/build_exe.py

Output: build/dist/WildLife/WildLife.exe (a folder app, with its icon, version details,
THIRD-PARTY-NOTICES.txt and licenses/). scripts/build_installer.py then wraps it in the
installer. The smoke test starts the built .exe against a temporary data folder and
checks it opens and exits cleanly.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BUILD = ROOT / "build"
DIST = BUILD / "dist" / "WildLife"
ICON = ROOT / "src" / "wildlife" / "resources" / "icons" / "wildlife.ico"
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import notices  # noqa: E402

from wildlife import __version__  # noqa: E402

# Qt modules Thicket never uses. Excluding them keeps the download smaller.
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


def version_file() -> Path:
    """The details Windows shows in the .exe's Properties › Details."""
    numbers = (*(int(n) for n in __version__.split(".")), 0)
    path = BUILD / "version_info.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    strings = {
        "CompanyName": "Thicket",
        "FileDescription": "Thicket wildlife journal",
        "FileVersion": __version__,
        "InternalName": "Thicket",
        "LegalCopyright": "Thicket. Third-party notices: THIRD-PARTY-NOTICES.txt",
        "OriginalFilename": "WildLife.exe",
        "ProductName": "Thicket",
        "ProductVersion": __version__,
    }
    table = ", ".join(f"StringStruct({k!r}, {v!r})" for k, v in strings.items())
    lines = [
        "VSVersionInfo(",
        f"  ffi=FixedFileInfo(filevers={numbers}, prodvers={numbers}, mask=0x3f, flags=0x0,",
        "    OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),",
        f"  kids=[StringFileInfo([StringTable('080904B0', [{table}])]),",  # en-GB, Unicode
        "    VarFileInfo([VarStruct('Translation', [2057, 1200])])]",
        ")",
    ]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


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
        "WildLife",  # the .exe keeps its first name: taskbar pins point at it
        "--icon",
        str(ICON),
        "--version-file",
        str(version_file()),
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


def smoke_log_ok(returncode: int, log: str) -> tuple[bool, str]:
    """Did the packaged app's --smoke-test pass? (passed, what happened with the map)

    The map needs WebGL, which needs a graphics card. GitHub's build machines have none,
    so there (WILDLIFE_NO_GPU=1, set by the release workflow) "WebGL isn't available" is
    accepted: it means the map page and all its files loaded and ran; only drawing
    needs the graphics card. Everywhere else the map must really draw."""
    basics = (
        returncode == 0
        and "Smoke test: catalogue" in log
        and "Smoke test: RAW ok" in log
        and "Smoke test: icon ok" in log
    )
    if "Smoke test: map ready" in log and "Smoke test OK" in log:
        return basics, "map drawn"
    if os.environ.get("WILDLIFE_NO_GPU") == "1" and "Map page: no_webgl" in log:
        return basics, "map loaded; no graphics card here to draw it"
    return False, "map failed"


def smoke_test() -> None:
    exe = DIST / "WildLife.exe"
    with tempfile.TemporaryDirectory() as tmp:
        start = time.perf_counter()
        result = subprocess.run([str(exe), "--smoke-test", "--data-dir", tmp], timeout=60)
        elapsed = time.perf_counter() - start
        log = (Path(tmp) / "logs" / "wildlife.log").read_text(encoding="utf-8")
    ok, map_result = smoke_log_ok(result.returncode, log)
    print(
        f"Smoke test: {'PASS' if ok else 'FAIL'} (exit {result.returncode}, {elapsed:.1f} s, {map_result})"
    )
    if not ok:
        print(log[-2000:])
        tail = "\n".join(log.splitlines()[-10:])
        raise SystemExit(f"Smoke test FAILED (exit {result.returncode}). End of its log:\n{tail}")


def main() -> None:
    run_pyinstaller()
    saved = trim()
    print(f"Trimmed {saved / 1e6:.0f} MB. App folder: {size_of(DIST) / 1e6:.0f} MB at {DIST}")
    print(f"Third-party notices written ({notices.write(DIST)} licence files)")
    smoke_test()


if __name__ == "__main__":
    from ci_report import report_failures

    report_failures(main, "Building the app failed")
