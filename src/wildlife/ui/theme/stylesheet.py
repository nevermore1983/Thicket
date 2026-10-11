"""Builds the Qt stylesheet (QSS) and palette from the design tokens.

Widgets opt into styles with an objectName (e.g. "Sidebar") or a dynamic
property (e.g. variant="primary"). Style names are component-specific on
purpose: the prototype taught us that generic names like "empty" collide.
"""

from __future__ import annotations

from PySide6.QtGui import QColor, QPalette

from wildlife.ui.theme.tokens import (
    FONT_DISPLAY,
    FONT_FALLBACK,
    FONT_UI,
    RADIUS_LG,
    RADIUS_MD,
    RADIUS_SM,
    SIZE_BODY,
    SIZE_CAPTION,
    SIZE_SMALL,
    SIZE_TITLE,
    Tokens,
)


def build_palette(t: Tokens) -> QPalette:
    """A QPalette so any unstyled Qt widget still matches the theme."""
    p = QPalette()
    roles = {
        QPalette.ColorRole.Window: t.bg,
        QPalette.ColorRole.WindowText: t.text,
        QPalette.ColorRole.Base: t.surface,
        QPalette.ColorRole.AlternateBase: t.surface_2,
        QPalette.ColorRole.Text: t.text,
        QPalette.ColorRole.Button: t.surface,
        QPalette.ColorRole.ButtonText: t.text,
        QPalette.ColorRole.Highlight: t.accent,
        QPalette.ColorRole.HighlightedText: t.accent_fg,
        QPalette.ColorRole.ToolTipBase: t.text,
        QPalette.ColorRole.ToolTipText: t.surface,
        QPalette.ColorRole.PlaceholderText: t.text_3,
        QPalette.ColorRole.Link: t.accent,
        QPalette.ColorRole.Mid: t.border,
        QPalette.ColorRole.Midlight: t.surface_2,
        QPalette.ColorRole.Dark: t.border_strong,
    }
    for role, colour in roles.items():
        p.setColor(role, QColor(colour))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, QColor(t.text_3))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, QColor(t.text_3))
    return p


