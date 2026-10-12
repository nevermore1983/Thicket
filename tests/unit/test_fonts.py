"""The bundled font is the one recorded in VENDOR.json, and Qt can use it."""

import hashlib
import json
from pathlib import Path

FONTS = Path(__file__).parents[2] / "src" / "wildlife" / "resources" / "fonts"


def test_bundled_files_match_their_checksums():
    vendor = json.loads((FONTS / "VENDOR.json").read_text(encoding="utf-8"))
    for name, info in vendor["files"].items():
        data = (FONTS / name).read_bytes()
        assert hashlib.sha256(data).hexdigest() == info["sha256"], name
        blob = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
        assert blob == info["git_blob_sha1"], name  # the same file as in Adobe's repository


def test_scientific_names_use_the_bundled_font(qapp):
    from PySide6.QtGui import QFont, QFontInfo

    from wildlife.ui.theme.manager import load_bundled_fonts
    from wildlife.ui.theme.tokens import FONT_SCI

    assert FONT_SCI in load_bundled_fonts()
    font = QFont(FONT_SCI)
    font.setItalic(True)
    assert QFontInfo(font).family() == FONT_SCI  # not a fallback like Georgia
