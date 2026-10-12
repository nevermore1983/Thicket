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
QLabel#KeyCap {{ background: {t.surface_2}; border: 1px solid {t.border}; border-radius: 6px; padding: 2px 8px; font-weight: 600; color: {t.text}; }}
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
QLineEdit:focus, QComboBox:focus, QPlainTextEdit:focus, QDateEdit:focus, QSpinBox:focus {{ border-color: {t.accent}; }}
QComboBox::drop-down, QDateEdit::drop-down {{ subcontrol-origin: padding; subcontrol-position: center right;
    width: 26px; border: none; background: transparent; }}
QSpinBox::up-button, QSpinBox::down-button {{ border: none; background: transparent; width: 18px; }}
QScrollBar:vertical {{ background: transparent; width: 12px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: {t.border_strong}; border-radius: 4px; min-height: 32px; }}
QScrollBar::handle:vertical:hover {{ background: {t.text_3}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 12px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: {t.border_strong}; border-radius: 4px; min-width: 32px; }}
QScrollArea {{ border: none; }}
QScrollArea > QWidget > QWidget#PanelBody, QWidget#PanelBody {{ background: {t.surface}; }}

/* ---- side panel ---- */
QFrame#SidePanel {{ background: {t.surface}; border-left: 1px solid {t.border}; }}
QFrame#PanelHead {{ background: {t.surface}; border-bottom: 1px solid {t.border}; }}
QFrame#PanelFoot {{ background: {t.surface}; border-top: 1px solid {t.border}; }}

/* ---- form fields ---- */
QLabel[role="fieldLabel"] {{ font-size: 12.5px; font-weight: 600; color: {t.text_2}; }}
QLabel[role="help"] {{ font-size: 12.5px; color: {t.text_3}; }}
QLabel[role="error"] {{ font-size: 12.5px; color: {t.danger}; }}
QLabel[role="ok"] {{ font-size: 12.5px; color: {t.good_text}; }}
QLabel[role="warning"] {{ color: {t.warning}; }}
QLabel[role="callout"] {{ background: {t.surface_2}; border-radius: {RADIUS_MD}px; padding: 10px 12px; color: {t.text_2}; }}
QLineEdit[invalid="true"], QComboBox[invalid="true"], QDateEdit[invalid="true"], QPlainTextEdit[invalid="true"] {{
    border-color: {t.danger}; }}
QFrame#ChosenSpecies {{ background: {t.surface}; border: 1px solid {t.border_strong}; border-radius: 8px; }}
QListWidget#Suggestions {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: {RADIUS_MD}px;
    outline: 0; padding: 2px; }}
QListWidget#Suggestions::item {{ border-radius: 6px; color: {t.text_2}; }}
QListWidget#Suggestions::item:selected, QListWidget#Suggestions::item:hover {{ background: {t.surface_2}; }}
QPushButton[chip="true"], QComboBox[chip="true"] {{
    min-height: 28px; border-radius: 14px; padding: 0 12px; font-size: 12.5px; font-weight: 500; }}
QPushButton[chip="true"]:checked {{
    background: {t.accent_subtle}; border-color: {t.accent_subtle}; color: {t.accent_subtle_text}; }}
QFrame#DropZone {{ background: {t.surface_2}; border: 1.5px dashed {t.border_strong}; border-radius: {RADIUS_MD}px; }}
QFrame#DropZone:hover, QFrame#DropZone[over="true"] {{ border-color: {t.accent}; }}
QCheckBox {{ spacing: 8px; color: {t.text}; }}

/* ---- filter bar & bulk bar ---- */
QPushButton[filterChip="idle"], QPushButton[filterChip="active"] {{
    min-height: 32px; border-radius: 16px; padding: 0 12px; font-size: 13px; font-weight: 500; }}
QPushButton[filterChip="active"] {{
    background: {t.accent_subtle}; border-color: {t.accent_subtle}; color: {t.accent_subtle_text}; }}
QFrame#BulkBar {{ background: {t.text}; border-radius: {RADIUS_MD}px; }}
QLabel#BulkLabel {{ color: {t.surface}; font-weight: 600; }}
QPushButton[variant="bulk"] {{ background: transparent; color: {t.surface}; border-color: {t.text_3}; min-height: 30px; }}
QPushButton[variant="bulk"]:hover {{ background: {t.text_2}; }}

/* ---- tables ---- */
QTableView, QTableWidget {{
    background: {t.surface}; border: 1px solid {t.border}; border-radius: {RADIUS_LG}px; gridline-color: {t.border};
    selection-background-color: {t.accent_subtle}; selection-color: {t.text}; outline: 0; }}
