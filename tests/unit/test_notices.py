"""The packaged app must credit everything it bundles (scripts/notices.py)."""

import importlib.metadata as md
import re
import sys
from pathlib import Path

from packaging.requirements import Requirement

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "scripts"))

import notices  # noqa: E402


def _normal(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _runtime_packages(name: str, seen: set[str]) -> set[str]:
    """Every package `name` needs at run time, following their own requirements."""
    for line in md.requires(name) or []:
        requirement = Requirement(line)
        if requirement.marker and not requirement.marker.evaluate({"extra": ""}):
            continue  # an optional extra, or not for this Python / Windows
        dep = _normal(requirement.name)
        if dep not in seen:
            seen.add(dep)
            _runtime_packages(dep, seen)
    return seen


def test_every_bundled_package_is_credited():
    bundled = _runtime_packages("wildlife", set())
    assert bundled <= notices.PYTHON_PACKAGES, bundled - notices.PYTHON_PACKAGES


def test_notices_and_licence_texts_are_written(tmp_path):
    copied = notices.write(tmp_path)
    text = (tmp_path / "THIRD-PARTY-NOTICES.txt").read_text(encoding="utf-8")
    for c in notices.components():
        assert c.name in text
    assert copied >= 10
    lgpl = (tmp_path / "licenses" / "Qt" / "LGPL-3.0.txt").read_text(encoding="utf-8")
    assert "GNU LESSER GENERAL PUBLIC LICENSE" in lgpl and "Version 3" in lgpl
    gpl = (tmp_path / "licenses" / "Qt" / "GPL-3.0.txt").read_text(encoding="utf-8")
    assert gpl.lstrip().startswith("GNU GENERAL PUBLIC LICENSE")
    assert "END OF TERMS AND CONDITIONS" in gpl
    assert "Natural History Museum" in text  # the species list's required attribution
