"""Links for reporting a problem or suggesting an idea: GitHub's issue forms
(.github/ISSUE_TEMPLATE), with Thicket's and Windows' versions filled in.

Thicket itself sends nothing: the link opens in your browser, and you see the whole
form (and can change anything) before you press Submit there.
"""

from __future__ import annotations

import platform
from urllib.parse import urlencode

from wildlife import __version__

ISSUES = "https://github.com/nevermore1983/Thicket/issues/new"
FORMS = {"problem": "problem.yml", "idea": "idea.yml"}


def windows_version() -> str:
    """'Windows 11 (10.0.26100)': enough to reproduce a problem, nothing about you."""
    release, build = platform.release(), platform.version()
    if platform.system() != "Windows":
        return f"{platform.system()} {release}"
    if release == "10" and build.count(".") >= 2 and int(build.split(".")[2]) >= 22000:
        release = "11"  # Windows 11 still calls itself 10; its builds start at 22000
    return f"Windows {release} ({build})"


def form_url(kind: str) -> str:
    """The issue form for 'problem' or 'idea', with the versions filled in."""
    fields = {"template": FORMS[kind], "version": __version__}
    if kind == "problem":
        fields["windows"] = windows_version()
    return f"{ISSUES}?{urlencode(fields)}"
