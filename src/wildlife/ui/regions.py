"""Choosing where you record, and adding a US state's species pack (docs/16-regions-plan.md).

AddPackDialog lists the packs Thicket offers (from the internet, in the background),
then downloads, checks and installs the one you choose, with progress. Nothing changes
if anything goes wrong. Used from Settings › Region and the first-run welcome.
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QProgressBar,
    QVBoxLayout,
    QWidget,
)

from wildlife.context import AppContext
from wildlife.domain.errors import WildlifeError
from wildlife.services.species_packs import Pack
from wildlife.ui.components.visuals import plural
from wildlife.ui.workers import run_in_background

UK_NAME = "United Kingdom"


def region_name(ctx: AppContext, region: str) -> str:
    """'United Kingdom', 'California'…"""
    names = {p["region"]: p["name"] for p in ctx.catalogue.packs()}
    return names.get(region, UK_NAME if region == "uk" else region)


def describe(pack: Pack) -> str:
    size = (
        f"{pack.bytes / 1e6:.1f} MB"
        if pack.bytes >= 1e6
        else f"{max(1, round(pack.bytes / 1e3))} KB"
    )
    return f"{pack.name}  ·  {pack.species:,} species  ·  {size}"


def problem_text(exc: BaseException) -> str:
    if isinstance(exc, WildlifeError):
        return exc.user_message
    return "Something went wrong. Nothing was changed; details are in the log."


class AddPackDialog(QDialog):
    """Add a US state's species: choose it, then it's downloaded, checked and installed."""

    def __init__(self, ctx: AppContext, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.ctx = ctx
        self.installed_region: str | None = None
        self._busy = False
        self.setWindowTitle("Add a US state")
        self.setMinimumSize(480, 480)
        v = QVBoxLayout(self)
        v.setContentsMargins(20, 18, 20, 16)
        v.setSpacing(10)
        intro = QLabel(
            "Species recorded in a state, with their American names, from GBIF (the Global "
            "Biodiversity Information Facility). Downloaded once; the UK list stays as it is."
        )
        intro.setWordWrap(True)
        intro.setProperty("role", "muted")
        v.addWidget(intro)
        self.filter = QLineEdit()
        self.filter.setPlaceholderText("Type to find a state")
        self.filter.setAccessibleName("Find a state")
        self.filter.textChanged.connect(self._filter)
        v.addWidget(self.filter)
        self.list = QListWidget()
        self.list.setAccessibleName("US states")
        self.list.itemDoubleClicked.connect(lambda _item: self._install())
        self.list.currentItemChanged.connect(lambda *_: self._update_buttons())
        v.addWidget(self.list, 1)
        self.use_it = QCheckBox("Use it as my region (its names and suggestions)")
        self.use_it.setChecked(True)
        v.addWidget(self.use_it)
        self.progress = QProgressBar()
        self.progress.setRange(0, 100)
        self.progress.setTextVisible(False)
        self.progress.hide()
        v.addWidget(self.progress)
        self.status = QLabel("Getting the list of states…")
        self.status.setWordWrap(True)
        self.status.setProperty("role", "muted")
        v.addWidget(self.status)
        self.buttons = QDialogButtonBox()
        self.add_btn = self.buttons.addButton(
            "Download and add", QDialogButtonBox.ButtonRole.AcceptRole
        )
        self.add_btn.setProperty("variant", "primary")
        self.add_btn.clicked.connect(self._install)
        self.buttons.addButton(QDialogButtonBox.StandardButton.Cancel)
        self.buttons.rejected.connect(self.reject)
        v.addWidget(self.buttons)
        self._update_buttons()
        run_in_background(self.ctx.species_packs.offered, on_done=self._show, on_error=self._failed)

    def _show(self, packs: list[Pack]) -> None:
        installed = {p["region"]: p["version"] for p in self.ctx.catalogue.packs()}
        for pack in packs:
            text = describe(pack)
            if pack.region in installed:
                text += "  ·  added" + (
                    "" if installed[pack.region] == pack.version else ": update available"
                )
            item = QListWidgetItem(text)
            item.setData(Qt.ItemDataRole.UserRole, pack)
            self.list.addItem(item)
        self.status.setText(f"{plural(len(packs), 'state')}. Choose one, then Download and add.")
        self._update_buttons()

    def _failed(self, exc: BaseException) -> None:
        self.status.setText(problem_text(exc))
        self.status.setProperty("role", "error")
        self.status.style().polish(self.status)

    def _filter(self, text: str) -> None:
        wanted = text.strip().lower()
        for i in range(self.list.count()):
            item = self.list.item(i)
            item.setHidden(bool(wanted) and wanted not in item.text().lower())

    def _chosen(self) -> Pack | None:
        item = self.list.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item and not item.isHidden() else None

    def _update_buttons(self) -> None:
        self.add_btn.setEnabled(self._chosen() is not None and not self._busy)

    def _install(self) -> None:
        pack = self._chosen()
        if pack is None or self._busy:
            return
        self._busy = True
        self._update_buttons()
        self.list.setEnabled(False)
        self.progress.show()

        def progress(step: str, fraction: float) -> None:
            self.progress.setValue(int(fraction * 100))
            self.status.setText(step + "…")

        def done(count: int) -> None:
            self._busy = False
            self.installed_region = pack.region
            if self.use_it.isChecked():
                self.ctx.catalogue.set_region(pack.region)
            self.accept()

        def failed(exc: BaseException) -> None:
            self._busy = False
            self.list.setEnabled(True)
            self.progress.hide()
            self._failed(exc)
            self._update_buttons()

        run_in_background(
            lambda report: self.ctx.species_packs.install(pack, report),
            on_done=done,
            on_error=failed,
            on_progress=progress,
        )

    def reject(self) -> None:  # not while a pack is being installed: it finishes first
        if not self._busy:
            super().reject()
