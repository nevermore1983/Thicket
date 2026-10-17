"""Build the WildLife installer, then check it really installs, upgrades and uninstalls.

    uv run --with "pyinstaller==6.22.3" python scripts/build_exe.py   (first)
    uv run python scripts/build_installer.py

Output: build/installer/WildLife-Setup-<version>.exe

The check uses a test copy of the installer with its own name and app ID, so it never
touches a real WildLife installation, and the installed app only ever runs on a
temporary data folder. It:
  1. installs an "old" version into a temporary folder;
  2. installs the current version over it (the upgrade) and checks stale files are gone;
  3. runs the installed app's smoke test, and checks it marks itself as running;
  4. uninstalls, and checks the program, its shortcut and its Windows entry are gone
     while the data folder, and your real data, are untouched.
Needs Inno Setup 7 (https://jrsoftware.org/isinfo.php).
"""

from __future__ import annotations

import argparse
import ctypes
import hashlib
import os
import shutil
import subprocess
import sys
import tempfile
import time
import winreg
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wildlife import __version__  # noqa: E402
from wildlife.app import RUNNING_MUTEX  # noqa: E402

APP_FOLDER = ROOT / "build" / "dist" / "WildLife"
OUTPUT = ROOT / "build" / "installer"
SCRIPT = ROOT / "packaging" / "installer.iss"
TEST_APP_ID = "{6F1D0C52-9B7E-4C61-A0E3-3C5D2A7B8E14}"  # as in installer.iss (TestBuild)
TEST_NAME = "WildLife installer test"
UNINSTALL_KEY = rf"Software\Microsoft\Windows\CurrentVersion\Uninstall\{TEST_APP_ID}_is1"


def find_iscc() -> Path:
    candidates = [
        os.environ.get("ISCC", ""),
        Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 7" / "ISCC.exe",
        Path(os.environ.get("PROGRAMFILES", "")) / "Inno Setup 7" / "ISCC.exe",
    ]
    for c in candidates:
        if c and Path(c).is_file():
            return Path(c)
    raise SystemExit("Inno Setup 7 not found. Install it, or set ISCC to ISCC.exe's path.")


def compile_installer(version: str, out: Path, test: bool = False) -> Path:
    if not (APP_FOLDER / "WildLife.exe").is_file():
        raise SystemExit("Build the app first: scripts/build_exe.py")
    if not (APP_FOLDER / "THIRD-PARTY-NOTICES.txt").is_file():
        raise SystemExit("The app folder has no third-party notices: rebuild it")
    defines = {
        "AppVersion": version,
        "AppFolder": str(APP_FOLDER),
        "OutputDir": str(out),
        "Compression": "lzma2/fast" if test else "lzma2/max",
    }
    cmd = [str(find_iscc()), "-q", *(f"-D{k}={v}" for k, v in defines.items())]
    if test:
        cmd.append("-DTestBuild")
    started = time.perf_counter()
    subprocess.run([*cmd, str(SCRIPT)], check=True)
    name = f"{'WildLife-InstallerTest' if test else 'WildLife'}-Setup-{version}.exe"
    setup = out / name
    print(
        f"Built {setup.name}: {setup.stat().st_size / 1e6:.0f} MB in {time.perf_counter() - started:.0f} s"
    )
    return setup


