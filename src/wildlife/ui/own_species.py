"""Add a species of your own: one that isn't in your species list (an escape, a new
arrival, a species from a region whose pack you haven't added). Opened from the species
picker's last suggestion, "Add … as your own species"."""

from __future__ import annotations

import re

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from wildlife.domain.errors import ValidationError, WildlifeError
from wildlife.domain.models import Taxon
from wildlife.services.species_catalogue import SpeciesCatalogue

# Two or more words, the first capitalised and the rest lower case: a scientific name
_LOOKS_SCIENTIFIC = re.compile(r"^[A-Z][a-z]+(?: [a-z][a-z.-]+)+$")


class AddSpeciesDialog(QDialog):
    """`taxon` holds the new species once it's added."""

    def __init__(
        self,
        catalogue: SpeciesCatalogue,
        typed: str,
        parent: QWidget | None = None,
        editing: Taxon | None = None,  # correct one you added, instead of adding
    ):
        super().__init__(parent)
        self.catalogue, self.editing = catalogue, editing
        self.taxon: Taxon | None = None
        self._group_chosen = editing is not None
        self.setWindowTitle("Add your own species" if editing is None else "Change your species")
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

        if editing is not None:
            self.common.setText(editing.common_name or "")
            self.scientific.setText(editing.scientific_name)
            self.group.setCurrentIndex(max(0, self.group.findData(editing.category_id)))
            intro.setText("Its sightings follow the new names and group.")
        buttons = QDialogButtonBox()
        label = "Add species" if editing is None else "Save"
        self.add_btn = buttons.addButton(label, QDialogButtonBox.ButtonRole.AcceptRole)
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
        names = (self.scientific.text(), self.common.text(), self.group.currentData())
        try:
            if self.editing is None:
                self.taxon = self.catalogue.add_species(*names)
            else:
                self.taxon = self.catalogue.rename_species(self.editing.id, *names)
        except ValidationError as exc:
            self.problem.setText(" ".join(exc.fields.values()))
            self.problem.show()
            self.scientific.setFocus()
            return
        self.accept()


class OwnSpeciesDialog(QDialog):
    """Settings › Region › Your own species: change one's names or group, or remove one
    no sighting uses."""

    def __init__(self, catalogue: SpeciesCatalogue, parent: QWidget | None = None):
        super().__init__(parent)
        self.catalogue = catalogue
        self.changed = False
        self.setWindowTitle("Your own species")
        self.setMinimumSize(460, 380)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(10)
        self.list = QListWidget()
        self.list.setAccessibleName("Your own species")
        self.list.currentRowChanged.connect(lambda _row: self._update_buttons())
        self.list.itemDoubleClicked.connect(lambda _item: self._edit())
        v.addWidget(self.list, 1)
        self.problem = QLabel()
        self.problem.setWordWrap(True)
        self.problem.setProperty("role", "error")
        self.problem.hide()
        v.addWidget(self.problem)
        row = QHBoxLayout()
        self.edit_btn = QPushButton("Change…")
        self.edit_btn.clicked.connect(self._edit)
        self.remove_btn = QPushButton("Remove")
        self.remove_btn.setToolTip("Only a species no sighting uses (the recycle bin included)")
        self.remove_btn.clicked.connect(self._remove)
        row.addWidget(self.edit_btn)
        row.addWidget(self.remove_btn)
        row.addStretch(1)
        close = QPushButton("Close")
        close.clicked.connect(self.accept)
        row.addWidget(close)
        v.addLayout(row)
        self._fill()

    def _fill(self, select: int | None = None) -> None:
        self.list.clear()
        for taxon, uses in self.catalogue.own_species():
            name = (
                f"{taxon.common_name} ({taxon.scientific_name})"
                if taxon.common_name
                else taxon.scientific_name
            )
            item = QListWidgetItem(f"{name}  ·  {uses:,} sighting{'s' if uses != 1 else ''}")
            item.setData(Qt.ItemDataRole.UserRole, (taxon, uses))
            self.list.addItem(item)
            if taxon.id == select:
                self.list.setCurrentItem(item)
        if self.list.currentRow() < 0 and self.list.count():
            self.list.setCurrentRow(0)
        self._update_buttons()

    def _chosen(self) -> tuple[Taxon, int] | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _update_buttons(self) -> None:
        chosen = self._chosen()
        self.edit_btn.setEnabled(chosen is not None)
        self.remove_btn.setEnabled(chosen is not None and chosen[1] == 0)

    def _edit(self) -> None:
        chosen = self._chosen()
        if chosen is None:
            return
        form = AddSpeciesDialog(self.catalogue, "", self, editing=chosen[0])
        try:
            if form.exec() and form.taxon is not None:
                self.changed = True
                self._fill(select=form.taxon.id)
        finally:
            form.deleteLater()

    def _remove(self) -> None:
        chosen = self._chosen()
        if chosen is None:
            return
        try:
            self.catalogue.remove_species(chosen[0].id)
        except WildlifeError as exc:
            self.problem.setText(exc.user_message)
            self.problem.show()
            return
        self.changed = True
        self.problem.hide()
        self._fill()
