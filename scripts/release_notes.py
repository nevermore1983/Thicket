"""The notes for a version's download page on GitHub, from CHANGELOG.md.

    uv run python scripts/release_notes.py 1.0.3 <installer SHA-256> [notes.md]

Used by .github/workflows/release.yml. tests/unit/test_release_notes.py checks the
current version has an entry, so a release can't go out without one.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO = "https://github.com/nevermore1983/Thicket"


def changes(version: str, changelog: Path = ROOT / "CHANGELOG.md") -> str:
    """The text under '## <version>' in the changelog."""
    text = changelog.read_text(encoding="utf-8")
    found = re.search(rf"^## {re.escape(version)}\s*$(.*?)(?=^## |\Z)", text, re.M | re.S)
    if not found or not found.group(1).strip():
        raise SystemExit(f"CHANGELOG.md has no notes for version {version}")
    return found.group(1).strip()


def notes(version: str, sha256: str) -> str:
    return f"""{changes(version)}

## Installing

1. Download **Thicket-Setup-{version}.exe** below. (**Thicket-Setup.exe** is the same file, under a name that never changes.)
2. Run it. It installs for your Windows account only, with no administrator password, and adds Thicket to the Start menu.
3. Already have Thicket? Running it upgrades your copy. Your sightings, photos and settings are kept.

**"Windows protected your PC"**: Windows shows this for programs downloaded from the internet that aren't signed with a paid certificate. Click **More info**, then **Run anyway**. ([Why?]({REPO}/blob/main/docs/14-packaging.md#4-windows-protected-your-pc))

Needs Windows 10 or 11 (64-bit). Your data stays on your PC in `%LOCALAPPDATA%\\WildLife`; uninstalling never removes it.

SHA-256 of the installer: `{sha256}`

Built from this version's source by GitHub Actions, after all the tests and the install, upgrade and uninstall check passed.
"""


if __name__ == "__main__":
    text = notes(sys.argv[1], sys.argv[2])
    if len(sys.argv) > 3:  # written as UTF-8 directly: no console encoding in the way
        Path(sys.argv[3]).write_text(text, encoding="utf-8")
    else:
        print(text)
