"""Location maths: WGS84 lat/lon <-> British National Grid, parsing typed locations.

Everything here is pure Python (no Qt, no database), so it is easy to test.

Accuracy: the datum shift uses Ordnance Survey's published 7-parameter Helmert
transformation, which is good to a few metres across Great Britain. That is
far finer than the 10 m / 100 m grid squares used for wildlife records. (The
survey-grade alternative, OSTN15, needs a 15 MB grid file and isn't worth it
here; the spike in spikes/geo_accuracy measures the difference.)

References: "A guide to coordinate systems in Great Britain", Ordnance Survey.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Literal

# --- ellipsoids and the National Grid projection ---------------------------
_WGS84 = (6_378_137.000, 6_356_752.314245)
_AIRY1830 = (6_377_563.396, 6_356_256.909)
_F0 = 0.9996012717  # scale factor on the central meridian
_LAT0, _LON0 = math.radians(49), math.radians(-2)  # true origin
_E0, _N0 = 400_000.0, -100_000.0  # false origin

# WGS84 -> OSGB36 Helmert parameters (metres, ppm, arc-seconds)
_TX, _TY, _TZ = -446.448, 125.157, -542.060
_S = 20.4894e-6
_RX, _RY, _RZ = (math.radians(v / 3600) for v in (-0.1502, -0.2470, -0.8421))

_LETTERS = "ABCDEFGHJKLMNOPQRSTUVWXYZ"  # the grid alphabet skips I


# --- low-level conversions --------------------------------------------------
def _to_cartesian(
    lat: float, lon: float, ellipsoid: tuple[float, float]
) -> tuple[float, float, float]:
    a, b = ellipsoid
    e2 = 1 - (b * b) / (a * a)
    phi, lam = math.radians(lat), math.radians(lon)
    nu = a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
    return (
        nu * math.cos(phi) * math.cos(lam),
        nu * math.cos(phi) * math.sin(lam),
        (1 - e2) * nu * math.sin(phi),
    )


def _to_geodetic(
    x: float, y: float, z: float, ellipsoid: tuple[float, float]
) -> tuple[float, float]:
    a, b = ellipsoid
    e2 = 1 - (b * b) / (a * a)
    p = math.hypot(x, y)
    phi = math.atan2(z, p * (1 - e2))
    for _ in range(10):
        nu = a / math.sqrt(1 - e2 * math.sin(phi) ** 2)
        phi = math.atan2(z + e2 * nu * math.sin(phi), p)
    return math.degrees(phi), math.degrees(math.atan2(y, x))


def _helmert(x: float, y: float, z: float, sign: int) -> tuple[float, float, float]:
    """Apply the WGS84->OSGB36 shift (sign=+1) or its inverse (sign=-1)."""
    tx, ty, tz, s = sign * _TX, sign * _TY, sign * _TZ, sign * _S
    rx, ry, rz = sign * _RX, sign * _RY, sign * _RZ
    return (
        tx + (1 + s) * x - rz * y + ry * z,
        ty + rz * x + (1 + s) * y - rx * z,
        tz - ry * x + rx * y + (1 + s) * z,
    )


def _meridional_arc(phi: float) -> float:
    a, b = _AIRY1830
    n = (a - b) / (a + b)
    n2, n3 = n * n, n**3
    d, s = phi - _LAT0, phi + _LAT0
    return (
        b
        * _F0
        * (
            (1 + n + 1.25 * n2 + 1.25 * n3) * d
            - (3 * n + 3 * n2 + 2.625 * n3) * math.sin(d) * math.cos(s)
            + (1.875 * n2 + 1.875 * n3) * math.sin(2 * d) * math.cos(2 * s)
            - (35 / 24) * n3 * math.sin(3 * d) * math.cos(3 * s)
        )
    )


def _radii(phi: float) -> tuple[float, float, float]:
    a, b = _AIRY1830
    e2 = 1 - (b * b) / (a * a)
    sin2 = math.sin(phi) ** 2
    nu = a * _F0 / math.sqrt(1 - e2 * sin2)
    rho = a * _F0 * (1 - e2) / (1 - e2 * sin2) ** 1.5
    return nu, rho, nu / rho - 1


def osgb36_latlon_to_grid(lat: float, lon: float) -> tuple[float, float]:
    """Transverse Mercator: OSGB36 lat/lon (degrees) -> easting, northing (metres)."""
    phi, lam = math.radians(lat), math.radians(lon)
    nu, rho, eta2 = _radii(phi)
    sin, cos, tan = math.sin(phi), math.cos(phi), math.tan(phi)
    m = _meridional_arc(phi)
    i = m + _N0
    ii = nu / 2 * sin * cos
    iii = nu / 24 * sin * cos**3 * (5 - tan**2 + 9 * eta2)
    iiia = nu / 720 * sin * cos**5 * (61 - 58 * tan**2 + tan**4)
    iv = nu * cos
    v = nu / 6 * cos**3 * (nu / rho - tan**2)
    vi = nu / 120 * cos**5 * (5 - 18 * tan**2 + tan**4 + 14 * eta2 - 58 * tan**2 * eta2)
    dl = lam - _LON0
    northing = i + ii * dl**2 + iii * dl**4 + iiia * dl**6
    easting = _E0 + iv * dl + v * dl**3 + vi * dl**5
    return easting, northing


def grid_to_osgb36_latlon(easting: float, northing: float) -> tuple[float, float]:
    """Inverse Transverse Mercator: easting, northing -> OSGB36 lat/lon (degrees)."""
    a, _ = _AIRY1830
    phi = (northing - _N0) / (a * _F0) + _LAT0
    m = _meridional_arc(phi)
    while abs(northing - _N0 - m) >= 0.00001:  # iterate to 0.01 mm
        phi += (northing - _N0 - m) / (a * _F0)
        m = _meridional_arc(phi)
    nu, rho, eta2 = _radii(phi)
    tan, sec = math.tan(phi), 1 / math.cos(phi)
    vii = tan / (2 * rho * nu)
    viii = tan / (24 * rho * nu**3) * (5 + 3 * tan**2 + eta2 - 9 * tan**2 * eta2)
    ix = tan / (720 * rho * nu**5) * (61 + 90 * tan**2 + 45 * tan**4)
    x = sec / nu
    xi = sec / (6 * nu**3) * (nu / rho + 2 * tan**2)
    xii = sec / (120 * nu**5) * (5 + 28 * tan**2 + 24 * tan**4)
    xiia = sec / (5040 * nu**7) * (61 + 662 * tan**2 + 1320 * tan**4 + 720 * tan**6)
    de = easting - _E0
    lat = phi - vii * de**2 + viii * de**4 - ix * de**6
    lon = _LON0 + x * de - xi * de**3 + xii * de**5 - xiia * de**7
    return math.degrees(lat), math.degrees(lon)


# --- public API -------------------------------------------------------------
def wgs84_to_grid(lat: float, lon: float) -> tuple[float, float]:
    """WGS84 lat/lon (as used by GPS and maps) -> National Grid easting/northing."""
    x, y, z = _helmert(*_to_cartesian(lat, lon, _WGS84), sign=+1)
    return osgb36_latlon_to_grid(*_to_geodetic(x, y, z, _AIRY1830))


def grid_to_wgs84(easting: float, northing: float) -> tuple[float, float]:
    """National Grid easting/northing -> WGS84 lat/lon."""
    lat, lon = grid_to_osgb36_latlon(easting, northing)
    x, y, z = _helmert(*_to_cartesian(lat, lon, _AIRY1830), sign=-1)
    return _to_geodetic(x, y, z, _WGS84)


def is_northern_ireland(lat: float, lon: float) -> bool:
    """Rough box for Northern Ireland, which uses the Irish Grid instead."""
    return 54.0 <= lat <= 55.35 and -8.2 <= lon <= -5.4


def in_gb_grid(lat: float, lon: float) -> bool:
    """True where a British National Grid reference makes sense."""
    if not (49.7 <= lat <= 61.0 and -8.9 <= lon <= 2.0) or is_northern_ireland(lat, lon):
        return False
    easting, northing = wgs84_to_grid(lat, lon)
    return 0 <= easting < 700_000 and 0 <= northing < 1_300_000


def digits_for_uncertainty(uncertainty_m: float | None) -> int:
    """How many figures a grid reference should have for this uncertainty."""
    if uncertainty_m is None or uncertainty_m <= 10:
        return 8  # 10 m square
    if uncertainty_m <= 100:
        return 6
    if uncertainty_m <= 1000:
        return 4
    return 2


def format_grid_ref(easting: float, northing: float, digits: int = 6, spaced: bool = True) -> str:
    """Easting/northing -> 'TQ 308 808'. digits is the total of numeric figures (2-10)."""
    if digits not in (2, 4, 6, 8, 10):
        raise ValueError("digits must be 2, 4, 6, 8 or 10")
    e100k, n100k = int(easting // 100_000), int(northing // 100_000)
    if not (0 <= e100k <= 6 and 0 <= n100k <= 12):
        raise ValueError("position is outside the British National Grid")
    first = (19 - n100k) - (19 - n100k) % 5 + (e100k + 10) // 5
    second = (19 - n100k) * 5 % 25 + e100k % 5
    letters = _LETTERS[first] + _LETTERS[second]
    half = digits // 2
    e = int(easting % 100_000) // 10 ** (5 - half)
    n = int(northing % 100_000) // 10 ** (5 - half)
    sep = " " if spaced else ""
    return f"{letters}{sep}{e:0{half}d}{sep}{n:0{half}d}"


def grid_ref_for(lat: float, lon: float, uncertainty_m: float | None = None) -> str | None:
    """WGS84 lat/lon -> grid reference sized to the uncertainty, or None outside GB."""
    if not in_gb_grid(lat, lon):
        return None
    return format_grid_ref(*wgs84_to_grid(lat, lon), digits_for_uncertainty(uncertainty_m))


@dataclass(frozen=True, slots=True)
class GridSquare:
    """A parsed grid reference: the square's centre and its size."""

    easting: float
    northing: float
    size_m: int


