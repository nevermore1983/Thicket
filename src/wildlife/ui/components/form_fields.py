"""Form building blocks shared by the editors (sighting, outing, place): a labelled
field with a help or error line, choice boxes, and reading typed times."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractButton,
    QAbstractSpinBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPlainTextEdit,
    QVBoxLayout,
    QWidget,
)

_TIME = re.compile(r"^\s*(\d{1,2})[:.]?(\d{2})\s*$")


def normalise_time(text: str) -> str | None:
    """'930' / '9:30' / '09.30' -> '09:30'; '' -> None; anything else is returned as typed."""
    text = text.strip()
    if not text:
        return None
    if m := _TIME.match(text):
        return f"{int(m[1]):02d}:{m[2]}"
    return text


TIME_PROBLEM = "Use 24-hour time like 09:30, or leave it empty if you don't know."


def check_time_field(edit: QLineEdit, field: Field) -> None:
    """When you leave a time box: tidy what you typed ('930' becomes '09:30'), or say
    straight away if it can't be read, rather than waiting for Save."""
    fixed = normalise_time(edit.text())
    if fixed is None:
        field.reset_note()
        return
    hour, _, minute = fixed.partition(":")
    if not (minute and hour.isdigit() and minute.isdigit() and int(hour) < 24 and int(minute) < 60):
        field.set_note(TIME_PROBLEM, "error")
        return
    if fixed != edit.text():
        edit.setText(fixed)
    field.reset_note()


INPUTS = (QLineEdit, QComboBox, QAbstractSpinBox, QPlainTextEdit, QAbstractButton)


def input_of(control: QWidget) -> QWidget:
    """The part of a control that takes keyboard input (the text box of the species
    picker, the first input inside a row of controls), or the control itself."""
    if isinstance(control, INPUTS):
        return control
    if isinstance(getattr(control, "edit", None), QWidget):
        return control.edit
    return next((w for w in control.findChildren(QWidget) if isinstance(w, INPUTS)), control)


class Field(QWidget):
    """Label above a control, with a help/error line below it. `beside`: a button to the
    right of the control (e.g. "Choose on map")."""

    def __init__(
        self, label: str, control: QWidget, help_text: str = "", beside: QWidget | None = None
    ) -> None:
        super().__init__()
        self.control = control
        v = QVBoxLayout(self)
        v.setContentsMargins(0, 0, 0, 0)
        v.setSpacing(5)
        self.label = QLabel(label)
        self.label.setProperty("role", "fieldLabel")
        v.addWidget(self.label)
        if beside is None:
            v.addWidget(control)
        else:
            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(control, 1)
            row.addWidget(beside)
            v.addLayout(row)
        # Link the label to the field, so screen readers say "Date, edit" rather than "edit"
        target = input_of(control)
        self.label.setBuddy(target)
        if not target.accessibleName() and not isinstance(target, QAbstractButton):
            target.setAccessibleName(label)  # a button keeps its own words ("Garden")
        if help_text:
            target.setAccessibleDescription(help_text)
        self.note = QLabel(help_text)
        self.note.setWordWrap(True)
        self.note.setProperty("role", "help")
        self.note.setVisible(bool(help_text))
        self._help = help_text
        v.addWidget(self.note)

    def set_note(self, text: str, tone: str = "help") -> None:
        self.note.setText(text)
        self.note.setProperty("role", tone)
        self.note.setVisible(bool(text))
        self.note.style().unpolish(self.note)
        self.note.style().polish(self.note)
        self.control.setProperty("invalid", tone == "error")
        self.control.style().unpolish(self.control)
        self.control.style().polish(self.control)

    def reset_note(self) -> None:
        self.set_note(self._help)


def maybe_enum(enum, value):
    return None if value is None else enum(value)


def combo(options: list[tuple[str, object]], current: object) -> QComboBox:
    box = QComboBox()
    for label, value in options:
        box.addItem(label, value)
        if explanation := getattr(value, "explanation", ""):
            box.setItemData(box.count() - 1, explanation, Qt.ItemDataRole.ToolTipRole)
    box.setCurrentIndex(max(0, box.findData(current)))
    return box
