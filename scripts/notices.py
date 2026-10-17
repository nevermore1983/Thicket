"""Third-party notices for the packaged app: what WildLife bundles, under which licence,
and the licence texts themselves. Used by build_exe.py; tests/unit/test_notices.py
checks every bundled Python package is listed here.

Output in the app folder:
    THIRD-PARTY-NOTICES.txt   one entry per component
    licenses/<component>/...  the full licence texts
"""

from __future__ import annotations

import importlib.metadata as md
import json
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "wildlife"
PACKAGING = ROOT / "packaging" / "licenses"


@dataclass(frozen=True)
class Component:
    name: str
    licence: str
    url: str
    files: list[Path] = field(default_factory=list)
    version: str = ""
    note: str = ""


def _dist_files(dist: str) -> list[Path]:
    """The licence files a package declares (its dist-info `licenses` folder, PEP 639)."""
    d = md.distribution(dist)
    found = [
        Path(d.locate_file(f))
        for f in d.files or []
        if f.parts[0].endswith(".dist-info") and "licenses" in f.parts
    ]
    if not found:
        raise FileNotFoundError(f"{dist} declares no licence files")
    return found


def _version(dist: str) -> str:
    return md.version(dist)


def _vendor_version(folder: Path, file: str | None = None) -> str:
    vendor = json.loads((folder / "VENDOR.json").read_text(encoding="utf-8"))
    return vendor["files"][file]["version"] if file else vendor["version"]


# Python packages that end up in the app folder, by their distribution name.
# (tests/unit/test_notices.py fails if a runtime dependency is missing from this list.)
PYTHON_PACKAGES = {
    "pyside6",
    "pyside6-essentials",
    "pyside6-addons",
    "pyside6-webengine",
    "pyside6-pdf",
    "shiboken6",
    "pillow",
    "pi-heif",
    "rawpy",
    "numpy",
}


def components() -> list[Component]:
    maplibre = SRC / "ui" / "web" / "assets" / "vendor" / "maplibre"
    fonts = SRC / "resources" / "fonts"
    catalogue = json.loads(
        (SRC / "resources" / "species" / "catalogue_info.json").read_text(encoding="utf-8")
    )
    lgpl = [PACKAGING / "LGPL-3.0.txt", PACKAGING / "GPL-3.0.txt"]
    return [
        Component(
            "Python",
            "PSF-2.0",
            "https://www.python.org/",
            [Path(sys.base_prefix) / "LICENSE.txt"],
            sys.version.split()[0],
        ),
        Component(
            "Qt, Qt for Python (PySide6) and Shiboken",
            "LGPL-3.0-only",
            "https://www.qt.io/qt-for-python",
            lgpl,
            _version("pyside6"),
            "WildLife uses Qt under the GNU LGPL version 3 (the texts are in licenses/). "
            "Qt's libraries are the separate files in _internal/PySide6 and can be replaced "
            "with your own builds of the same version. The source code is available from "
            "https://download.qt.io/official_releases/QtForPython/ and "
            "https://download.qt.io/official_releases/qt/. Qt WebEngine contains Chromium; "
            "its third-party licences are listed at "
            "https://doc.qt.io/qt-6/qtwebengine-licensing.html.",
        ),
        Component(
            "Pillow (with libjpeg-turbo, libpng, libwebp, zlib and others)",
            "MIT-CMU and the bundled libraries' licences",
            "https://python-pillow.org/",
            _dist_files("pillow"),
            _version("pillow"),
        ),
        Component(
            "pi-heif (with libheif and libde265)",
            "BSD-3-Clause; libheif and libde265 are LGPL-3.0",
            "https://github.com/bigcat88/pillow_heif",
            _dist_files("pi-heif") + lgpl,
            _version("pi-heif"),
            "libheif and libde265 are included as separate libraries, under the GNU LGPL v3. "
            "Source: https://github.com/strukturag/libheif and "
            "https://github.com/strukturag/libde265.",
        ),
        Component(
            "rawpy (with LibRaw)",
            "MIT; LibRaw is LGPL-2.1 or CDDL-1.0",
            "https://github.com/letmaik/rawpy",
            _dist_files("rawpy"),
            _version("rawpy"),
            "LibRaw source: https://www.libraw.org/",
        ),
        Component(
            "NumPy (with OpenBLAS, LAPACK and the GCC runtime)",
            "BSD-3-Clause and the bundled libraries' licences",
            "https://numpy.org/",
            _dist_files("numpy"),
            _version("numpy"),
        ),
        Component(
            "MapLibre GL JS",
            "BSD-3-Clause",
            "https://maplibre.org/",
            [maplibre / "LICENSE.txt"],
            _vendor_version(maplibre),
        ),
        Component(
            "Source Serif 4 (font)",
            "OFL-1.1",
            "https://github.com/adobe-fonts/source-serif",
            [fonts / "SourceSerif4-LICENSE.md"],
            _vendor_version(fonts, "SourceSerif4Variable-Italic.ttf"),
        ),
        Component(
            "UK Species Inventory (species names)",
            catalogue["licence"],
            catalogue["source_url"],
            [],
            catalogue["version"],
            catalogue["attribution"] + ". Names were reformatted for WildLife; no other "
            "changes. Licence: https://creativecommons.org/licenses/by/4.0/",
        ),
        Component(
            "PyInstaller bootloader",
            "GPL-2.0 with the PyInstaller bootloader exception",
            "https://pyinstaller.org/",
            [],
            "",
            "The exception allows the bootloader to start programs under any licence.",
        ),
    ]


def write(app_folder: Path) -> int:
    """Write THIRD-PARTY-NOTICES.txt and licenses/ into `app_folder`. Returns how many
    licence files were copied."""
    target = app_folder / "licenses"
    shutil.rmtree(target, ignore_errors=True)
    lines = [
        "WildLife: third-party notices",
        "=============================",
        "",
        "WildLife includes the components below. Their licence texts are in the "
        "'licenses' folder next to this file.",
        "",
        "Maps are loaded while online from OpenFreeMap (https://openfreemap.org/), using "
        "OpenStreetMap data (c) OpenStreetMap contributors (https://www.openstreetmap.org/copyright). "
        "Nothing from them is included in the app.",
        "",
    ]
    copied = 0
    for c in components():
        folder = target / _slug(c.name)
        lines += [
            "-" * 78,
            f"{c.name}{' ' + c.version if c.version else ''}",
            f"Licence: {c.licence}",
            f"Website: {c.url}",
        ]
        if c.note:
            lines.append(c.note)
        if c.files:
            lines.append(f"Licence texts: licenses/{folder.name}/")
        lines.append("")
        for path in c.files:
            if not path.is_file():
                raise FileNotFoundError(f"Licence file for {c.name} not found: {path}")
            dest = folder / _inside_licenses(path)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, dest)
            copied += 1
    (app_folder / "THIRD-PARTY-NOTICES.txt").write_text("\n".join(lines), encoding="utf-8")
    return copied


def _inside_licenses(path: Path) -> Path:
    """A package's licence file keeps the sub-folder it has under its `licenses` folder
    (NumPy has several LICENSE.md files, one per bundled library)."""
    parts = path.parts
    if "licenses" in parts:
        last = len(parts) - 1 - parts[::-1].index("licenses")
        return Path(*parts[last + 1 :])
    return Path(path.name)


def _slug(name: str) -> str:
    first = name.split(" (")[0].split(",")[0]
    return "".join(ch if ch.isalnum() else "-" for ch in first).strip("-")
