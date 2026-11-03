"""Add a species of your own: one that isn't in your species list (an escape, a new
arrival, a species from a region whose pack you haven't added). Opened from the species
picker's last suggestion, "Add … as your own species"."""

from __future__ import annotations

import re

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QVBoxLayout,
    QWidget,
)

from wildlife.domain.errors import ValidationError
from wildlife.domain.models import Taxon
from wildlife.services.species_catalogue import SpeciesCatalogue

# Two or more words, the first capitalised and the rest lower case: a scientific name
_LOOKS_SCIENTIFIC = re.compile(r"^[A-Z][a-z]+(?: [a-z][a-z.-]+)+$")


class AddSpeciesDialog(QDialog):
    """`taxon` holds the new species once it's added."""

    def __init__(self, catalogue: SpeciesCatalogue, typed: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.catalogue = catalogue
        self.taxon: Taxon | None = None
        self._group_chosen = False
        self.setWindowTitle("Add your own species")
        self.setMinimumWidth(460)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(12)
        intro = QLabel(
            "For a species that isn't in your list. It's added for you only, and an "
            "export brings it along. If a species pack adds it later, the two become one."
        )
        intro.setWordWrap(True)
        intro.setProperty("role", "muted")
        v.addWidget(intro)

        form = QFormLayout()
        form.setVerticalSpacing(10)
        typed = " ".join(typed.split())
        # A scientific name if it's written like one and starts with a genus the list has
        # ("Erithacus akahige"), else a common name ("Japanese robin")
        scientific = bool(_LOOKS_SCIENTIFIC.match(typed)) and (
            catalogue.suggested_category(typed) is not None
        )
        self.common = QLineEdit("" if scientific else typed)
        self.common.setPlaceholderText("e.g. Red-headed Bunting (optional)")
        self.scientific = QLineEdit(typed if scientific else "")
        self.scientific.setPlaceholderText("e.g. Emberiza bruniceps")
        self.scientific.editingFinished.connect(self._suggest_group)
        self.group = QComboBox()
        for category in catalogue.categories():
            self.group.addItem(category.name, category.id)
        self.group.setCurrentIndex(
            max(0, self.group.findData(next(c.id for c in catalogue.categories() if c.is_fallback)))
        )
        self.group.activated.connect(lambda _i: setattr(self, "_group_chosen", True))
        self.problem = QLabel()
        self.problem.setWordWrap(True)
        self.problem.setProperty("role", "error")
        self.problem.hide()
        form.addRow("Common name", self.common)
        form.addRow("Scientific name", self.scientific)
        form.addRow("Group", self.group)
        v.addLayout(form)
        hint = QLabel(
            "Not sure of the scientific name? iNaturalist or Wikipedia give it at the top "
            "of the species' page. It keeps your records clear when you share them."
        )
        hint.setWordWrap(True)
        hint.setProperty("role", "caption")
        v.addWidget(hint)
        v.addWidget(self.problem)

        buttons = QDialogButtonBox()
        self.add_btn = buttons.addButton("Add species", QDialogButtonBox.ButtonRole.AcceptRole)
        self.add_btn.setProperty("variant", "primary")
        self.add_btn.setDefault(True)
        buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self._add)
        buttons.rejected.connect(self.reject)
        v.addWidget(buttons)
        self._suggest_group()
        (self.common if scientific else self.scientific).setFocus()  # the name still missing

    def _suggest_group(self) -> None:
        """Until you choose a group, take the one of a species in the same genus."""
        if self._group_chosen:
            return
        suggested = self.catalogue.suggested_category(self.scientific.text())
        if suggested is not None:
            self.group.setCurrentIndex(max(0, self.group.findData(suggested)))

    def _add(self) -> None:
        try:
            self.taxon = self.catalogue.add_species(
                self.scientific.text(), self.common.text(), self.group.currentData()
            )
        except ValidationError as exc:
            self.problem.setText(" ".join(exc.fields.values()))
            self.problem.show()
            self.scientific.setFocus()
            return
        self.accept()
