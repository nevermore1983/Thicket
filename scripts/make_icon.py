"""Draw the Thicket app icon: the leaf from the app's own icon set, in white on the
app's green, at every size Windows asks for (title bar, taskbar, Start menu, Explorer).

    uv run python scripts/make_icon.py          # the app's icons and the website's
    uv run python scripts/make_icon.py --site   # only the website's

Writes src/wildlife/resources/icons/wildlife.ico (all sizes in one file, used by the
window, the .exe and the installer) and wildlife-256.png (for docs). For the website
(site/images): logo.svg (the header), favicon.svg and favicon.ico (browser tabs) and
apple-touch-icon.png (phones' home screens). Re-run it only if the design changes; the
output is committed, and tests/unit/test_site_icons.py checks the SVGs still match.
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

from PIL import Image
from PySide6.QtCore import QBuffer, QByteArray, QIODevice, QRectF, Qt
from PySide6.QtGui import QColor, QGuiApplication, QImage, QPainter, QPainterPath
from PySide6.QtSvg import QSvgRenderer

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from wildlife.ui.theme import icons  # noqa: E402
from wildlife.ui.theme.tokens import LIGHT  # noqa: E402

OUT = ROOT / "src" / "wildlife" / "resources" / "icons"
SITE = ROOT / "site" / "images"
SIZES = [16, 20, 24, 32, 40, 48, 64, 128, 256]
RADIUS = 0.22  # corner radius, as a share of the size
# (up to this size, margin as a share of the size, line width in the 24-unit icon grid)
STYLE = [(16, 0.08, 0), (24, 0.1, 0), (48, 0.14, 2.4), (256, 0.18, 2.0)]
LEAF, VEIN = (part.split('"')[1] for part in icons.PATHS["leaf"].split("<path")[1:])
SOLID_LEAF = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">'
    f'<path d="{LEAF}" fill="#ffffff" stroke="#ffffff" stroke-width="1.5" stroke-linejoin="round"/>'
    f'<path d="{VEIN}" fill="none" stroke="{{green}}" stroke-width="2.2" stroke-linecap="round"/>'
    "</svg>"
)


def draw(size: int, rounded: bool = True) -> Image.Image:
    """The icon at `size` pixels. rounded=False fills the whole square (for phones, which
    round the corners themselves)."""
    image = QImage(size, size, QImage.Format.Format_ARGB32)
    image.fill(Qt.GlobalColor.transparent)
    p = QPainter(image)
    p.setRenderHint(QPainter.RenderHint.Antialiasing)
    tile = QPainterPath()
    radius = size * RADIUS if rounded else 0
    tile.addRoundedRect(QRectF(0, 0, size, size), radius, radius)
    p.fillPath(tile, QColor(LIGHT.accent))
    # Small sizes get a bigger leaf (and a solid one), so it still reads at 16 px
    margin, stroke = next((m, s) for limit, m, s in STYLE if size <= limit)
    box = QRectF(size * margin, size * margin, size * (1 - 2 * margin), size * (1 - 2 * margin))
    if size <= 24:  # too small for outlines: a solid leaf with the vein cut out
        QSvgRenderer(QByteArray(SOLID_LEAF.format(green=LIGHT.accent).encode())).render(p, box)
    else:
        icons.render(p, "leaf", "#ffffff", box, stroke)
    p.end()
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "PNG")
    return Image.open(io.BytesIO(bytes(data))).convert("RGBA")


def svg(size: int) -> str:
    """The icon as an SVG, styled as draw() styles it at `size` pixels (the size it's
    mostly shown at), so the website's icons match the app's exactly."""
    margin, stroke = next((m, s) for limit, m, s in STYLE if size <= limit)
    offset, scale = round(24 * margin, 4), round(1 - 2 * margin, 4)
    if size <= 24:  # the solid leaf with the vein cut out, as in SOLID_LEAF
        leaf = (
            f'<path d="{LEAF}" fill="#ffffff" stroke="#ffffff" stroke-width="1.5" '
            f'stroke-linejoin="round"/><path d="{VEIN}" fill="none" stroke="{LIGHT.accent}" '
            'stroke-width="2.2" stroke-linecap="round"/>'
        )
    else:
        leaf = (
            f'<g fill="none" stroke="#ffffff" stroke-width="{stroke}" stroke-linecap="round" '
            f'stroke-linejoin="round">{icons.PATHS["leaf"]}</g>'
        )
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24">\n'
        f'  <rect width="24" height="24" rx="{round(24 * RADIUS, 4)}" fill="{LIGHT.accent}"/>\n'
        f'  <g transform="translate({offset} {offset}) scale({scale})">{leaf}</g>\n'
        "</svg>\n"
    )


def site() -> None:
    """The website's icons, in site/images."""
    (SITE / "logo.svg").write_text(svg(32), encoding="utf-8", newline="\n")  # header: 32 px
    (SITE / "favicon.svg").write_text(svg(16), encoding="utf-8", newline="\n")  # tab: 16 px
    tab = [draw(16), draw(32)]
    tab[1].save(SITE / "favicon.ico", sizes=[(16, 16), (32, 32)], append_images=tab[:1])
    draw(180, rounded=False).save(SITE / "apple-touch-icon.png", optimize=True)
    print("site/images: logo.svg, favicon.svg, favicon.ico, apple-touch-icon.png")


def main() -> None:
    QGuiApplication(sys.argv[:1])
    if "--site" not in sys.argv:
        OUT.mkdir(parents=True, exist_ok=True)
        images = [draw(s) for s in SIZES]
        largest = images[-1]
        largest.save(
            OUT / "wildlife.ico",
            sizes=[(s, s) for s in SIZES],
            append_images=images[:-1],  # each size drawn on its own, not shrunk from 256
        )
        largest.save(OUT / "wildlife-256.png")
        with Image.open(OUT / "wildlife.ico") as ico:
            print(f"wildlife.ico: {sorted(ico.info['sizes'])}")
    site()


if __name__ == "__main__":
    main()
