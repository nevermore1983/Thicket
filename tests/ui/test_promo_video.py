"""scripts/promo_video.py films the website's tour by driving the real app, partly through
private parts (names starting with _). These tests fail when an app change removes one,
instead of the next re-film breaking months later."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

import promo_video

from wildlife.ui.calendar.month_view import MonthView


def test_the_video_script_can_still_drive_the_app(window):
    assert promo_video.missing_hooks(window) == []


def test_a_renamed_part_is_reported(window, monkeypatch):
    """The check itself works: take one part away and it's named."""
    monkeypatch.delattr(MonthView, "_cell_rect")
    missing = promo_video.missing_hooks(window)
    assert len(missing) == 1 and missing[0].startswith("calendar month_view._cell_rect()")
