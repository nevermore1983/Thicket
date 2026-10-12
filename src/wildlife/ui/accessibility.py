"""Checking a screen for controls a screen reader can't name or the keyboard can't reach.

Used by the tests (so a nameless button fails the build) and by scripts/audit_ui.py.
"""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractItemView,
    QAbstractSlider,
    QAbstractSpinBox,
    QComboBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QScrollBar,
    QTextEdit,
    QWidget,
)

INTERACTIVE = (
    QAbstractButton,
    QLineEdit,
    QComboBox,
    QAbstractSpinBox,
    QAbstractItemView,
    QAbstractSlider,
    QPlainTextEdit,
    QTextEdit,
)


@dataclass(frozen=True, slots=True)
class Finding:
    severity: str  # 'high' (no name on a button or drawn widget) or 'medium'
    message: str


def describe(w: QWidget) -> str:
    text = w.text() if isinstance(w, QAbstractButton) else ""
    if isinstance(w, QLineEdit):
        text = w.placeholderText()
    return f"{type(w).__name__}({w.objectName() or text[:30] or '?'})"


def name_of(w: QWidget, buddies: set[int]) -> str:
    """What a screen reader would call the control ('' if nothing)."""
    if w.accessibleName():
        return w.accessibleName()
    if isinstance(w, QAbstractButton) and w.text().strip():
        return w.text()
    return "(label)" if id(w) in buddies else ""


def skip(w: QWidget) -> bool:
    """Parts that aren't controls in their own right: scroll bars and table headers (the
    keyboard scrolls the content itself), a spin box's inner text field, a combo box's
    pop-up list, a text box's own icon buttons, and the unselected options of an
    exclusive group (Tab reaches the group through its selected option; the arrow keys
    move between options)."""
    if isinstance(w, (QScrollBar, QHeaderView)) or w.objectName() == "qt_spinbox_lineedit":
        return True
    if isinstance(w, QAbstractItemView) and isinstance(w.parent(), QComboBox):
        return True
    if isinstance(w, QAbstractButton) and isinstance(w.parent(), QLineEdit):
        return True  # a text box's own icon or clear button (the keyboard edits the text)
    if isinstance(w, QAbstractButton):
        group = w.group()
        if ((group and group.exclusive()) or w.autoExclusive()) and not w.isChecked():
            return True
    return False


def is_custom_painted(w: QWidget) -> bool:
    """Our own drawn widgets (charts, calendar, grids) that take keyboard focus."""
    return bool(
        type(w).__module__.startswith("wildlife.")
        and w.focusPolicy() & Qt.FocusPolicy.TabFocus
        and not isinstance(w, INTERACTIVE)
        and not w.findChildren(QWidget)
    )


def controls(root: QWidget) -> list[QWidget]:
    """The visible, enabled controls on a screen."""
    return [
        w
        for w in root.findChildren(QWidget)
        if w.isVisibleTo(root)
        and w.isEnabled()
        and (isinstance(w, INTERACTIVE) or is_custom_painted(w))
        and not skip(w)
    ]


def check(root: QWidget) -> list[Finding]:
    """Every control without a name, or that Tab can't reach."""
    buddies = {id(lbl.buddy()) for lbl in root.window().findChildren(QLabel) if lbl.buddy()}
    out = []
    for w in controls(root):
        if not name_of(w, buddies):
            painted = isinstance(w, QAbstractButton) or is_custom_painted(w)
            tip = f" (tooltip: “{w.toolTip()}”)" if w.toolTip() else ""
            out.append(Finding("high" if painted else "medium", f"No name for {describe(w)}{tip}"))
        if not (w.focusPolicy() & Qt.FocusPolicy.TabFocus):
            out.append(Finding("medium", f"Not reachable with Tab: {describe(w)}"))
    return out
