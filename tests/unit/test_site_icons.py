"""The website's icons are the app icon: scripts/make_icon.py --site draws both from one recipe."""

import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import make_icon


def test_the_website_logos_match_the_app_icon():
    """If the icon's design changes, re-run `uv run python scripts/make_icon.py`."""
    assert (make_icon.SITE / "logo.svg").read_text(encoding="utf-8") == make_icon.svg(32)
    assert (make_icon.SITE / "favicon.svg").read_text(encoding="utf-8") == make_icon.svg(16)


def test_the_phone_and_tab_icons_have_the_right_sizes():
    with Image.open(make_icon.SITE / "apple-touch-icon.png") as icon:
        assert icon.size == (180, 180)
        assert icon.getpixel((0, 0))[3] == 255  # square corners: phones round them themselves
    with Image.open(make_icon.SITE / "favicon.ico") as ico:
        assert sorted(ico.info["sizes"]) == [(16, 16), (32, 32)]
