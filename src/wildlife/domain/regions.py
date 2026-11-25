"""Where you record: the regions Thicket knows (docs/16-regions-plan.md for the US,
docs/23-europe-packs-plan.md for Europe).

'uk' (the built-in UK list), European countries by their international code ('fr',
'de', ...), the US states and DC ('us-oh', ...), Canada's provinces and territories
('ca-on', ...), Australia's states and territories ('au-nsw', ...), New Zealand
('nz'; docs/24-canada-australia-nz-plan.md), and the countries and territories of Latin
America and the Caribbean, by their international code too ('br', 'cr', 'pr', ...;
docs/25-latin-america-caribbean-plan.md), and Africa's, the same way ('za', 'ke', 're',
...; docs/26-africa-plan.md), and the Middle East's and Asia's ('il', 'cn', 'jp', ...;
docs/28-asia-plan.md). Each has where the map opens when
there's nothing else to go on (an approximate centre and a zoom that shows most of it).
The species pack builder uses the same lists (scripts/build_species_packs.py).

Finding a region by typing (docs/27-find-your-region-plan.md): accents, apostrophes and
"St" don't matter, and a few other names people use ("Ivory Coast") find it too.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

UK = "uk"
UK_GROUP, EUROPE, US = "United Kingdom", "Europe", "United States"
CANADA, AUSTRALIA, NEW_ZEALAND = "Canada", "Australia", "New Zealand"
LATIN_AMERICA = "Latin America and the Caribbean"
AFRICA = "Africa"
MIDDLE_EAST, ASIA = "Middle East", "Asia"
# How the region lists are arranged (a region this version doesn't know comes last)
GROUPS = (EUROPE, US, CANADA, AUSTRALIA, NEW_ZEALAND, LATIN_AMERICA, AFRICA, MIDDLE_EAST, ASIA)
# Outside the US group but writing dates the US way: Puerto Rico, the US Virgin Islands,
# and the Philippines (docs/28)
MONTH_FIRST_TOO = frozenset({"pr", "vi", "ph"})


@dataclass(frozen=True, slots=True)
class Region:
    code: str  # 'uk', 'fr', 'us-oh'
    name: str  # 'United Kingdom', 'France', 'Ohio'
    lat: float
    lon: float
    zoom: float
    group: str = UK_GROUP  # UK_GROUP or one of GROUPS: how the region lists are arranged
    languages: tuple[str, ...] = ()  # its languages' codes, for local species names

    @property
    def is_uk(self) -> bool:
        return self.code == UK

    @property
    def month_first(self) -> bool:
        """Dates written with numbers put the month first (US: 3/5 is 5 March; Canada
        uses both, and month first is the more common; Puerto Rico, the US Virgin
        Islands and the Philippines do too). The UK, the rest of Europe, Australia, New
        Zealand, Latin America, Africa and the Middle East put the day first; East Asia
        writes the year first, which is read the same either way."""
        return self.group in (US, CANADA) or self.code in MONTH_FIRST_TOO

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

# name, country code (as GBIF uses it; RU-EU is Russia west of the Urals), centre (lat,
# lon), zoom, languages. Russia, Turkey and the Caucasus came in version 1.6.1.
_COUNTRIES = (
    ("Albania", "AL", 41.15, 20.17, 7.0, ("sq",)),
    ("Andorra", "AD", 42.55, 1.58, 10.5, ("ca",)),
    ("Armenia", "AM", 40.2, 45.0, 7.6, ("hy",)),
    ("Austria", "AT", 47.6, 14.1, 6.6, ("de",)),
    ("Azerbaijan", "AZ", 40.3, 47.7, 6.8, ("az",)),
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
    ("European Russia", "RU-EU", 55.8, 42.0, 4.2, ("ru",)),  # west of the Urals (60°E)
    ("Finland", "FI", 64.5, 26.0, 4.8, ("fi", "sv")),
    ("France", "FR", 46.6, 2.4, 5.2, ("fr",)),
    ("Georgia", "GE", 42.3, 43.4, 6.8, ("ka",)),
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
    ("Russia (all)", "RU", 62.0, 95.0, 3.0, ("ru",)),
    ("San Marino", "SM", 43.94, 12.46, 11.5, ("it",)),
    ("Serbia", "RS", 44.0, 20.9, 6.7, ("sr",)),
    ("Slovakia", "SK", 48.7, 19.7, 7.0, ("sk",)),
    ("Slovenia", "SI", 46.1, 14.9, 7.8, ("sl",)),
    ("Spain", "ES", 40.2, -3.6, 5.4, ("es", "ca", "eu", "gl")),
    ("Sweden", "SE", 62.5, 16.5, 4.4, ("sv",)),
    ("Switzerland", "CH", 46.8, 8.2, 7.2, ("de", "fr", "it")),
    ("Turkey", "TR", 39.0, 35.2, 5.6, ("tr",)),
    ("Ukraine", "UA", 48.8, 31.4, 5.2, ("uk",)),
    ("Vatican City", "VA", 41.903, 12.453, 14.5, ("it",)),
)

# Canada: name, Canada Post code, centre, zoom, languages (French is searchable where
# it's an official language of the province)
_PROVINCES = (
    ("Alberta", "AB", 55.0, -115.0, 4.6, ()),
    ("British Columbia", "BC", 54.0, -125.0, 4.2, ()),
    ("Manitoba", "MB", 55.0, -97.5, 4.4, ()),
    ("New Brunswick", "NB", 46.5, -66.2, 6.4, ("fr",)),
    ("Newfoundland and Labrador", "NL", 52.5, -60.0, 4.4, ()),
    ("Northwest Territories", "NT", 64.8, -119.0, 3.6, ()),
    ("Nova Scotia", "NS", 45.0, -63.0, 6.2, ()),
    ("Nunavut", "NU", 68.0, -90.0, 3.0, ()),
    ("Ontario", "ON", 50.0, -85.0, 4.2, ()),
    ("Prince Edward Island", "PE", 46.4, -63.2, 8.0, ()),
    ("Quebec", "QC", 52.5, -71.5, 3.9, ("fr",)),
    ("Saskatchewan", "SK", 54.5, -105.9, 4.4, ()),
    ("Yukon", "YT", 64.0, -135.5, 4.4, ()),
)
# Australia: name, abbreviation, centre, zoom
_AU_STATES = (
    ("Australian Capital Territory", "ACT", -35.5, 149.0, 8.6),
    ("New South Wales", "NSW", -32.5, 147.0, 5.2),  # with Jervis Bay Territory
    ("Northern Territory", "NT", -19.5, 133.5, 4.6),
    ("Queensland", "QLD", -21.5, 145.0, 4.4),
    ("South Australia", "SA", -30.5, 135.5, 4.6),
    ("Tasmania", "TAS", -42.0, 146.6, 6.4),
    ("Victoria", "VIC", -36.9, 144.3, 6.0),
    ("Western Australia", "WA", -25.5, 121.5, 4.2),
)
NZ = "nz"

# Latin America and the Caribbean: name, country code (as GBIF uses it), centre (lat,
# lon), zoom, languages. The French, Dutch, British and US territories have their own
# codes in GBIF, so their own packs. The Caribbean Netherlands' map opens on Bonaire.
_LATIN_AMERICA = (
    ("Anguilla", "AI", 18.22, -63.05, 11.0, ()),
    ("Antigua and Barbuda", "AG", 17.35, -61.8, 9.6, ()),
    ("Argentina", "AR", -38.4, -63.6, 3.8, ("es",)),
    ("Aruba", "AW", 12.52, -69.97, 11.0, ("nl",)),
    ("Bahamas", "BS", 24.3, -76.6, 6.0, ()),
    ("Barbados", "BB", 13.19, -59.54, 11.0, ()),
    ("Belize", "BZ", 17.2, -88.7, 7.6, ()),
    ("Bermuda", "BM", 32.31, -64.77, 11.0, ()),
    ("Bolivia", "BO", -16.3, -64.6, 5.4, ("es",)),
    ("Brazil", "BR", -14.2, -51.9, 3.8, ("pt",)),
    ("British Virgin Islands", "VG", 18.45, -64.55, 10.2, ()),
    ("Caribbean Netherlands", "BQ", 12.18, -68.26, 9.4, ("nl",)),
    ("Cayman Islands", "KY", 19.4, -80.9, 8.4, ()),
    ("Chile", "CL", -35.7, -71.5, 3.8, ("es",)),
    ("Colombia", "CO", 4.1, -73.1, 5.0, ("es",)),
    ("Costa Rica", "CR", 9.8, -84.2, 7.2, ("es",)),
    ("Cuba", "CU", 21.6, -79.5, 6.0, ("es",)),
    ("Curaçao", "CW", 12.17, -68.99, 10.6, ("nl",)),
    ("Dominica", "DM", 15.42, -61.36, 10.6, ()),
    ("Dominican Republic", "DO", 18.8, -70.2, 7.6, ("es",)),
    ("Ecuador", "EC", -1.6, -78.4, 6.4, ("es",)),
    ("El Salvador", "SV", 13.7, -88.9, 7.8, ("es",)),
    ("Falkland Islands", "FK", -51.8, -59.5, 7.0, ()),
    ("French Guiana", "GF", 4.0, -53.1, 7.0, ("fr",)),
    ("Grenada", "GD", 12.2, -61.65, 10.0, ()),
    ("Guadeloupe", "GP", 16.2, -61.55, 9.2, ("fr",)),
    ("Guatemala", "GT", 15.7, -90.3, 6.8, ("es",)),
    ("Guyana", "GY", 4.9, -58.9, 6.2, ()),
    ("Haiti", "HT", 19.0, -72.7, 7.8, ("fr",)),
    ("Honduras", "HN", 14.8, -86.6, 6.8, ("es",)),
    ("Jamaica", "JM", 18.1, -77.3, 8.2, ()),
    ("Martinique", "MQ", 14.64, -61.02, 10.0, ("fr",)),
    ("Mexico", "MX", 23.6, -102.5, 4.6, ("es",)),
    ("Montserrat", "MS", 16.74, -62.19, 12.0, ()),
    ("Nicaragua", "NI", 12.9, -85.0, 6.8, ("es",)),
    ("Panama", "PA", 8.5, -80.1, 6.8, ("es",)),
    ("Paraguay", "PY", -23.4, -58.4, 5.8, ("es",)),
    ("Peru", "PE", -9.2, -75.0, 5.0, ("es",)),
    ("Puerto Rico", "PR", 18.2, -66.5, 8.6, ("es",)),
    ("Saint Barthélemy", "BL", 17.9, -62.83, 12.5, ("fr",)),
    ("Saint Kitts and Nevis", "KN", 17.25, -62.7, 10.6, ()),
    ("Saint Lucia", "LC", 13.91, -60.98, 10.8, ()),
    ("Saint Martin", "MF", 18.08, -63.05, 12.0, ("fr",)),
    ("Saint Vincent and the Grenadines", "VC", 13.0, -61.2, 9.4, ()),
    ("Sint Maarten", "SX", 18.04, -63.06, 12.5, ("nl",)),
    ("South Georgia and the South Sandwich Islands", "GS", -54.4, -36.6, 6.4, ()),
    ("Suriname", "SR", 4.1, -55.9, 6.8, ("nl",)),
    ("Trinidad and Tobago", "TT", 10.7, -61.2, 8.6, ()),
    ("Turks and Caicos Islands", "TC", 21.7, -71.8, 8.6, ()),
    ("United States Virgin Islands", "VI", 18.0, -64.8, 9.6, ()),
    ("Uruguay", "UY", -32.8, -56.0, 6.4, ("es",)),
    ("Venezuela", "VE", 7.1, -66.2, 5.4, ("es",)),
)

# Africa: the same, with the languages GBIF has enough names in (docs/26): Arabic,
# French, Portuguese, Spanish, Afrikaans, Malagasy, Swahili, Kinyarwanda, Wolof, Somali,
# Chichewa, Lingala, Hausa. Maps of scattered islands open on the main one: Saint
# Helena, Mauritius, the Seychelles (Mahé), Chagos (Diego Garcia's atolls) and the French
# Southern Territories (Kerguelen).
_AFRICA = (
    ("Algeria", "DZ", 28.0, 2.6, 4.8, ("ar", "fr")),
    ("Angola", "AO", -12.3, 17.5, 5.3, ("pt",)),
    ("Benin", "BJ", 9.3, 2.3, 6.6, ("fr",)),
    ("Botswana", "BW", -22.3, 24.7, 5.8, ()),
    ("British Indian Ocean Territory", "IO", -6.3, 71.9, 7.2, ()),
    ("Burkina Faso", "BF", 12.3, -1.6, 6.2, ("fr",)),
    ("Burundi", "BI", -3.4, 29.9, 8.0, ("fr",)),
    ("Cabo Verde", "CV", 16.0, -24.0, 8.0, ("pt",)),
    ("Cameroon", "CM", 5.7, 12.4, 5.6, ("fr",)),
    ("Central African Republic", "CF", 6.6, 20.9, 5.6, ("fr",)),
    ("Chad", "TD", 15.4, 18.7, 5.0, ("fr", "ar")),
    ("Comoros", "KM", -11.9, 43.9, 8.6, ("fr", "ar")),
    ("Côte d'Ivoire", "CI", 7.6, -5.5, 6.4, ("fr",)),
    ("Democratic Republic of the Congo", "CD", -2.9, 23.6, 4.8, ("fr", "sw", "ln")),
    ("Djibouti", "DJ", 11.8, 42.6, 8.0, ("fr", "ar")),
    ("Egypt", "EG", 26.8, 30.8, 5.4, ("ar",)),
    ("Equatorial Guinea", "GQ", 2.6, 9.5, 7.0, ("es", "fr")),
    ("Eritrea", "ER", 15.2, 39.4, 6.6, ()),
    ("Eswatini", "SZ", -26.5, 31.5, 8.4, ()),
    ("Ethiopia", "ET", 9.1, 40.0, 5.4, ()),
    ("French Southern Territories", "TF", -49.3, 69.4, 7.6, ("fr",)),
    ("Gabon", "GA", -0.8, 11.6, 6.4, ("fr",)),
    ("Gambia", "GM", 13.45, -15.4, 7.8, ("wo",)),
    ("Ghana", "GH", 7.9, -1.0, 6.4, ()),
    ("Guinea", "GN", 10.4, -10.9, 6.4, ("fr",)),
    ("Guinea-Bissau", "GW", 11.8, -15.2, 7.6, ("pt",)),
    ("Kenya", "KE", 0.2, 37.9, 5.8, ("sw",)),
    ("Lesotho", "LS", -29.6, 28.2, 8.0, ()),
    ("Liberia", "LR", 6.4, -9.4, 7.0, ()),
    ("Libya", "LY", 26.9, 17.3, 4.8, ("ar",)),
    ("Madagascar", "MG", -19.4, 46.7, 5.4, ("mg", "fr")),
    ("Malawi", "MW", -13.3, 34.0, 6.2, ("ny",)),
    ("Mali", "ML", 17.6, -3.5, 5.0, ("fr",)),
    ("Mauritania", "MR", 20.3, -10.4, 5.2, ("ar", "fr")),
    ("Mauritius", "MU", -20.25, 57.55, 9.6, ("fr",)),
    ("Mayotte", "YT", -12.83, 45.15, 10.4, ("fr",)),
    ("Morocco", "MA", 31.8, -7.1, 5.6, ("ar", "fr")),
    ("Mozambique", "MZ", -18.7, 35.5, 5.0, ("pt",)),
    ("Namibia", "NA", -22.6, 17.1, 5.4, ("af",)),
    ("Niger", "NE", 17.6, 8.1, 5.2, ("fr", "ha")),
    ("Nigeria", "NG", 9.1, 8.7, 5.6, ("ha",)),
    ("Republic of the Congo", "CG", -0.7, 15.0, 6.0, ("fr", "ln")),
    ("Réunion", "RE", -21.12, 55.53, 9.6, ("fr",)),
    ("Rwanda", "RW", -1.95, 29.9, 8.2, ("rw", "fr")),
    ("Saint Helena, Ascension and Tristan da Cunha", "SH", -15.96, -5.71, 11.0, ()),
    ("São Tomé and Príncipe", "ST", 0.95, 7.05, 8.4, ("pt",)),
    ("Senegal", "SN", 14.5, -14.5, 6.6, ("fr", "wo")),
    ("Seychelles", "SC", -4.68, 55.49, 9.8, ("fr",)),
    ("Sierra Leone", "SL", 8.5, -11.8, 7.4, ()),
    ("Somalia", "SO", 5.2, 46.2, 5.2, ("so", "ar")),
    ("South Africa", "ZA", -29.0, 25.1, 5.0, ("af",)),
    ("South Sudan", "SS", 7.3, 30.2, 5.8, ()),
    ("Sudan", "SD", 15.6, 30.2, 5.0, ("ar",)),
    ("Tanzania", "TZ", -6.4, 34.9, 5.4, ("sw",)),
    ("Togo", "TG", 8.6, 0.9, 6.8, ("fr",)),
    ("Tunisia", "TN", 34.0, 9.5, 6.2, ("ar", "fr")),
    ("Uganda", "UG", 1.4, 32.3, 6.6, ("sw",)),
    ("Western Sahara", "EH", 24.2, -12.9, 5.8, ("ar", "es")),
    ("Zambia", "ZM", -13.1, 27.8, 5.6, ("ny",)),
    ("Zimbabwe", "ZW", -19.0, 29.2, 6.0, ()),
)
# The Middle East and Asia (docs/28): the same, with the languages GBIF has names in.
# Turkey, Cyprus, the Caucasus and Russia stay under Europe.
_MIDDLE_EAST = (
    ("Bahrain", "BH", 26.03, 50.55, 9.4, ("ar",)),
    ("Iran", "IR", 32.4, 53.7, 4.6, ("fa",)),
    ("Iraq", "IQ", 33.2, 43.7, 5.4, ("ar",)),
    ("Israel", "IL", 31.4, 35.0, 6.8, ("he", "ar")),
    ("Jordan", "JO", 31.2, 36.5, 6.6, ("ar",)),
    ("Kuwait", "KW", 29.3, 47.6, 7.6, ("ar",)),
    ("Lebanon", "LB", 33.9, 35.9, 7.8, ("ar",)),
    ("Oman", "OM", 20.6, 56.1, 5.4, ("ar",)),
    ("Palestine", "PS", 31.9, 35.2, 8.0, ("ar",)),
    ("Qatar", "QA", 25.3, 51.2, 7.8, ("ar",)),
    ("Saudi Arabia", "SA", 23.9, 45.1, 4.6, ("ar",)),
    ("Syria", "SY", 34.8, 38.9, 6.0, ("ar",)),
    ("United Arab Emirates", "AE", 24.0, 54.0, 6.6, ("ar",)),
    ("Yemen", "YE", 15.6, 48.0, 5.4, ("ar",)),
)
_ASIA = (
    ("Afghanistan", "AF", 33.9, 67.7, 5.2, ("fa",)),
    ("Bangladesh", "BD", 23.7, 90.4, 6.2, ("bn",)),
    ("Bhutan", "BT", 27.5, 90.4, 7.6, ("dz",)),
    ("Brunei", "BN", 4.5, 114.7, 8.6, ("ms",)),
    ("Cambodia", "KH", 12.6, 105.0, 6.4, ("km",)),
    ("China", "CN", 35.9, 104.2, 3.4, ("zh",)),
    ("Christmas Island", "CX", -10.49, 105.63, 11.0, ()),
    ("Cocos (Keeling) Islands", "CC", -12.16, 96.87, 11.0, ()),
    ("Hong Kong", "HK", 22.35, 114.15, 9.6, ("zh",)),
    ("India", "IN", 22.0, 79.0, 3.9, ("hi", "bn", "ta")),
    ("Indonesia", "ID", -2.5, 118.0, 3.8, ("id", "ms")),
    ("Japan", "JP", 36.2, 138.3, 4.6, ("ja",)),
    ("Kazakhstan", "KZ", 48.0, 67.0, 3.9, ("ru", "kk")),
    ("Kyrgyzstan", "KG", 41.2, 74.8, 5.8, ("ru",)),
    ("Laos", "LA", 18.2, 103.9, 5.6, ("lo",)),
    ("Macao", "MO", 22.17, 113.55, 11.4, ("zh", "pt")),
    ("Malaysia", "MY", 4.2, 108.0, 4.8, ("ms", "zh", "ta")),
    ("Maldives", "MV", 3.2, 73.2, 6.0, ()),
    ("Mongolia", "MN", 46.9, 103.8, 4.4, ("mn", "ru")),
    ("Myanmar", "MM", 19.8, 96.1, 4.8, ("my",)),
    ("Nepal", "NP", 28.4, 84.1, 6.2, ("ne",)),
    ("North Korea", "KP", 40.3, 127.5, 6.2, ("ko",)),
    ("Pakistan", "PK", 30.4, 69.3, 4.8, ("ur",)),
    ("Philippines", "PH", 12.9, 121.8, 5.0, ("tl",)),
    ("Singapore", "SG", 1.35, 103.82, 10.6, ("ms", "zh", "ta")),
    ("South Korea", "KR", 36.4, 127.8, 6.4, ("ko",)),
    ("Sri Lanka", "LK", 7.9, 80.8, 6.8, ("si", "ta")),
    ("Taiwan", "TW", 23.7, 121.0, 6.8, ("zh",)),
    ("Tajikistan", "TJ", 38.9, 71.3, 6.0, ("ru",)),
    ("Thailand", "TH", 13.0, 101.0, 5.0, ("th",)),
    ("Timor-Leste", "TL", -8.85, 125.7, 7.8, ("pt",)),
    ("Turkmenistan", "TM", 39.0, 59.6, 5.4, ("ru",)),
    ("Uzbekistan", "UZ", 41.4, 64.6, 5.2, ("ru", "uz")),
    ("Vietnam", "VN", 16.0, 106.0, 5.0, ("vi",)),
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
    **{
        f"ca-{code.lower()}": Region(f"ca-{code.lower()}", name, lat, lon, zoom, CANADA, langs)
        for name, code, lat, lon, zoom, langs in _PROVINCES
    },
    **{
        f"au-{code.lower()}": Region(f"au-{code.lower()}", name, lat, lon, zoom, AUSTRALIA)
        for name, code, lat, lon, zoom in _AU_STATES
    },
    NZ: Region(NZ, "New Zealand", -41.0, 172.5, 4.9, NEW_ZEALAND, ("mi",)),
    **{
        code.lower(): Region(code.lower(), name, lat, lon, zoom, LATIN_AMERICA, langs)
        for name, code, lat, lon, zoom, langs in _LATIN_AMERICA
    },
    **{
        code.lower(): Region(code.lower(), name, lat, lon, zoom, AFRICA, langs)
        for name, code, lat, lon, zoom, langs in _AFRICA
    },
    **{
        code.lower(): Region(code.lower(), name, lat, lon, zoom, MIDDLE_EAST, langs)
        for name, code, lat, lon, zoom, langs in _MIDDLE_EAST
    },
    **{
        code.lower(): Region(code.lower(), name, lat, lon, zoom, ASIA, langs)
        for name, code, lat, lon, zoom, langs in _ASIA
    },
}
POSTAL_CODES = {name: code for name, code, *_ in _STATES}  # 'Ohio' -> 'OH'
COUNTRY_CODES = {name: code for name, code, *_ in _COUNTRIES}  # 'France' -> 'FR'
LATIN_AMERICA_CODES = {name: code for name, code, *_ in _LATIN_AMERICA}  # 'Brazil' -> 'BR'
AFRICA_CODES = {name: code for name, code, *_ in _AFRICA}  # 'Kenya' -> 'KE'
MIDDLE_EAST_CODES = {name: code for name, code, *_ in _MIDDLE_EAST}  # 'Israel' -> 'IL'
ASIA_CODES = {name: code for name, code, *_ in _ASIA}  # 'Japan' -> 'JP'
PROVINCE_CODES = {name: code for name, code, *_ in _PROVINCES}  # 'Ontario' -> 'ON'
AU_STATE_CODES = {name: code for name, code, *_ in _AU_STATES}  # 'Tasmania' -> 'TAS'


# Other names people use for a region, found by the search too (docs/27, section 3).
# Everyday names and abbreviations only: plain codes ("ZA", "TX") are not matched.
OTHER_NAMES: dict[str, tuple[str, ...]] = {
    "ci": ("Ivory Coast",),
    "sz": ("Swaziland",),
    "cv": ("Cape Verde",),
    "cd": ("DR Congo", "DRC", "Congo-Kinshasa", "Zaire"),
    "cg": ("Congo-Brazzaville",),
    "cz": ("Czech Republic",),
    "nl": ("Holland",),
    "tr": ("Türkiye",),
    "va": ("Holy See",),
    "bq": ("Bonaire", "Sint Eustatius", "Saba"),
    "vi": ("US Virgin Islands", "USVI"),
    "vg": ("BVI",),
    "bl": ("St Barts", "St Barths"),
    "us-dc": ("Washington DC",),
    "au-act": ("ACT",),
    "au-nsw": ("NSW",),
    "ca-pe": ("PEI",),
    "mm": ("Burma",),
    "tl": ("East Timor",),
    "ae": ("UAE",),
    "mo": ("Macau",),
    "vn": ("Viet Nam",),
    "kr": ("Republic of Korea",),
    "kp": ("DPRK",),
    "ps": ("West Bank", "Gaza"),
}
# Typing one of these finds no pack: the UK's list is built in, and a note says so
UK_NAMES = (
    "United Kingdom",
    "UK",
    "Great Britain",
    "Britain",
    "England",
    "Scotland",
    "Wales",
    "Northern Ireland",
)


def fold(text: str) -> str:
    """Text as the region search compares it: no capitals or accents, no apostrophes or
    full stops, hyphens as spaces, '&' as 'and', and 'St' as 'Saint'.
    'St. Barthélemy' -> 'saint barthelemy', "Côte d'Ivoire" -> 'cote divoire'."""
    text = unicodedata.normalize("NFKD", text.casefold())
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = re.sub(r"['’`.]", "", text.replace("&", " and "))
    text = re.sub(r"[-‐–—,()/]", " ", text)
    # "St" only once a space follows it, so typing "st" on the way to "Sta..." still
    # finds Estonia and Australia
    text = re.sub(r"\bst\s", "saint ", text)
    return " ".join(text.split())


def region_matches(typed: str, code: str, name: str) -> bool:
    """Is the region (its code and its name in the list of packs) one that `typed` finds?
    Empty text finds them all."""
    wanted = fold(typed)
    return not wanted or any(wanted in fold(n) for n in (name, *OTHER_NAMES.get(code, ())))


def means_the_uk(typed: str) -> bool:
    """Is the typed text (3 letters at least, or "UK") the start of one of the UK's names?
    ("Wales" is, though it's in New South Wales too; "Ireland" isn't.)"""
    wanted = fold(typed)
    return (len(wanted) >= 3 or wanted == "uk") and any(
        fold(n).startswith(wanted) for n in UK_NAMES
    )


# Countries split into several packs: their packs' codes start with these
_SPLIT = {"US": "us-", "CA": "ca-", "AU": "au-"}


def regions_of_country(country: str | None) -> list[str]:
    """The packs for a country, by its two-letter code ('KE' -> ['ke'], 'US' -> every
    state, 'RU' -> European Russia and all of Russia); [] for the UK (its list is built
    in), a country without a pack, or None. For the welcome's suggestion (docs/27)."""
    if not country:
        return []
    country = country.upper()
    if prefix := _SPLIT.get(country):
        return [code for code in REGIONS if code.startswith(prefix)]
    if country == "RU":
        return ["ru-eu", "ru"]
    code = country.lower()
    return [code] if code in REGIONS and code != UK else []


def region(code: str) -> Region:
    """The region with this code; an unknown one is treated as the UK."""
    return REGIONS.get(code, REGIONS[UK])


def group_of(code: str) -> str:
    """United Kingdom or one of GROUPS (Europe, United States...); 'Elsewhere' for a pack
    from a region this version doesn't know yet."""
    found = REGIONS.get(code)
    return found.group if found else "Elsewhere"
