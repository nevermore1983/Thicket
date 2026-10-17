"""Turn failed tests into GitHub annotations: short notes on the Actions run's page.

    uv run python scripts/ci_report.py test-results.xml

GitHub only shows a run's full log to people signed in to GitHub. Its annotations are
public, so a failed release can be understood (and fixed) from the notes alone.
Used by .github/workflows/release.yml when a step fails.
"""

from __future__ import annotations

import os
import re
import sys
import traceback
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path

MAX_NOTES = 20  # GitHub shows up to 10 per step; the rest go to the log
MAX_TEXT = 900
ANSI = re.compile(r"(\x1b|#x1B)\[[0-9;]*m")  # terminal colours, if any slipped through


def failures(results: Path) -> list[tuple[str, str]]:
    """(test name, what went wrong) for every failed or broken test."""
    out = []
    for case in ET.parse(results).getroot().iter("testcase"):
        for problem in (*case.findall("failure"), *case.findall("error")):
            name = f"{case.get('classname', '')}.{case.get('name', '')}".strip(".")
            detail = (problem.get("message") or "") + "\n" + (problem.text or "")
            out.append((name, detail.strip()))
    return out


def annotation(name: str, detail: str) -> str:
    """One workflow command. GitHub needs %, CR and LF escaped in its text."""
    lines = [ANSI.sub("", line) for line in detail.splitlines() if line.strip()]
    # pytest marks what went wrong with "E "; the last line says where it happened
    wrong = [line for line in lines if line.lstrip().startswith("E ")]
    shown = wrong[:10] or lines[-10:]
    if lines and lines[-1] not in shown:
        shown.append(lines[-1])
    text = "\n".join(shown)[-MAX_TEXT:]
    text = text.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")
    title = name.replace("%", "%25").replace(":", "-").replace(",", " ")
    return f"::error title={title}::{text}"


def note(title: str, text: str) -> None:
    """Post a public note on the GitHub Actions run (does nothing anywhere else)."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        print(annotation(title, text), flush=True)


def report_failures(main: Callable[[], None], title: str) -> None:
    """Run a build script's main(); if it fails, say why in a public note too."""
    try:
        main()
    except SystemExit as exc:
        if exc.code not in (0, None):
            note(title, "\n".join(f"E {line}" for line in str(exc.code).splitlines()))
        raise
    except BaseException:
        note(title, "\n".join(f"E {line}" for line in traceback.format_exc().splitlines()[-12:]))
        raise


def main() -> None:
    results = Path(sys.argv[1])
    if not results.exists():
        print("::error title=No test results::The tests didn't get far enough to report")
        return
    found = failures(results)
    for name, detail in found[:MAX_NOTES]:
        print(annotation(name, detail))
    print(f"{len(found)} test(s) failed")


if __name__ == "__main__":
    main()
