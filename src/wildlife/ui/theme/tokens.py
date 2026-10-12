"""Design tokens: every colour, size and font the UI uses, in one place.

Values come from docs/04-ui-ux-design.md. Screens never use raw colours;
they use these names, so light/dark switching is just a different Tokens.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Tokens:
    dark: bool
    bg: str
    surface: str
    surface_2: str
    surface_3: str
    border: str
    border_strong: str
    text: str
    text_2: str
    text_3: str
    accent: str
    accent_hover: str
    accent_fg: str
    accent_subtle: str
    accent_subtle_text: str
    danger: str
    danger_subtle: str
    warning: str
    warning_subtle: str
    good_text: str
    good_subtle: str
    # categorical slots 1..8 (validated order) + 0 for "Other"
    categories: tuple[str, ...]
    category_ink: tuple[str, ...]  # icon colour drawn on top of each category colour
    # sequential ramp q0 (zero) .. q6 (most)
    ramp: tuple[str, ...]


LIGHT = Tokens(
    dark=False,
    bg="#f3f5f1",
    surface="#ffffff",
    surface_2="#f0f2ed",
    surface_3="#e5e9e2",
    border="#dfe3dc",
    border_strong="#c7cec4",
    text="#17201a",
    text_2="#556058",
    text_3="#687069",
    accent="#2e7d4f",
    accent_hover="#256a42",
    accent_fg="#ffffff",
    accent_subtle="#e2f0e7",
    accent_subtle_text="#1d5a37",
    danger="#c4372c",
    danger_subtle="#fbe8e6",
    warning="#8f5b00",
    warning_subtle="#fbf1d9",
    good_text="#1e6b2c",
    good_subtle="#e4f3e6",
    categories=(
        "#7d847e",
        "#2a78d6",
        "#eb6834",
        "#1baf7a",
        "#eda100",
        "#e87ba4",
        "#008300",
        "#4a3aa7",
        "#e34948",
    ),
    category_ink=(
        "#ffffff",
        "#ffffff",
        "#ffffff",
        "#0b2a1f",
        "#2b1d00",
        "#3a0d1f",
        "#ffffff",
        "#ffffff",
        "#ffffff",
    ),
    ramp=("#eef1ec", "#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95"),
)

DARK = Tokens(
    dark=True,
    bg="#0f1210",
    surface="#181c19",
    surface_2="#1f2420",
    surface_3="#282e29",
    border="#2b322d",
    border_strong="#3b443d",
    text="#e6ebe6",
    text_2="#a9b3aa",
    text_3="#8d978e",
    accent="#5fbf85",
    accent_hover="#78cc99",
    accent_fg="#0d1a12",
    accent_subtle="#1b3125",
    accent_subtle_text="#9edcb5",
    danger="#ef7166",
    danger_subtle="#3a1d1a",
    warning="#e3a73f",
    warning_subtle="#33290f",
    good_text="#6fd08a",
    good_subtle="#18301e",
    categories=(
        "#7a847b",
        "#3987e5",
        "#d95926",
        "#199e70",
        "#c98500",
        "#d55181",
        "#008300",
        "#9085e9",
        "#e66767",
    ),
    category_ink=(
        "#ffffff",
        "#ffffff",
        "#ffffff",
        "#ffffff",
        "#ffffff",
        "#ffffff",
        "#ffffff",
        "#120d33",
        "#ffffff",
    ),
    # validated sequential steps (dark: near-zero recedes into the surface, high values lighten)
    ramp=("#1f2420", "#0d366b", "#184f95", "#256abf", "#3987e5", "#6da7ec", "#b7d3f6"),
)

# Spacing scale (px), radii (px) and type sizes (px)
SPACE = (0, 4, 8, 12, 16, 24, 32)
RADIUS_SM, RADIUS_MD, RADIUS_LG = 6, 10, 14
FONT_UI = "Segoe UI Variable Text"
FONT_DISPLAY = "Segoe UI Variable Display"
FONT_FALLBACK = "Segoe UI"
# Scientific names. Bundled (resources/fonts, loaded by the ThemeManager); Georgia if missing
FONT_SCI = "Source Serif 4 Variable"
SIZE_BODY, SIZE_SMALL, SIZE_CAPTION, SIZE_TITLE, SIZE_TILE = 14, 13, 12, 24, 30
