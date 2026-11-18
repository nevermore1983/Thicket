"""Where you record: the regions Thicket knows (docs/16-regions-plan.md for the US,
docs/23-europe-packs-plan.md for Europe).

'uk' (the built-in UK list), European countries by their international code ('fr',
'de', ...), and the US states and DC ('us-oh', ...). Each has where the map opens when
there's nothing else to go on (an approximate centre and a zoom that shows most of it).
The species pack builder uses the same lists (scripts/build_species_packs.py).
"""

from __future__ import annotations

from dataclasses import dataclass

UK = "uk"
UK_GROUP, EUROPE, US = "United Kingdom", "Europe", "United States"


@dataclass(frozen=True, slots=True)
class Region:
    code: str  # 'uk', 'fr', 'us-oh'
    name: str  # 'United Kingdom', 'France', 'Ohio'
    lat: float
    lon: float
    zoom: float
    group: str = UK_GROUP  # UK_GROUP, EUROPE or US: how the region lists are arranged
    languages: tuple[str, ...] = ()  # its languages' codes, for local species names

    @property
    def is_uk(self) -> bool:
        return self.code == UK

    @property
    def month_first(self) -> bool:
        """Dates written with numbers put the month first (US: 3/5 is 5 March). The UK
        and the rest of Europe put the day first."""
        return self.group == US

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

# name, country code (as GBIF uses it), centre (lat, lon), zoom, languages
_COUNTRIES = (
    ("Albania", "AL", 41.15, 20.17, 7.0, ("sq",)),
    ("Andorra", "AD", 42.55, 1.58, 10.5, ("ca",)),
    ("Austria", "AT", 47.6, 14.1, 6.6, ("de",)),
    ("Belarus", "BY", 53.7, 28.0, 5.8, ("be", "ru")),
    ("Belgium", "BE", 50.6, 4.6, 7.3, ("fr", "nl", "de")),
    ("Bosnia and Herzegovina", "BA", 44.2, 17.8, 6.9, ("bs", "hr", "sr")),
    ("Bulgaria", "BG", 42.7, 25.4, 6.6, ("bg",)),
    ("Croatia", "HR", 44.7, 16.0, 6.5, ("hr",)),
    ("Cyprus", "CY", 35.0, 33.2, 8.0, ("el", "tr")),
    ("Czechia", "CZ", 49.8, 15.5, 6.8, ("cs",)),
    ("Denmark", "DK", 56.0, 10.4, 6.4, ("da",)),
    ("Estonia", "EE", 58.7, 25.0, 6.8, ("et",)),
    ("Faroe Islands", "FO", 62.0, -6.9, 8.0, ("fo", "da")),
    ("Finland", "FI", 64.5, 26.0, 4.8, ("fi", "sv")),
    ("France", "FR", 46.6, 2.4, 5.2, ("fr",)),
    ("Germany", "DE", 51.2, 10.4, 5.5, ("de",)),
    ("Gibraltar", "GI", 36.14, -5.35, 12.5, ()),
    ("Greece", "GR", 39.0, 22.9, 5.9, ("el",)),
    ("Hungary", "HU", 47.2, 19.4, 6.7, ("hu",)),
    ("Iceland", "IS", 64.9, -18.6, 5.8, ("is",)),
    ("Ireland", "IE", 53.4, -8.0, 6.3, ("ga",)),
    ("Italy", "IT", 42.5, 12.6, 5.2, ("it",)),
    ("Kosovo", "XK", 42.6, 20.9, 8.0, ("sq", "sr")),
    ("Latvia", "LV", 56.9, 24.6, 6.7, ("lv",)),
    ("Liechtenstein", "LI", 47.15, 9.55, 10.5, ("de",)),
    ("Lithuania", "LT", 55.2, 23.9, 6.7, ("lt",)),
    ("Luxembourg", "LU", 49.8, 6.1, 8.8, ("lb", "fr", "de")),
    ("Malta", "MT", 35.9, 14.4, 9.8, ("mt",)),
    ("Moldova", "MD", 47.2, 28.5, 7.0, ("ro",)),
    ("Monaco", "MC", 43.74, 7.42, 12.5, ("fr",)),
    ("Montenegro", "ME", 42.7, 19.3, 7.8, ("sr", "hr")),
    ("Netherlands", "NL", 52.2, 5.3, 6.8, ("nl",)),
    ("North Macedonia", "MK", 41.6, 21.7, 7.6, ("mk",)),
    ("Norway", "NO", 64.5, 13.0, 4.2, ("no", "nb", "nn")),
    ("Poland", "PL", 52.0, 19.4, 5.8, ("pl",)),
    ("Portugal", "PT", 39.6, -8.0, 6.2, ("pt",)),
    ("Romania", "RO", 45.9, 25.0, 6.0, ("ro",)),
    ("San Marino", "SM", 43.94, 12.46, 11.5, ("it",)),
    ("Serbia", "RS", 44.0, 20.9, 6.7, ("sr",)),
    ("Slovakia", "SK", 48.7, 19.7, 7.0, ("sk",)),
    ("Slovenia", "SI", 46.1, 14.9, 7.8, ("sl",)),
    ("Spain", "ES", 40.2, -3.6, 5.4, ("es", "ca", "eu", "gl")),
    ("Sweden", "SE", 62.5, 16.5, 4.4, ("sv",)),
    ("Switzerland", "CH", 46.8, 8.2, 7.2, ("de", "fr", "it")),
    ("Ukraine", "UA", 48.8, 31.4, 5.2, ("uk",)),
    ("Vatican City", "VA", 41.903, 12.453, 14.5, ("it",)),
)

REGIONS: dict[str, Region] = {
    UK: Region(UK, "United Kingdom", 54.4, -3.2, 4.6),
    **{
        code.lower(): Region(code.lower(), name, lat, lon, zoom, EUROPE, langs)
        for name, code, lat, lon, zoom, langs in _COUNTRIES
    },
    **{
        f"us-{code.lower()}": Region(f"us-{code.lower()}", name, lat, lon, zoom, US)
        for name, code, lat, lon, zoom in _STATES
    },
}
POSTAL_CODES = {name: code for name, code, *_ in _STATES}  # 'Ohio' -> 'OH'
COUNTRY_CODES = {name: code for name, code, *_ in _COUNTRIES}  # 'France' -> 'FR'


def region(code: str) -> Region:
    """The region with this code; an unknown one is treated as the UK."""
    return REGIONS.get(code, REGIONS[UK])


def group_of(code: str) -> str:
    """Europe, United States or United Kingdom; 'Elsewhere' for a pack from a region this
    version doesn't know yet."""
    found = REGIONS.get(code)
    return found.group if found else "Elsewhere"
