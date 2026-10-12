"""UI tests for the iNaturalist import window (invented rows; the internet is faked)."""

from helpers import inat_csv, inat_row, taxon_id
from wildlife.domain.filters import SightingFilter
from wildlife.ui.imports.inaturalist_dialog import InatImportDialog


def export(tmp_path):
    path = tmp_path / "observations-1.csv"
    rows = [
        inat_row(1),
        inat_row(2, "Rubus fruticosus", iconic_taxon_name="Plantae"),
        inat_row(3, "Sphecodogastra", iconic_taxon_name="Insecta"),
        inat_row(4, observed_on_string="", observed_on="", time_observed_at=""),
    ]
    path.write_text(inat_csv(rows), encoding="utf-8")
    return path


def open_and_read(window, qtbot, tmp_path) -> InatImportDialog:
    window.settings_page.import_inaturalist.emit()
    dialog = window.findChildren(InatImportDialog)[-1]
    dialog.open_file(export(tmp_path))
    qtbot.waitUntil(lambda: dialog.pages.currentIndex() == 1, timeout=10_000)
    return dialog


def test_check_page_explains_what_will_happen(window, qtbot, tmp_path):
    window.ctx.settings.update(allow_online=False)
    dialog = open_and_read(window, qtbot, tmp_path)
    assert (
        "<b>3</b> new" in dialog.summary.text() and "1 can't be imported" in dialog.summary.text()
    )
    assert dialog.go_btn.text() == "Import 2 sightings"  # the unmatched name isn't counted yet
    assert (
        not dialog.photos_box.isEnabled() and "Allow online features" in dialog.photos_note.text()
    )
    dialog._choose(
        "Sphecodogastra", window.ctx.catalogue.get(taxon_id(window.ctx, "Beetlus obscurus"))
    )
    assert dialog.go_btn.text() == "Import 3 sightings"
    dialog.reject()


def test_import_toast_undo_and_show_imported(window, qtbot, tmp_path):
    window.ctx.settings.update(allow_online=False)
    dialog = open_and_read(window, qtbot, tmp_path)
    dialog._import()
    qtbot.waitUntil(lambda: dialog.result is not None, timeout=10_000)
    assert dialog.done_title.text() == "Imported"
    assert any("iNaturalist import: 2 added" in m for m in window.toasts.messages())
    batch = dialog.result.batch_id
    dialog._view()
    assert window.current_page() == "sightings"
    assert window.sightings_page.model.filter == SightingFilter(import_batch_id=batch)
    assert window.sightings_page.model.total == 2


def test_undo_from_the_window(window, qtbot, tmp_path):
    window.ctx.settings.update(allow_online=False)
    dialog = open_and_read(window, qtbot, tmp_path)
    dialog._import()
    qtbot.waitUntil(lambda: dialog.result is not None, timeout=10_000)
    dialog._undo()
    assert dialog.done_title.text() == "Import undone"
    assert window.ctx.sightings.totals(SightingFilter())[0] == 0
    dialog.reject()


def test_a_wrong_file_is_explained(window, qtbot, tmp_path):
    window.settings_page.import_inaturalist.emit()
    dialog = window.findChildren(InatImportDialog)[-1]
    wrong = tmp_path / "list.csv"
    wrong.write_text("species,date\nRobin,2026-05-03\n", encoding="utf-8")
    dialog.open_file(wrong)
    qtbot.waitUntil(lambda: "iNaturalist" in dialog.choose_status.text(), timeout=10_000)
    assert dialog.pages.currentIndex() == 0 and dialog.choose_btn.isEnabled()
    dialog.reject()
