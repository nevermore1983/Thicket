"""The map's bundled files and network rules (no browser needed)."""

import hashlib
import json
from importlib import resources

import pytest

from wildlife.domain import geo
from wildlife.ui.web.scheme import is_allowed

VENDOR = resources.files("wildlife.ui.web") / "assets" / "vendor" / "maplibre"


def test_bundled_maplibre_is_byte_for_byte_the_verified_release():
    info = json.loads((VENDOR / "VENDOR.json").read_text(encoding="utf-8"))
    assert info["version"] == "6.11.2"
    for name, expected in info["sha256"].items():
        assert hashlib.sha256((VENDOR / name).read_bytes()).hexdigest() == expected, name
    shipped = {f.name for f in VENDOR.iterdir()} - {"VENDOR.json"}
    assert shipped == set(info["sha256"]), "every bundled file must be listed with its hash"


@pytest.mark.parametrize(
    ("scheme", "host", "online", "allowed"),
    [
        ("wildlife", "app", False, True),
        ("data", "", False, True),
        ("https", "tiles.openfreemap.org", True, True),
        ("https", "tiles.openfreemap.org", False, False),  # online features switched off
        ("http", "tiles.openfreemap.org", True, False),  # never unencrypted
        ("https", "example.com", True, False),  # nowhere else, ever
        ("https", "tile.openstreetmap.org", True, False),  # bulk use is against its policy
        ("file", "", True, False),
    ],
)
def test_network_gate(scheme, host, online, allowed):
    assert is_allowed(scheme, host, online) is allowed


def test_page_files_exist():
    assets = resources.files("wildlife.ui.web") / "assets"
    for name in ("map.html", "map.js", "map.css", "uk-outline.geojson"):
        assert (assets / name).is_file(), name
    outline = json.loads((assets / "uk-outline.geojson").read_text(encoding="utf-8"))
    assert len(outline["features"]) >= 2


@pytest.mark.parametrize(
    ("zoom", "metres"), [(6, 10_000), (9, 2_500), (12, 250), (15, 25), (19, 5)]
)
def test_click_uncertainty_follows_zoom(zoom, metres):
    assert geo.click_uncertainty(51.5, zoom) == metres
