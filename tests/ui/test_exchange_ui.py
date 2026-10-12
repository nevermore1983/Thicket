"""UI tests for importing, exporting, the health check and restoring (invented data)."""

from helpers import inat_csv, inat_row, taxon_id
from wildlife.domain.filters import SightingFilter
from wildlife.ui.exchange.import_dialog import CHECK, CHOOSE, MAP, ImportDialog


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


def open_and_read(window, qtbot, tmp_path) -> ImportDialog:
    dialog = window.import_data("inaturalist")
    dialog.open_file(export(tmp_path))
    qtbot.waitUntil(lambda: dialog.pages.currentIndex() == CHECK, timeout=10_000)
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
    qtbot.waitUntil(lambda: dialog.outcome is not None, timeout=10_000)
    assert dialog.done_title.text() == "Imported"
    assert any("Import (iNaturalist): 2 added" in m for m in window.toasts.messages())
    batch = dialog.outcome.batch_id
    dialog._view()
    assert window.current_page() == "sightings"
    assert window.sightings_page.model.filter == SightingFilter(import_batch_id=batch)
    assert window.sightings_page.model.total == 2


def test_undo_from_the_window(window, qtbot, tmp_path):
    window.ctx.settings.update(allow_online=False)
    dialog = open_and_read(window, qtbot, tmp_path)
    dialog._import()
    qtbot.waitUntil(lambda: dialog.outcome is not None, timeout=10_000)
    dialog._undo()
    assert dialog.done_title.text() == "Import undone"
    assert window.ctx.sightings.totals(SightingFilter())[0] == 0
    dialog.reject()


def test_a_wrong_file_is_explained(window, qtbot, tmp_path):
    dialog = window.import_data("inaturalist")
    wrong = tmp_path / "list.csv"
    wrong.write_text("species,date\nRobin,2026-05-03\n", encoding="utf-8")
    dialog.open_file(wrong)
    qtbot.waitUntil(lambda: "iNaturalist" in dialog.choose_status.text(), timeout=10_000)
    assert dialog.pages.currentIndex() == CHOOSE and dialog.choose_btn.isEnabled()
    dialog.reject()


# ---- spreadsheets and WildLife exports ---------------------------------------------------
def test_spreadsheet_columns_are_matched_then_checked(window, qtbot, tmp_path):
    sheet = tmp_path / "my records.csv"
    sheet.write_text("Bird,When,Where,How many\nRobin,03/05/2026,Garden,2\n", encoding="utf-8")
    dialog = window.import_data("csv")
    dialog.open_file(sheet)
    qtbot.waitUntil(lambda: dialog.pages.currentIndex() == MAP, timeout=10_000)
    assert not dialog.go_btn.isEnabled()  # no column recognised as the species or date yet
    dialog.combos["species"].setCurrentIndex(1)  # "Bird"
    dialog.combos["date"].setCurrentIndex(2)  # "When"
    assert dialog.go_btn.isEnabled() and dialog.mapping() == {
        "species": 0,
        "date": 1,
        "location_text": 2,  # "Where" and "How many" were recognised
        "count": 3,
    }
    dialog._go()
    qtbot.waitUntil(lambda: dialog.pages.currentIndex() == CHECK, timeout=10_000)
    assert dialog.go_btn.text() == "Import 1 sighting"
    dialog._import()
    qtbot.waitUntil(lambda: dialog.outcome is not None, timeout=10_000)
    assert window.ctx.sightings.totals(SightingFilter())[0] == 1
    dialog.reject()


def test_wildlife_export_comes_back_in(window, qtbot, tmp_path):
    from datetime import date

    from wildlife.domain.models import SightingDraft
    from wildlife.services.export import ExportOptions

    window.ctx.sightings.save(
        SightingDraft(taxon_id(window.ctx, "Vulpes vulpes"), date(2026, 5, 3))
    )
    path = window.ctx.export.export(ExportOptions("archive"), tmp_path / "all").path
    window.ctx.sightings.delete([s.id for s in window.ctx.sightings.page(SightingFilter())])
    window.ctx.sightings.purge_recycle_bin(0)
    dialog = window.import_data("wildlife")
    dialog.open_file(path)
    qtbot.waitUntil(lambda: dialog.pages.currentIndex() == CHECK, timeout=10_000)
    assert "<b>1</b> new sightings" in dialog.summary.text()
    assert not dialog.photos_box.isVisibleTo(dialog)
    dialog._import()
    qtbot.waitUntil(lambda: dialog.outcome is not None, timeout=10_000)
    assert window.ctx.sightings.totals(SightingFilter())[0] == 1
    dialog.reject()