# ---- the check ----------------------------------------------------------------------
def check(work: Path) -> None:
    app, data = work / "app", work / "data"
    shortcut = (
        Path(os.environ["APPDATA"]) / "Microsoft" / "Windows" / "Start Menu" / "Programs"
    ) / f"{TEST_NAME}.lnk"
    if _registry() is not None:
        raise SystemExit("A previous installer test is still installed: uninstall it first")
    if _mutex_exists():
        raise SystemExit("Close WildLife first: the check starts and closes a copy of it")
    real_data = _fingerprint(Path(os.environ["LOCALAPPDATA"]) / "WildLife" / "wildlife.db")

    old = compile_installer("0.0.1", work / "setup", test=True)
    new = compile_installer(__version__, work / "setup", test=True)

    _install(old, f"/DIR={app}")
    _expect(_registry() == "0.0.1", "old version registered")
    _expect(shortcut.is_file(), "Start-menu shortcut made")
    stale = app / "_internal" / "left-over-from-the-old-version.dll"
    stale.write_bytes(b"old")

    _install(new)  # no /DIR: an upgrade must find the existing installation itself
    _expect(_registry() == __version__, f"upgraded to {__version__}")
    _expect((app / "WildLife.exe").is_file(), "upgrade went into the same folder")
    _expect(not stale.exists(), "files the new version doesn't need were removed")

    result = subprocess.run(
        [str(app / "WildLife.exe"), "--smoke-test", "--data-dir", str(data)], timeout=90
    )
    log = (data / "logs" / "wildlife.log").read_text(encoding="utf-8")
    _expect(result.returncode == 0 and "Smoke test OK" in log, "installed app works")
    _check_running_mark(app / "WildLife.exe", work / "data2")

    data_before = _fingerprint(data / "wildlife.db")
    _uninstall(app)
    _expect(_registry() is None, "removed from Windows' installed apps")
    _expect(not shortcut.exists(), "Start-menu shortcut removed")
    leftovers = [p for p in app.rglob("*")] if app.exists() else []
    _expect(not leftovers, f"program folder emptied ({len(leftovers)} left)")
    _expect(_fingerprint(data / "wildlife.db") == data_before, "data folder untouched")
    real_after = _fingerprint(Path(os.environ["LOCALAPPDATA"]) / "WildLife" / "wildlife.db")
    _expect(real_after == real_data, "your real data untouched")
    print("Installer check: PASS")


def _install(setup: Path, *extra: str) -> None:
    args = [str(setup), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", *extra]
    result = subprocess.run(args, timeout=600)
    _expect(result.returncode == 0, f"{setup.name} installed (exit {result.returncode})")


def _uninstall(app: Path) -> None:
    uninstaller = next(app.glob("unins*.exe"))
    subprocess.run(
        [str(uninstaller), "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"], timeout=300
    )
    # The uninstaller hands over to a copy of itself and returns early: wait for it
    for _ in range(120):
        if _registry() is None and not uninstaller.exists():
            return
        time.sleep(0.5)


def _check_running_mark(exe: Path, data: Path) -> None:
    """While WildLife is open, the mark the installer looks for (AppMutex) exists."""
    proc = subprocess.Popen([str(exe), "--data-dir", str(data)])
    try:
        seen = False
        for _ in range(60):
            if _mutex_exists():
                seen = True
                break
            time.sleep(0.5)
        _expect(seen, "a running WildLife is visible to the installer")
    finally:
        # Close it like the X button (WM_CLOSE), not a kill. A new data folder opens the
        # welcome dialog first, and a close request closes only that, so ask again.
        how = "had to be ended"
        for _ in range(3):
            subprocess.run(["taskkill", "/PID", str(proc.pid)], capture_output=True)
            try:
                proc.wait(timeout=10)
                how = "closed normally"
                break
            except subprocess.TimeoutExpired:
                pass
        if proc.poll() is None:
            proc.kill()
            proc.wait()
    _expect(not _mutex_exists(), f"the mark goes when WildLife closes ({how})")


def _mutex_exists() -> bool:
    synchronize = 0x00100000
    handle = ctypes.windll.kernel32.OpenMutexW(synchronize, False, RUNNING_MUTEX)
    if handle:
        ctypes.windll.kernel32.CloseHandle(handle)
    return bool(handle)


def _registry() -> str | None:
    """The installed test version, or None if it isn't installed."""
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, UNINSTALL_KEY) as key:
            return winreg.QueryValueEx(key, "DisplayVersion")[0]
    except FileNotFoundError:
        return None


def _fingerprint(path: Path) -> tuple | None:
    """Size, modified time and hash: read only, so checking never changes the file."""
    if not path.is_file():
        return None
    stat = path.stat()
    return stat.st_size, stat.st_mtime_ns, hashlib.sha256(path.read_bytes()).hexdigest()


def _expect(ok: bool, what: str) -> None:
    print(f"  {'ok  ' if ok else 'FAIL'} {what}")
    if not ok:
        raise SystemExit(f"Installer check FAILED: {what}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--no-check", action="store_true", help="build only, skip the check")
    args = parser.parse_args()
    compile_installer(__version__, OUTPUT)
    if not args.no_check:
        work = Path(tempfile.mkdtemp(prefix="wildlife-installer-"))
        try:
            check(work)
        finally:
            shutil.rmtree(work, ignore_errors=True)


if __name__ == "__main__":
    from ci_report import report_failures

    report_failures(main, "Building or checking the installer failed")