_GRID_RE = re.compile(r"^\s*([A-HJ-Z]{2})\s*(\d+)\s*(\d*)\s*$", re.IGNORECASE)


def parse_grid_ref(text: str) -> GridSquare | None:
    """'TQ 308 808' / 'tq308808' / 'TQ 30 80' -> centre of that square, or None."""
    match = _GRID_RE.match(text)
    if not match:
        return None
    letters, digits = match[1].upper(), match[2] + match[3]
    if len(digits) % 2 or not 2 <= len(digits) <= 10:
        return None
    first, second = _LETTERS.index(letters[0]), _LETTERS.index(letters[1])
    e100k = ((first - 2) % 5) * 5 + second % 5
    n100k = (19 - (first // 5) * 5) - second // 5
    if not (0 <= e100k <= 6 and 0 <= n100k <= 12):
        return None
    half = len(digits) // 2
    size = 10 ** (5 - half)
    easting = e100k * 100_000 + int(digits[:half]) * size + size / 2
    northing = n100k * 100_000 + int(digits[half:]) * size + size / 2
    return GridSquare(easting, northing, size)


# --- parsing whatever the user typed or pasted ------------------------------
Method = Literal["grid_ref", "typed", "link"]


@dataclass(frozen=True, slots=True)
class ParsedLocation:
    latitude: float
    longitude: float
    uncertainty_m: int
    method: Method
    looks_swapped: bool = False  # e.g. "-0.12, 51.5" typed the wrong way round


_DEC = r"[-+]?\d{1,3}(?:\.\d+)?"
_PAIR_RE = re.compile(rf"^\s*({_DEC})\s*[,;\s]\s*({_DEC})\s*$")
_LINK_RES = (
    re.compile(rf"@({_DEC}),({_DEC})"),  # Google Maps .../@51.5,-0.12,15z
    re.compile(rf"[?&](?:q|query|ll)=({_DEC}),({_DEC})"),  # ?q=51.5,-0.12
    re.compile(rf"#map=\d+(?:\.\d+)?/({_DEC})/({_DEC})"),  # OpenStreetMap #map=15/51.5/-0.12
)
_DMS_RE = re.compile(
    r"(\d{1,3})[°\s]+(\d{1,2})['′\s]+(\d{1,2}(?:\.\d+)?)[\"″]?\s*([NSEW])",
    re.IGNORECASE,
)


def _uncertainty_from_decimals(text: str) -> int:
    decimals = len(text.split(".")[1]) if "." in text else 0
    return {0: 100_000, 1: 10_000, 2: 1_000, 3: 100, 4: 10}.get(decimals, 1)


def _valid(lat: float, lon: float) -> bool:
    return -90 <= lat <= 90 and -180 <= lon <= 180


def parse_location(text: str) -> ParsedLocation | None:
    """Understand a grid reference, decimal pair, degrees-minutes-seconds or map link."""
    text = text.strip()
    if not text:
        return None
    if square := parse_grid_ref(text):
        lat, lon = grid_to_wgs84(square.easting, square.northing)
        return ParsedLocation(lat, lon, square.size_m, "grid_ref")
    for pattern in _LINK_RES:
        if m := pattern.search(text):
            lat, lon = float(m[1]), float(m[2])
            if _valid(lat, lon):
                return ParsedLocation(lat, lon, 10, "link")
    if m := _PAIR_RE.match(text):
        lat, lon = float(m[1]), float(m[2])
        if _valid(lat, lon):
            unc = max(_uncertainty_from_decimals(m[1]), _uncertainty_from_decimals(m[2]))
            # UK latitudes are ~50-61; UK longitudes are ~-9..2. Spot the classic swap.
            swapped = abs(lat) < 10 and 49 <= abs(lon) <= 61
            return ParsedLocation(lat, lon, unc, "typed", looks_swapped=swapped)
    dms = _DMS_RE.findall(text)
    if len(dms) == 2:
        values = {}
        for deg, minutes, seconds, hemi in dms:
            value = int(deg) + int(minutes) / 60 + float(seconds) / 3600
            hemi = hemi.upper()
            values["lat" if hemi in "NS" else "lon"] = -value if hemi in "SW" else value
        if len(values) == 2 and _valid(values["lat"], values["lon"]):
            return ParsedLocation(values["lat"], values["lon"], 30, "typed")
    return None


def distance_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle distance in metres (haversine; plenty accurate for 'is it near?')."""
    r = 6_371_008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))
