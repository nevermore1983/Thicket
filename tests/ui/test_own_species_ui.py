"""The picker's "Add … as your own species", its form, and Settings › About › Feedback."""

from PySide6.QtWidgets import QPushButton

from wildlife.ui.components.species_picker import NEW_SPECIES
from wildlife.ui.own_species import AddSpeciesDialog
from wildlife.ui.panels.sighting_editor import SightingEditor


def editor(window) -> SightingEditor:
    window.add_sighting()
    return window.panel.current()


def test_the_picker_always_offers_to_add_a_species_last(window, qtbot):
    picker = editor(window).picker
    picker.edit.setText("robin")
    picker._refresh()
    assert picker.list.currentRow() == 0  # Enter still picks the best match
    last = picker.list.item(picker.list.count() - 1)
    assert last.data(0x0100) == NEW_SPECIES and "“robin” as your own species" in last.text()
    picker.edit.setText("zzzzz")
    picker._refresh()
    assert picker.list.currentRow() == -1  # no match: Enter doesn't open the form


def test_choosing_it_adds_the_species_and_picks_it(window, qtbot, monkeypatch):
    def fill_in(dialog):
        dialog.common.setText("Japanese Robin")
        dialog._add()
        return dialog.result()

    monkeypatch.setattr(AddSpeciesDialog, "exec", fill_in)
    form = editor(window)
    form.picker.edit.setText("Erithacus akahige")
    form.picker._refresh()
    form.picker._pick(NEW_SPECIES)
    assert form.picker.taxon is not None and form.picker.taxon.common_name == "Japanese Robin"


def test_the_form_guesses_which_name_you_typed(window):
    catalogue = window.ctx.catalogue
    by_scientific = AddSpeciesDialog(catalogue, "Erithacus akahige", window)
    assert by_scientific.scientific.text() == "Erithacus akahige"
    assert by_scientific.group.currentText() == "Bird"  # from its genus
    by_common = AddSpeciesDialog(catalogue, "Japanese robin", window)
    assert by_common.common.text() == "Japanese robin" and by_common.scientific.text() == ""
    by_common._add()
    assert by_common.problem.isVisibleTo(by_common) and by_common.taxon is None
    for dialog in (by_scientific, by_common):
        dialog.deleteLater()


def test_feedback_buttons_open_githubs_forms(window, monkeypatch):
    from wildlife.ui.pages import settings_page

    opened = []
    monkeypatch.setattr(settings_page.QDesktopServices, "openUrl", lambda url: opened.append(url))
    window.go("settings")
    page = window.settings_page
    for text in ("Report a problem…", "Suggest an idea…"):
        next(b for b in page.findChildren(QPushButton) if b.text() == text).click()
    assert [u.toString().split("template=")[1].split("&")[0] for u in opened] == [
        "problem.yml",
        "idea.yml",
    ]
