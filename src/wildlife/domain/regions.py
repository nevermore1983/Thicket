"""Where you record: the regions WildLife knows (docs/16-regions-plan.md).

'uk' (the built-in UK list) and the US states and DC ('us-oh', ...), each with where the
map opens when there's nothing else to go on. The state centres are approximate
geographic centres; the zoom shows most of the state. The species pack builder uses the
same list (scripts/build_species_packs.py).
"""

from __future__ import annotations

from dataclasses import dataclass

UK = "uk"


@dataclass(frozen=True, slots=True)
class Region:
    code: str  # 'uk', 'us-oh'
    name: str  # 'United Kingdom', 'Ohio'
    lat: float
    lon: float
    zoom: float

    @property
    def is_uk(self) -> bool:
        return self.code == UK

    @property
    def month_first(self) -> bool:
        """Dates written with numbers put the month first (US: 3/5 is 5 March)."""
        return not self.is_uk

    @property
    def start_view(self) -> dict[str, float]:
        return {"lat": self.lat, "lon": self.lon, "zoom": self.zoom}


# name, postal code, centre (lat, lon), zoom
_STATES = (
    ("Alabama", "AL", 32.8, -86.8, 6.0), ("Alaska", "AK", 63.6, -152.5, 3.4),
    ("Arizona", "AZ", 34.3, -111.7, 5.6), ("Arkansas", "AR", 34.9, -92.4, 6.0),
    ("California", "CA", 37.2, -119.5, 5.0), ("Colorado", "CO", 39.0, -105.5, 5.8),
    ("Connecticut", "CT", 41.6, -72.7, 7.6), ("Delaware", "DE", 39.0, -75.5, 7.6),
    ("District of Columbia", "DC", 38.9, -77.03, 10.5), ("Florida", "FL", 28.6, -82.4, 5.6),
    ("Georgia", "GA", 32.7, -83.4, 6.0), ("Hawaii", "HI", 20.6, -157.5, 6.0),
    ("Idaho", "ID", 44.4, -114.6, 5.4), ("Illinois", "IL", 40.0, -89.2, 5.8),
    ("Indiana", "IN", 39.9, -86.3, 6.2), ("Iowa", "IA", 42.1, -93.5, 6.2),
    ("Kansas", "KS", 38.5, -98.4, 6.0), ("Kentucky", "KY", 37.5, -85.3, 6.2),
    ("Louisiana", "LA", 31.1, -92.0, 6.2), ("Maine", "ME", 45.4, -69.2, 6.0),
    ("Maryland", "MD", 39.0, -76.8, 7.0), ("Massachusetts", "MA", 42.3, -71.8, 7.2),
    ("Michigan", "MI", 44.3, -85.4, 5.6), ("Minnesota", "MN", 46.3, -94.3, 5.6),
    ("Mississippi", "MS", 32.7, -89.7, 6.0), ("Missouri", "MO", 38.4, -92.5, 6.0),
    ("Montana", "MT", 47.0, -109.6, 5.4), ("Nebraska", "NE", 41.5, -99.8, 5.8),
    ("Nevada", "NV", 39.3, -116.6, 5.4), ("New Hampshire", "NH", 43.7, -71.6, 6.8),
    ("New Jersey", "NJ", 40.2, -74.7, 7.0), ("New Mexico", "NM", 34.4, -106.1, 5.6),
    ("New York", "NY", 42.9, -75.5, 6.0), ("North Carolina", "NC", 35.6, -79.4, 6.0),
    ("North Dakota", "ND", 47.5, -100.5, 6.0), ("Ohio", "OH", 40.3, -82.8, 6.4),
    ("Oklahoma", "OK", 35.6, -97.5, 6.0), ("Oregon", "OR", 43.9, -120.6, 5.8),
    ("Pennsylvania", "PA", 40.9, -77.8, 6.4), ("Rhode Island", "RI", 41.7, -71.5, 8.4),
    ("South Carolina", "SC", 33.9, -80.9, 6.6), ("South Dakota", "SD", 44.4, -100.2, 6.0),
    ("Tennessee", "TN", 35.9, -86.4, 6.2), ("Texas", "TX", 31.5, -99.3, 5.0),
    ("Utah", "UT", 39.3, -111.7, 5.8), ("Vermont", "VT", 44.1, -72.7, 7.0),
    ("Virginia", "VA", 37.5, -78.8, 6.2), ("Washington", "WA", 47.4, -120.5, 6.0),
    ("West Virginia", "WV", 38.6, -80.6, 6.6), ("Wisconsin", "WI", 44.6, -89.9, 6.0),
    ("Wyoming", "WY", 43.0, -107.6, 5.8),
)  # fmt: skip

REGIONS: dict[str, Region] = {
    UK: Region(UK, "United Kingdom", 54.4, -3.2, 4.6),
    **{
        f"us-{code.lower()}": Region(f"us-{code.lower()}", name, lat, lon, zoom)
        for name, code, lat, lon, zoom in _STATES
    },
}
POSTAL_CODES = {name: code for name, code, *_ in _STATES}  # 'Ohio' -> 'OH'


def region(code: str) -> Region:
    """The region with this code; an unknown one is treated as the UK."""
    return REGIONS.get(code, REGIONS[UK])
