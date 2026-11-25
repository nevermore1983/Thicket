"""Choosing where you record (docs/16-regions-plan.md, step 3): Settings › Region, the
"Add a US state" dialog and the first-run welcome. The internet is pretend
(helpers.serve_us_pack)."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QComboBox, QPushButton

from helpers import FRANCE_PACK, MINI_CATALOGUE, US_PACK, serve_packs, serve_us_pack
from wildlife.data.repositories import taxa as taxa_repo
from wildlife.ui.dialogs import FirstRunDialog
from wildlife.ui.regions import AddPackDialog


def add_california(window, qtbot, use_it=True) -> AddPackDialog:
    serve_us_pack(window.ctx)
    dialog = AddPackDialog(window.ctx, window)
    qtbot.waitUntil(lambda: dialog.list.count() == 2, timeout=10_000)
    assert dialog.list.item(0).text() == "United States"  # a heading, not a choice
    assert dialog.list.item(1).text().strip().startswith("California  ·  5 species  ·  ")
    assert dialog.list.item(1).text().endswith(" KB") and dialog.status.text().startswith(
        "1 region."
    )
    dialog.use_it.setChecked(use_it)
    dialog.list.setCurrentRow(1)
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
    assert any(b.text() == "Add a region…" for b in page.findChildren(QPushButton))


def test_no_internet_in_the_dialog_is_explained(window, qtbot):
    window.ctx.settings.update(allow_online=False)
    dialog = AddPackDialog(window.ctx, window)
    qtbot.waitUntil(lambda: "Allow online features" in dialog.status.text(), timeout=10_000)
    assert not dialog.add_btn.isEnabled()
    dialog.reject()


def _welcome(ctx, monkeypatch, qtbot, country=None) -> FirstRunDialog:
    def quick_uk_list(report=lambda s, f: None):  # the real one is 106,000 species
        with ctx.db.transaction() as conn:
            return taxa_repo.install_catalogue(conn, MINI_CATALOGUE, version="test")

    monkeypatch.setattr(ctx.catalogue, "install", quick_uk_list)
    from wildlife.ui.theme.manager import ThemeManager

    theme = ThemeManager(QApplication.instance(), ctx.settings.current.theme)
    dialog = FirstRunDialog(ctx, theme, country=country)
    qtbot.addWidget(dialog)
    while dialog.pages.currentIndex() != dialog.region_index:
        dialog._next()
    return dialog


def test_choosing_the_uk_never_goes_online(ctx, monkeypatch, qtbot):
    """The privacy page promises GitHub is asked only when you add a state."""
    asked = []
    monkeypatch.setattr(ctx.species_packs, "offered", lambda *a: asked.append(True) or [])
    dialog = _welcome(ctx, monkeypatch, qtbot)
    dialog._next()
    qtbot.waitUntil(lambda: dialog.next_btn.isEnabled(), timeout=15_000)
    assert asked == [] and ctx.catalogue.region() == "uk"


# ---- step 4: the rest of Thicket follows the region ----------------------------------
def test_the_map_follows_the_region(window):
    from PySide6.QtCore import QSettings

    page = window.map_page
    page.set_mode("squares")
    QSettings().setValue("map/camera", {"lat": 51.5, "lon": -0.1, "zoom": 9})
    window.ctx.catalogue.set_region("us-oh")
    page.refresh()
    assert page.modes.button_for("squares").isHidden()  # the British National Grid: UK only
    assert page.mode == "pins"
    assert QSettings().value("map/camera") is None  # it opens on Ohio next time
    window.ctx.catalogue.set_region("uk")
    page.refresh()
    assert not page.modes.button_for("squares").isHidden()


def test_a_us_position_is_shown_as_coordinates(window):
    window.add_sighting()
    editor = window.panel.current()
    editor.location.setText("40.10000, -83.00000")  # Ohio
    editor._on_location_edited("")
    editor._update_location_note()
    note = editor.f_location.note.text()
    assert "40.10000, -83.00000" in note and "GB grid" not in note
    editor._dirty = False
    window.panel.close_panel()


def test_spreadsheet_import_starts_with_the_regions_date_order(window):
    window.ctx.catalogue.set_region("us-oh")
    dialog = window.import_data("csv")
    assert dialog.month_first()
    dialog.reject()
    window.ctx.catalogue.set_region("uk")
    dialog = window.import_data("csv")
    assert not dialog.month_first()
    dialog.reject()


def test_gbif_is_credited_once_a_state_is_added(window, qtbot):
    from PySide6.QtWidgets import QLabel

    def credits() -> str:
        window.settings_page.refresh()
        return " ".join(label.text() for label in window.settings_page.findChildren(QLabel))

    assert "GBIF.org" not in credits()
    add_california(window, qtbot)
    assert "Species packs (1): GBIF.org" in credits()


# ---- Europe (docs/23-europe-packs-plan.md) --------------------------------------------
def serve_france_and_california(ctx) -> None:
    serve_packs(ctx, [("fr", "France", FRANCE_PACK), ("us-ca", "California", US_PACK)])


def test_the_list_has_europe_and_the_us_under_headings(window, qtbot):
    serve_france_and_california(window.ctx)
    dialog = AddPackDialog(window.ctx, window)
    qtbot.waitUntil(lambda: dialog.list.count() == 4, timeout=10_000)
    texts = [dialog.list.item(i).text().strip() for i in range(4)]
    assert texts[0] == "Europe" and texts[1].startswith("France")
    assert texts[2] == "United States" and texts[3].startswith("California")
    dialog.filter.setText("fra")  # finds France; the US heading goes with its states
    hidden = [dialog.list.item(i).isHidden() for i in range(4)]
    assert hidden == [False, False, True, True]
    dialog.reject()


def test_adding_france_shows_english_names_and_finds_french_ones(window, qtbot):
    serve_france_and_california(window.ctx)
    dialog = AddPackDialog(window.ctx, window)
    qtbot.waitUntil(lambda: dialog.list.count() == 4, timeout=10_000)
    dialog.list.setCurrentRow(1)
    dialog._install()
    qtbot.waitUntil(lambda: dialog.installed_region == "fr", timeout=10_000)
    catalogue = window.ctx.catalogue
    assert catalogue.region() == "fr"
    redstart = catalogue.search("rougequeue")[0]
    assert redstart.taxon.display_name == "Black Redstart"
    assert redstart.matched_name == "Rougequeue noir"
    assert catalogue.search("rougegorge")[0].taxon.display_name == "Robin"
    # Linked, never copied: one Robin and one Red Fox, whichever pack they came from
    assert len({m.taxon.id for m in catalogue.search("Erithacus rubecula")}) == 1


# ---- Canada, Australia and New Zealand (docs/24-canada-australia-nz-plan.md) ---------


def test_the_list_has_canada_australia_and_new_zealand_under_headings(window, qtbot):
    serve_packs(
        window.ctx,
        [
            ("nz", "New Zealand", FRANCE_PACK),
            ("au-tas", "Tasmania", FRANCE_PACK),
            ("ca-on", "Ontario", US_PACK),
            ("us-ca", "California", US_PACK),
        ],
    )
    dialog = AddPackDialog(window.ctx, window)
    qtbot.waitUntil(lambda: dialog.list.count() == 8, timeout=10_000)
    headings = [dialog.list.item(i).text() for i in range(0, 8, 2)]
    assert headings == ["United States", "Canada", "Australia", "New Zealand"]
    dialog.reject()


# ---- Latin America and the Caribbean (docs/25-latin-america-caribbean-plan.md) -------


def test_the_list_has_latin_america_last_under_its_heading(window, qtbot):
    serve_packs(
        window.ctx,
        [("br", "Brazil", FRANCE_PACK), ("nz", "New Zealand", FRANCE_PACK)],
    )
    dialog = AddPackDialog(window.ctx, window)
    qtbot.waitUntil(lambda: dialog.list.count() == 4, timeout=10_000)
    headings = [dialog.list.item(i).text() for i in (0, 2)]
    assert headings == ["New Zealand", "Latin America and the Caribbean"]
    dialog.filter.setText("braz")
    assert not dialog.list.item(2).isHidden() and dialog.list.item(0).isHidden()
    dialog.reject()


# ---- Africa (docs/26-africa-plan.md) ---------------------------------------------------


def test_the_list_has_africa_last_under_its_heading(window, qtbot):
    serve_packs(
        window.ctx,
        [("za", "South Africa", FRANCE_PACK), ("br", "Brazil", FRANCE_PACK)],
    )
    dialog = AddPackDialog(window.ctx, window)
    qtbot.waitUntil(lambda: dialog.list.count() == 4, timeout=10_000)
    headings = [dialog.list.item(i).text() for i in (0, 2)]
    assert headings == ["Latin America and the Caribbean", "Africa"]
    dialog.filter.setText("south af")
    assert not dialog.list.item(3).isHidden() and dialog.list.item(1).isHidden()
    dialog.reject()


def test_the_search_ignores_accents_knows_other_names_and_says_when_nothing_is_found(window, qtbot):
    serve_packs(window.ctx, [("re", "Réunion", FRANCE_PACK), ("ci", "Côte d'Ivoire", FRANCE_PACK)])
    dialog = AddPackDialog(window.ctx, window)
    qtbot.waitUntil(lambda: dialog.list.count() == 3, timeout=10_000)
    ready = dialog.status.text()

    def shown() -> list[str]:  # the names showing, without the species and size
        return [
            dialog.list.item(i).text().strip().split("  ")[0]
            for i in range(3)
            if not dialog.list.item(i).isHidden()
        ]

    dialog.filter.setText("reunion")
    assert shown() == ["Africa", "Réunion"]
    dialog.filter.setText("Ivory Coast")
    assert shown() == ["Africa", "Côte d'Ivoire"]
    dialog.filter.setText("mb")  # the size on each line ("0.1 MB") isn't searched
    assert shown() == [] and "No region called “mb”" in dialog.status.text()
    assert not dialog.add_btn.isEnabled()
    dialog.filter.setText("Scotland")
    assert "built in: choose it in Settings › Region" in dialog.status.text()
    dialog.filter.setText("")
    assert len(shown()) == 3 and dialog.status.text() == ready
    dialog.reject()


def test_the_region_picker_on_its_own(qtbot):
    from wildlife.services.species_packs import Pack
    from wildlife.ui.regions import RegionPicker

    def made_up(region, name):
        return Pack(region, name, 120, 2_000_000, "0" * 64, f"https://example.test/{region}", "1")

    picker = RegionPicker("it's the first choice above")
    qtbot.addWidget(picker)
    notes, double_clicks = [], []
    picker.noted.connect(notes.append)
    picker.activated.connect(lambda: double_clicks.append(picker.chosen()))
    picker.filter.setText("ken")  # typed before the list is in: nothing said yet
    assert notes == []
    picker.set_packs([made_up("ke", "Kenya"), made_up("fr", "France")], {"fr": "1"})
    texts = [picker.list.item(i).text().strip() for i in range(4)]
    assert texts[0] == "Europe" and texts[1].endswith("·  added")
    assert texts[2] == "Africa" and texts[3].startswith("Kenya")
    assert [picker.list.item(i).isHidden() for i in range(4)] == [True, True, False, False]
    assert notes == [""]
    picker.list.setCurrentRow(3)
    assert picker.chosen().region == "ke"
    picker.list.itemDoubleClicked.emit(picker.list.item(3))
    picker.list.itemDoubleClicked.emit(picker.list.item(2))  # a heading: nothing happens
    assert [p.region for p in double_clicks] == ["ke"]
    picker.filter.setText("England")
    assert notes[-1] == "The UK's species list is built in: it's the first choice above."
    assert picker.chosen() is None  # Kenya is hidden now


# ---- the welcome: the UK, or somewhere else (docs/27-find-your-region-plan.md) --------
def _somewhere_else(dialog, qtbot, rows: int):
    """Choose "Somewhere else" and wait for the list (`rows` lines, headings included)."""
    dialog.elsewhere.setChecked(True)  # only now is the list of regions fetched
    qtbot.waitUntil(lambda: dialog.picker.list.count() == rows, timeout=10_000)
    assert dialog.picker.isVisible() or not dialog.isVisible()


def _pick(dialog, typed: str):
    """Type in the search and choose the first region it finds."""
    dialog.picker.filter.setText(typed)
    items = [dialog.picker.list.item(i) for i in range(dialog.picker.list.count())]
    first = next(i for i in items if not i.isHidden() and i.data(Qt.ItemDataRole.UserRole))
    dialog.picker.list.setCurrentItem(first)


def _installs(dialog, qtbot, name: str, region: str):
    dialog._next()  # to the install page: the UK list, then the region's pack
    qtbot.waitUntil(lambda: dialog.next_btn.isEnabled(), timeout=15_000)
    assert name in dialog.progress_text.text()
    assert dialog.ctx.catalogue.region() == region


def test_the_welcome_can_set_up_a_us_state(ctx, monkeypatch, qtbot):
    serve_us_pack(ctx)
    dialog = _welcome(ctx, monkeypatch, qtbot)
    assert dialog.in_uk.isChecked() and dialog.picker.isHidden()
    _somewhere_else(dialog, qtbot, 2)  # United States, California
    _pick(dialog, "calif")
    _installs(dialog, qtbot, "California", "us-ca")


def test_every_region_is_in_one_list_under_its_heading(ctx, monkeypatch, qtbot):
    serve_packs(
        ctx,
        [
            ("ke", "Kenya", FRANCE_PACK),
            ("cr", "Costa Rica", FRANCE_PACK),
            ("nz", "New Zealand", FRANCE_PACK),
            ("au-tas", "Tasmania", FRANCE_PACK),
            ("ca-on", "Ontario", US_PACK),
            ("fr", "France", FRANCE_PACK),
        ],
    )
    dialog = _welcome(ctx, monkeypatch, qtbot)
    _somewhere_else(dialog, qtbot, 12)
    headings = [dialog.picker.list.item(i).text() for i in range(0, 12, 2)]
    assert headings == [
        "Europe",
        "Canada",
        "Australia",
        "New Zealand",
        "Latin America and the Caribbean",
        "Africa",
    ]
    assert dialog.chosen_pack() is None  # no suggestion: nothing is chosen for you
    dialog._next()
    assert dialog.pages.currentIndex() == dialog.region_index
    assert "Choose your region first: type its name" in dialog.state_note.text()
    _pick(dialog, "costa")
    _installs(dialog, qtbot, "Costa Rica", "cr")


def test_a_double_click_goes_on_as_continue_does(ctx, monkeypatch, qtbot):
    serve_packs(ctx, [("ca-on", "Ontario", US_PACK), ("fr", "France", FRANCE_PACK)])
    dialog = _welcome(ctx, monkeypatch, qtbot)
    _somewhere_else(dialog, qtbot, 4)
    _pick(dialog, "ontario")
    dialog.picker.list.itemDoubleClicked.emit(dialog.picker.list.currentItem())
    qtbot.waitUntil(lambda: dialog.next_btn.isEnabled(), timeout=15_000)
    assert "Ontario" in dialog.progress_text.text() and ctx.catalogue.region() == "ca-on"


def test_the_welcome_waits_for_a_region_before_going_on(ctx, monkeypatch, qtbot):
    """Choosing somewhere else and pressing Continue before the list came used to install
    only the UK list, without a word."""
    dialog = _welcome(ctx, monkeypatch, qtbot)
    monkeypatch.setattr(dialog, "_ask_for_states", lambda: None)  # the list hasn't come yet
    dialog.elsewhere.setChecked(True)
    dialog._next()
    assert dialog.pages.currentIndex() == dialog.region_index
    assert "Choose your region first: the list is on its way" in dialog.state_note.text()


def test_the_welcome_carries_on_with_the_uk_without_internet(ctx, monkeypatch, qtbot):
    ctx.settings.update(allow_online=False)
    dialog = _welcome(ctx, monkeypatch, qtbot)
    dialog.elsewhere.setChecked(True)
    qtbot.waitUntil(lambda: not dialog.elsewhere.isEnabled(), timeout=10_000)
    assert dialog.in_uk.isChecked() and dialog.picker.isHidden()  # back, with the reason
    assert "Settings › Region" in dialog.state_note.text()
    dialog._next()
    qtbot.waitUntil(lambda: dialog.next_btn.isEnabled(), timeout=15_000)
    assert ctx.catalogue.region() == "uk"


def test_windows_country_is_suggested_but_the_uk_stays_chosen(ctx, monkeypatch, qtbot):
    asked = []
    serve_packs(ctx, [("ke", "Kenya", FRANCE_PACK), ("cr", "Costa Rica", FRANCE_PACK)])
    offered = ctx.species_packs.offered
    monkeypatch.setattr(ctx.species_packs, "offered", lambda *a: asked.append(1) or offered(*a))
    dialog = _welcome(ctx, monkeypatch, qtbot, country="KE")
    assert dialog.in_uk.isChecked() and asked == []  # nothing fetched for the suggestion
    _somewhere_else(dialog, qtbot, 4)
    assert dialog.chosen_pack().region == "ke"
    assert dialog.state_note.text() == (
        "Kenya is chosen, as Windows is set to it. Type to find another region."
    )
    dialog.picker.filter.setText("cos")  # typing: the suggestion's note goes
    assert dialog.state_note.text() == "" and dialog.chosen_pack() is None
    _pick(dialog, "costa")
    _installs(dialog, qtbot, "Costa Rica", "cr")


def test_a_country_with_several_packs_opens_at_its_heading(ctx, monkeypatch, qtbot):
    serve_packs(ctx, [("us-ca", "California", US_PACK), ("fr", "France", FRANCE_PACK)])
    dialog = _welcome(ctx, monkeypatch, qtbot, country="US")
    _somewhere_else(dialog, qtbot, 4)
    assert dialog.chosen_pack() is None  # you choose your own state
    assert dialog.state_note.text() == (
        "Windows is set to the United States: choose your state below."
    )


@pytest.mark.parametrize("country", ["GB", "IN", None])
def test_no_suggestion_for_the_uk_or_a_country_without_a_pack(ctx, monkeypatch, qtbot, country):
    serve_packs(ctx, [("ke", "Kenya", FRANCE_PACK)])
    dialog = _welcome(ctx, monkeypatch, qtbot, country=country)
    _somewhere_else(dialog, qtbot, 2)
    assert dialog.chosen_pack() is None and dialog.state_note.text() == ""


def test_typing_the_uk_says_where_it_is(ctx, monkeypatch, qtbot):
    serve_packs(ctx, [("ke", "Kenya", FRANCE_PACK)])
    dialog = _welcome(ctx, monkeypatch, qtbot)
    _somewhere_else(dialog, qtbot, 2)
    dialog.picker.filter.setText("England")
    assert dialog.state_note.text() == (
        "The UK's species list is built in: it's the first choice above."
    )
