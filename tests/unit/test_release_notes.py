"""Every version has notes for its download page (scripts/release_notes.py)."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import release_notes

from wildlife import __version__


def test_this_version_has_changelog_notes():
    """Bumping the version without writing what changed fails here, before a release."""
    assert release_notes.changes(__version__)


def test_the_notes_say_how_to_install_and_give_the_checksum():
    text = release_notes.notes(__version__, "ab" * 32)
    assert f"Thicket-Setup-{__version__}.exe" in text
    assert "More info" in text and "Run anyway" in text
    assert "ab" * 32 in text
    assert "## 1.0" not in text  # only this version's changes, not the whole changelog


def test_a_version_with_no_notes_is_refused(tmp_path):
    changelog = tmp_path / "CHANGELOG.md"
    changelog.write_text("# Changes\n\n## 9.9.9\n\n## 1.0.0\n\n- First\n", encoding="utf-8")
    assert release_notes.changes("1.0.0", changelog) == "- First"
    with pytest.raises(SystemExit):
        release_notes.changes("9.9.9", changelog)  # a heading with nothing under it
    with pytest.raises(SystemExit):
        release_notes.changes("2.0.0", changelog)