def build_qss(t: Tokens) -> str:
    fonts = f'"{FONT_UI}", "{FONT_FALLBACK}"'
    return f"""
* {{ font-family: {fonts}; font-size: {SIZE_BODY}px; }}
QMainWindow, QWidget#Page, QScrollArea#PageScroll, QWidget#PageBody {{ background: {t.bg}; }}
QToolTip {{ background: {t.text}; color: {t.surface}; border: none; padding: 5px 8px; border-radius: 6px; }}

/* ---- sidebar ---- */
QWidget#Sidebar {{ background: {t.surface}; border-right: 1px solid {t.border}; }}
QLabel#BrandName {{ font-family: "{FONT_DISPLAY}", {fonts}; font-size: 16px; font-weight: 650; color: {t.text}; }}
QLabel#BrandSub {{ font-size: 11px; color: {t.text_3}; }}
QLabel#BrandMark {{ background: {t.accent}; border-radius: 8px; }}
QPushButton#NavItem {{
    text-align: left; padding: 8px 10px; border: none; border-radius: 8px;
    background: transparent; color: {t.text_2}; min-height: 22px;
}}
QPushButton#NavItem:hover {{ background: {t.surface_2}; color: {t.text}; }}
QPushButton#NavItem:checked {{ background: {t.accent_subtle}; color: {t.accent_subtle_text}; font-weight: 600; }}

/* ---- top bar ---- */
QWidget#TopBar {{ background: {t.surface}; border-bottom: 1px solid {t.border}; }}
QLineEdit#GlobalSearch {{
    background: {t.surface_2}; border: 1px solid {t.border}; border-radius: 9px;
    padding: 0 12px; min-height: 36px; color: {t.text};
}}
QLineEdit#GlobalSearch:focus {{ background: {t.surface}; border-color: {t.accent}; }}

/* ---- buttons ---- */
QPushButton {{
    background: {t.surface}; color: {t.text}; border: 1px solid {t.border_strong};
    border-radius: 8px; padding: 0 14px; min-height: 34px; font-weight: 600;
}}
QPushButton:hover {{ background: {t.surface_2}; }}
QPushButton:focus {{ border-color: {t.accent}; }}
QPushButton:disabled {{ color: {t.text_3}; border-color: {t.border}; }}
QPushButton[variant="primary"] {{ background: {t.accent}; border-color: {t.accent}; color: {t.accent_fg}; }}
QPushButton[variant="primary"]:hover {{ background: {t.accent_hover}; border-color: {t.accent_hover}; }}
QPushButton[variant="ghost"] {{ background: transparent; border-color: transparent; color: {t.text_2}; }}
QPushButton[variant="ghost"]:hover {{ background: {t.surface_2}; color: {t.text}; }}
QPushButton[variant="link"] {{ background: transparent; border: none; color: {t.accent}; padding: 0 6px; min-height: 26px; }}

/* segmented control: a row of checkable buttons inside a Segmented frame */
QFrame#Segmented {{ background: {t.surface_2}; border: 1px solid {t.border}; border-radius: 9px; }}
QFrame#Segmented QPushButton {{
    border: none; background: transparent; color: {t.text_2}; min-height: 28px;
    border-radius: 6px; padding: 0 12px; font-size: {SIZE_SMALL}px;
}}
QFrame#Segmented QPushButton:checked {{ background: {t.surface}; color: {t.text}; }}

/* ---- text ---- */
QLabel#PageTitle {{ font-family: "{FONT_DISPLAY}", {fonts}; font-size: {SIZE_TITLE}px; font-weight: 600; color: {t.text}; }}
QLabel#PageSubtitle, QLabel[role="muted"] {{ color: {t.text_2}; }}
QLabel[role="caption"] {{ color: {t.text_3}; font-size: {SIZE_CAPTION}px; }}
QLabel[role="sectionTitle"] {{ font-size: 15px; font-weight: 600; color: {t.text}; }}
QLabel[role="rowTitle"] {{ font-weight: 600; color: {t.text}; }}

/* ---- cards & empty states ---- */
QFrame#Card {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: {RADIUS_LG}px; }}
QFrame#EmptyState {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: {RADIUS_LG}px; }}
QLabel#EmptyStateIcon {{ background: {t.accent_subtle}; border-radius: 14px; }}
QLabel#EmptyStateTitle {{ font-family: "{FONT_DISPLAY}", {fonts}; font-size: 16px; font-weight: 600; color: {t.text}; }}
QLabel#EmptyStateText {{ color: {t.text_2}; }}
QFrame#Callout {{ background: {t.surface_2}; border-radius: {RADIUS_MD}px; }}
QFrame#Callout[tone="warning"] {{ background: {t.warning_subtle}; }}
QFrame#Callout[tone="warning"] QLabel {{ color: {t.warning}; }}
QFrame#Callout[tone="good"] {{ background: {t.good_subtle}; }}
QFrame#Callout[tone="good"] QLabel {{ color: {t.good_text}; }}
QFrame#SettingsRow {{ border-top: 1px solid {t.border}; }}
QFrame#SettingsRow[first="true"] {{ border-top: none; }}

/* ---- toast ---- */
QFrame#Toast {{ background: {t.text}; border-radius: {RADIUS_MD}px; }}
QFrame#Toast QLabel {{ color: {t.surface}; }}
QFrame#Toast QPushButton {{ background: transparent; border: none; color: {t.surface}; padding: 0 8px; min-height: 28px; }}
QFrame#Toast QPushButton:hover {{ background: {t.text_2}; border-radius: {RADIUS_SM}px; }}

/* ---- inputs & scrollbars ---- */
QLineEdit, QComboBox, QSpinBox, QDateEdit, QTimeEdit, QPlainTextEdit, QTextEdit {{
    background: {t.surface}; color: {t.text}; border: 1px solid {t.border_strong};
    border-radius: 8px; padding: 0 10px; min-height: 34px;
    selection-background-color: {t.accent}; selection-color: {t.accent_fg};
}}
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus {{ border-color: {t.accent}; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.border_strong}; border-radius: 4px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: {t.text_3}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t.border_strong}; border-radius: 4px; min-width: 32px; }}
QScrollArea {{ border: none; }}
"""