# ---- export -------------------------------------------------------------------------------
def test_export_window(window, qtbot, tmp_path):
    from datetime import date

    from wildlife.domain.models import SightingDraft

    for name in ("Vulpes vulpes", "Erithacus rubecula"):
        window.ctx.sightings.save(SightingDraft(taxon_id(window.ctx, name), date(2026, 5, 3)))
    fox = SightingFilter(taxon_ids=frozenset({taxon_id(window.ctx, "Vulpes vulpes")}))
    dialog = window.export_data(fox)
    assert dialog.scope_shown.text() == "The sightings shown now (1)"
    dialog.formats["json"].setChecked(True)
    assert not dialog.sharing.isEnabled()  # complete formats are always exact
    dialog.formats["dwc"].setChecked(True)
    dialog.blur.changed.emit("1000")
    options = dialog.options()
    assert (options.format, options.blur_m, options.flt) == ("dwc", 1000, fox)
    dialog.export_to(tmp_path / "fox.csv", options)
    qtbot.waitUntil(lambda: dialog.summary is not None, timeout=10_000)
    assert dialog.status.text() == "Saved fox.csv: 1 sighting." and dialog.open_btn.isVisibleTo(
        dialog
    )
    dialog.reject()


def test_sightings_page_exports_what_it_shows(window, qtbot):
    flt = SightingFilter(months=frozenset({5}))
    window.show_sightings(flt)
    exported = []
    window.sightings_page.export_requested.connect(exported.append)
    window.sightings_page.export_requested.emit(window.sightings_page.model.filter)
    assert exported == [flt]


# ---- health check and restore ---------------------------------------------------------------
def test_health_check_window(window, qtbot):
    from wildlife.ui.maintenance.health_dialog import HealthDialog

    dialog = window.health_check()
    assert isinstance(dialog, HealthDialog)
    qtbot.waitUntil(lambda: dialog.report is not None, timeout=10_000)
    assert dialog.title.text() == "Some things need attention"  # no backup yet
    asked = []
    dialog.backup_requested.connect(lambda: asked.append(True))
    dialog._fix("backup_now")
    assert asked == [True]
    dialog.reject()


def test_restore_window_asks_for_a_restart(window, qtbot, monkeypatch):
    from wildlife.data.restore import pending

    window.ctx.backup.backup_now("manual")
    restarts = []
    monkeypatch.setattr(window, "restart_to_restore", lambda: restarts.append(True))
    dialog = window.restore_backup()
    dialog.restart_requested.disconnect()
    dialog.restart_requested.connect(window.restart_to_restore)
    assert dialog.list.count() == 1 and "made by you" in dialog.list.item(0).text()
    dialog.restore(dialog.list.item(0).data(256), confirm=False)
    assert restarts == [True] and pending(window.ctx.paths) is not None
    from wildlife.data.restore import cancel_restore

    cancel_restore(window.ctx.paths)


def test_settings_lists_imports_with_show_and_remove(window, qtbot, tmp_path):
    window.ctx.settings.update(allow_online=False)
    dialog = open_and_read(window, qtbot, tmp_path)
    dialog._import()
    qtbot.waitUntil(lambda: dialog.outcome is not None, timeout=10_000)
    dialog.reject()
    window.go("settings")
    window.settings_page.refresh()
    texts = [label.text() for label in window.settings_page.findChildren(type(dialog.summary))]
    assert any(t.startswith("Imported ") and t.endswith("· iNaturalist") for t in texts)


def test_bulk_change_menu(window, qtbot, monkeypatch):
    from datetime import date

    from wildlife.domain.models import PlaceDraft, SightingDraft

    garden = window.ctx.places.save(PlaceDraft("Garden", 51.4, 0.1))
    for name in ("Vulpes vulpes", "Erithacus rubecula"):
        window.ctx.sightings.save(SightingDraft(taxon_id(window.ctx, name), date(2026, 5, 3)))
    window.show_sightings(SightingFilter())
    page = window.sightings_page
    page.table.selectAll()
    change = next(b for b in page.bulk.findChildren(type(page.add_btn)) if b.menu())
    actions = [a.text() for a in change.menu().actions()]
    assert actions == ["Species…", "Place…", "Date…", "Outing…"]

    def choose_garden(title, *widgets):
        widgets[1].setCurrentIndex(widgets[1].findData(garden.id))
        return True

    monkeypatch.setattr(page, "_ask", choose_garden)
    page._change_place()
    assert {s.place_id for s in window.ctx.sightings.page(SightingFilter())} == {garden.id}
    assert any("moved to Garden" in m for m in window.toasts.messages())