QTableView::item, QTableWidget::item {{ padding: 0 10px; border-bottom: 1px solid {t.border}; }}
QTableView::item:hover, QTableWidget::item:hover {{ background: {t.surface_2}; }}
QTableView::item:selected, QTableWidget::item:selected {{ background: {t.accent_subtle}; color: {t.text}; }}
QHeaderView {{ background: transparent; }}
QHeaderView::section {{ background: {t.surface}; color: {t.text_2}; border: none; border-bottom: 1px solid {t.border};
    padding: 9px 10px; font-size: 12px; font-weight: 600; }}
QHeaderView::section:first {{ border-top-left-radius: {RADIUS_LG}px; }}
QTableCornerButton::section {{ background: {t.surface}; border: none; }}

/* ---- badges, tiles, clickable rows ---- */
QLabel[badge="lifer"] {{ background: {t.accent_subtle}; color: {t.accent_subtle_text}; border-radius: 9px;
    padding: 2px 9px; font-size: 12px; font-weight: 650; }}
QLabel[badge="warn"] {{ background: {t.warning_subtle}; color: {t.warning}; border-radius: 9px;
    padding: 2px 9px; font-size: 12px; font-weight: 650; }}
QLabel[badge="plain"] {{ background: {t.surface_3}; color: {t.text_2}; border-radius: 9px;
    padding: 2px 9px; font-size: 12px; font-weight: 650; }}
QFrame#Tile {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: {RADIUS_LG}px; }}
QLabel#TileLabel {{ color: {t.text_2}; font-size: 12.5px; font-weight: 600; }}
QLabel#TileValue {{ font-family: "{FONT_DISPLAY}", {fonts}; font-size: 30px; font-weight: 600; color: {t.text}; }}
QLabel[role="deltaUp"] {{ color: {t.good_text}; font-size: 12.5px; }}
QLabel[role="delta"] {{ color: {t.text_3}; font-size: 12.5px; }}
/* ---- calendar ---- */
QFrame#WeekCol {{ background: {t.surface}; border: 1px solid {t.border}; border-radius: {RADIUS_LG}px; }}
QFrame#WeekCol[selected="true"] {{ border: 2px solid {t.accent}; }}
QPushButton#WeekColHead {{ background: transparent; border: none; padding: 2px 4px; font-size: 13px;
    font-weight: 600; color: {t.text}; text-align: left; border-radius: 6px; }}
QPushButton#WeekColHead:hover {{ background: {t.surface_2}; }}
QPushButton#WeekColHead[today="true"] {{ color: {t.accent}; }}
QLabel#CalTitle {{ font-family: "{FONT_DISPLAY}", {fonts}; font-size: 20px; font-weight: 600; color: {t.text}; }}
QPushButton#OutingChip {{ background: {t.accent_subtle}; color: {t.accent_subtle_text}; border: none;
    border-radius: 15px; padding: 5px 12px; font-weight: 600; }}
QPushButton#OutingChip:hover {{ background: {t.surface_3}; }}
QFrame#RowButton {{ background: transparent; border-radius: 9px; }}
QFrame#RowButton:hover {{ background: {t.surface_2}; }}
QFrame#RowButton:focus {{ border: 2px solid {t.accent}; }}
QLabel#RowTitle {{ font-weight: 600; color: {t.text}; }}
QLabel#RowMeta {{ font-size: 12.5px; color: {t.text_2}; }}
QLabel#RowSide {{ font-size: 12.5px; color: {t.text_3}; }}

/* ---- menus, combo popups, progress ---- */
QMenu {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border}; border-radius: {RADIUS_MD}px; padding: 6px; }}
QMenu::item {{ padding: 6px 28px 6px 10px; border-radius: 6px; }}
QMenu::item:selected {{ background: {t.surface_2}; color: {t.text}; }}
QMenu::separator {{ height: 1px; background: {t.border}; margin: 6px 4px; }}
QComboBox QAbstractItemView {{ background: {t.surface}; color: {t.text}; border: 1px solid {t.border};
    selection-background-color: {t.surface_2}; selection-color: {t.text}; outline: 0; }}
QProgressBar {{ background: {t.surface_3}; border: none; border-radius: 4px; max-height: 8px; text-align: center; }}
QProgressBar::chunk {{ background: {t.accent}; border-radius: 4px; }}
QDialog {{ background: {t.surface}; }}
"""
