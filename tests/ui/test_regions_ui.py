"""Choosing where you record (docs/16-regions-plan.md, step 3): Settings › Region, the
"Add a US state" dialog and the first-run welcome. The internet is pretend
(helpers.serve_us_pack)."""

from PySide6.QtWidgets import QApplication, QComboBox, QPushButton

from helpers import MINI_CATALOGUE, serve_us_pack
from wildlife.data.repositories import taxa as taxa_repo
from wildlife.ui.dialogs import FirstRunDialog
from wildlife.ui.regions import AddPackDialog


def add_california(window, qtbot, use_it=True) -> AddPackDialog:
    serve_us_pack(window.ctx)
    dialog = AddPackDialog(window.ctx, window)
    qtbot.waitUntil(lambda: dialog.list.count() == 1, timeout=10_000)
    assert dialog.list.item(0).text().startswith("California  ·  5 species")
    dialog.use_it.setChecked(use_it)
    dialog.list.setCurrentRow(0)
    dialog._install()
    qtbot.waitUntil(lambda: dialog.installed_region == "us-ca", timeout=10_000)
    return dialog


def test_adding_a_state_installs_it_and_shows_its_names(window, qtbot):
    add_california(window, qtbot)
    ctx = window.ctx
    assert ctx.catalogue.region() == "us-ca"
    assert ctx.catalogue.search("robin")[0].taxon.display_name == "American Robin"
    assert {p["region"] for p in ctx.catalogue.packs()} == {"uk", "us-ca"}


def test_a_state_can_be_added_without_switching_to_it(window, qtbot):
    add_california(window, qtbot, use_it=False)
    assert window.ctx.catalogue.region() == "uk"


def test_settings_switches_between_the_regions_added(window, qtbot):
    add_california(window, qtbot, use_it=False)
    page = window.settings_page
    page.refresh()
    # the newest one: refreshing replaces the page, and Qt deletes the old one a moment later
    menus = [c for c in page.findChildren(QComboBox) if c.accessibleName() == "Where you record"]
    menu = menus[-1]
    assert [menu.itemText(i) for i in range(menu.count())] == ["United Kingdom", "California"]
    page._choose_region("us-ca")
    assert window.ctx.catalogue.region() == "us-ca"
    page._choose_region("uk")
    assert window.ctx.catalogue.search("robin")[0].taxon.display_name == "Robin"
    assert any(b.text() == "Add a US state…" for b in page.findChildren(QPushButton))


def test_no_internet_in_the_dialog_is_explained(window, qtbot):
    window.ctx.settings.update(allow_online=False)
    dialog = AddPackDialog(window.ctx, window)
    qtbot.waitUntil(lambda: "Allow online features" in dialog.status.text(), timeout=10_000)
    assert not dialog.add_btn.isEnabled()
    dialog.reject()


def _welcome(ctx, monkeypatch, qtbot) -> FirstRunDialog:
    def quick_uk_list(report=lambda s, f: None):  # the real one is 106,000 species
        with ctx.db.transaction() as conn:
            return taxa_repo.install_catalogue(conn, MINI_CATALOGUE, version="test")

    monkeypatch.setattr(ctx.catalogue, "install", quick_uk_list)
    from wildlife.ui.theme.manager import ThemeManager

    dialog = FirstRunDialog(ctx, ThemeManager(QApplication.instance(), ctx.settings.current.theme))
    qtbot.addWidget(dialog)
    while dialog.pages.currentIndex() != dialog.region_index:
        dialog._next()
    return dialog


def test_the_welcome_can_set_up_a_us_state(ctx, monkeypatch, qtbot):
    serve_us_pack(ctx)
    dialog = _welcome(ctx, monkeypatch, qtbot)
    qtbot.waitUntil(lambda: dialog.state.count() == 1, timeout=10_000)
    dialog.in_us.setChecked(True)
    dialog._next()  # to the install page: the UK list, then California
    qtbot.waitUntil(lambda: dialog.next_btn.isEnabled(), timeout=15_000)
    assert "California" in dialog.progress_text.text()
    assert ctx.catalogue.region() == "us-ca"


def test_the_welcome_carries_on_with_the_uk_without_internet(ctx, monkeypatch, qtbot):
    ctx.settings.update(allow_online=False)
    dialog = _welcome(ctx, monkeypatch, qtbot)
    qtbot.waitUntil(lambda: not dialog.in_us.isEnabled(), timeout=10_000)
    assert "Settings › Region" in dialog.state_note.text()
    dialog._next()
    qtbot.waitUntil(lambda: dialog.next_btn.isEnabled(), timeout=15_000)
    assert ctx.catalogue.region() == "uk"
