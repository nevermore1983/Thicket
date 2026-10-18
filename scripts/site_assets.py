"""Make the website's screenshots and font small (docs/17-website-plan.md).

    uv run python scripts/site_assets.py screenshots local_data/shots/add-light.png ...
    uv run --with fonttools --with brotli python scripts/site_assets.py font

screenshots: each PNG from scripts/screenshot.py becomes site/images/<name>.webp. App
screens stay pixel-perfect (lossless WebP). Photo-like ones, such as the map, are far
smaller as high-quality lossy WebP, so that's used when it saves at least a quarter.
dashboard-light.png also makes the 1200x630 picture shown when someone shares a link.

font: the app's italic font for scientific names, cut down to one weight (400) and the
characters the site needs: about 10 KB instead of 850 KB.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IMAGES = ROOT / "site" / "images"
FONT_SRC = ROOT / "src" / "wildlife" / "resources" / "fonts" / "SourceSerif4Variable-Italic.ttf"
FONT_OUT = ROOT / "site" / "fonts" / "SourceSerif4-Italic-400-latin.woff2"
# Basic Latin, plus × for hybrids, · and the typographic quotes and dashes
FONT_TEXT = "".join(chr(c) for c in range(0x20, 0x7F)) + "×·‘’“”–—"
SOCIAL = IMAGES / "social-card.png"
SOCIAL_SIZE = (1200, 630)


def webp(png: Path) -> Path:
    from PIL import Image

    image = Image.open(png).convert("RGB")
    lossless, lossy = io.BytesIO(), io.BytesIO()
    image.save(lossless, "WEBP", lossless=True, method=6)
    image.save(lossy, "WEBP", quality=90, method=6)
    use_lossy = lossy.tell() < lossless.tell() * 0.75
    out = IMAGES / f"{png.stem}.webp"
    out.write_bytes((lossy if use_lossy else lossless).getvalue())
    kind = "lossy, quality 90" if use_lossy else "lossless"
    print(f"{out.relative_to(ROOT)}: {out.stat().st_size // 1024} KB ({kind})")
    return out


def social_card(png: Path) -> None:
    """The top of the dashboard, at the size link previews use."""
    from PIL import Image

    image = Image.open(png).convert("RGB")
    width = image.width
    height = round(width * SOCIAL_SIZE[1] / SOCIAL_SIZE[0])
    card = image.crop((0, 0, width, height)).resize(SOCIAL_SIZE, Image.Resampling.LANCZOS)
    card.save(SOCIAL, optimize=True)
    print(f"{SOCIAL.relative_to(ROOT)}: {SOCIAL.stat().st_size // 1024} KB")


def screenshots(paths: list[Path]) -> None:
    for png in paths:
        webp(png)
        if png.name == "dashboard-light.png":
            social_card(png)


def font() -> None:
    from fontTools import subset
    from fontTools.ttLib import TTFont
    from fontTools.varLib import instancer

    # Pin both axes (weight, optical size) at their defaults' look: one static italic
    static = instancer.instantiateVariableFont(TTFont(FONT_SRC), {"wght": 400, "opsz": None})
    options = subset.Options()
    options.flavor = "woff2"
    options.layout_features = ["kern", "liga"]
    subsetter = subset.Subsetter(options)
    subsetter.populate(text=FONT_TEXT)
    subsetter.subset(static)
    static.flavor = "woff2"
    static.save(FONT_OUT)
    print(f"{FONT_OUT.relative_to(ROOT)}: {FONT_OUT.stat().st_size // 1024} KB")


if __name__ == "__main__":
    if sys.argv[1:2] == ["screenshots"] and len(sys.argv) > 2:
        screenshots([Path(p) for p in sys.argv[2:]])
    elif sys.argv[1:] == ["font"]:
        font()
    else:
        raise SystemExit(__doc__)
