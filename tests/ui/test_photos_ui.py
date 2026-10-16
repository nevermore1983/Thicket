"""UI tests for the Photos page, the Inbox, the viewer and the photo grid."""

import shutil
from pathlib import Path

import pytest
from PySide6.QtCore import QMimeData, QPoint, QPointF, Qt, QUrl
from PySide6.QtGui import QDropEvent
from PySide6.QtWidgets import QFileDialog

from helpers import TODAY, taxon_id
from wildlife.domain.models import PlaceDraft, SightingDraft
from wildlife.ui.panels.sighting_editor import SightingEditor
from wildlife.ui.photos import choose_sighting
from wildlife.ui.photos.viewer import PhotoViewer

FIXTURES = Path(__file__).parents[1] / "fixtures" / "photos"
RAINHAM = (51.4955, 0.1975)  # where the fixture photos were 'taken'


def pixel_folder(tmp_path: Path) -> Path:
    folder = tmp_path / "Camera"
    folder.mkdir()
    shutil.copy(FIXTURES / "sample.jpg", folder / "PXL_20261010_094207000.RAW-01.COVER.jpg")
    shutil.copy(FIXTURES / "sample.dng", folder / "PXL_20261010_094207000.RAW-02.ORIGINAL.dng")
    shutil.copy(FIXTURES / "sample.heic", folder / "IMG_0002.HEIC")
    return folder


def import_into_inbox(window, qtbot, paths) -> None:
    window.go("photos")
    page = window.photos_page
    toasts = []
    page.toast.connect(lambda message, _undo: toasts.append(message))
    page.import_paths(paths)
    qtbot.waitUntil(lambda: not page._importing, timeout=15_000)
    return toasts


def add_sighting(ctx, sci="Erithacus rubecula", **kw):
    return ctx.sightings.save(
        SightingDraft(taxon_id=taxon_id(ctx, sci), observed_date=TODAY, **kw)
    ).sighting


def test_import_a_folder_into_the_inbox(window, qtbot, tmp_path):
    toasts = import_into_inbox(window, qtbot, [pixel_folder(tmp_path)])
    page = window.photos_page
    assert toasts == ["2 imported · 1 RAW original kept"]
    assert page.current_tab() == "inbox"
    assert page.tabs.button_for("inbox").text() == "Inbox (2)"
    photos = [p for g in page._inbox_grids for p in (i.photo for i in g.items)]
    assert len(photos) == 2 and sum(p.has_raw for p in photos) == 1


def test_dropping_files_imports_them(window, qtbot, tmp_path):
    window.go("photos")
    page = window.photos_page
    data = QMimeData()
    data.setUrls([QUrl.fromLocalFile(str(FIXTURES / "sample.jpg"))])
    event = QDropEvent(
        QPointF(50, 50),
        Qt.DropAction.CopyAction,
        data,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    page.dropEvent(event)
    qtbot.waitUntil(lambda: not page._importing, timeout=15_000)
    assert window.ctx.photos.inbox_count() == 1


def test_create_sighting_from_inbox_photos(window, qtbot, tmp_path):
    ctx = window.ctx
    rainham = ctx.places.save(PlaceDraft("Rainham Marshes", *RAINHAM, radius_m=800))
    elsewhere = ctx.places.save(PlaceDraft("Garden", 51.75, -0.34, radius_m=30))
    add_sighting(ctx, place_id=elsewhere.id)  # 'remember the last place' would pick Garden
    import_into_inbox(window, qtbot, [FIXTURES / "sample.jpg", FIXTURES / "sample.heic"])
    page = window.photos_page
    for grid in page._inbox_grids:
        grid.select_all()
    assert page.bulk.isVisibleTo(page) and page.bulk_label.text() == "2 photos selected"
    page._create_sighting()
    editor = window.panel.current()
    assert isinstance(editor, SightingEditor)
    assert editor.date.date().toPython().isoformat() == "2026-10-10"
    assert editor.time.text() == "10:42"
    assert editor._place_id == rainham.id  # the photos' GPS beats the remembered place
    editor.picker.set_taxon(ctx.catalogue.get(taxon_id(ctx, "Erithacus rubecula")))
    saved = ctx.sightings.get(editor.save().sighting.id)  # photos attach just after saving
    assert saved.photo_count == 2 and saved.place_id == rainham.id
    assert ctx.photos.inbox_count() == 0


def test_add_inbox_photos_to_an_existing_sighting(window, qtbot, monkeypatch):
    target = add_sighting(window.ctx)
    import_into_inbox(window, qtbot, [FIXTURES / "sample.jpg"])
    page = window.photos_page
    page._inbox_grids[0].select_all()

    def fake_exec(dialog):
        dialog.chosen = target.id
        return True

    monkeypatch.setattr(choose_sighting.ChooseSightingDialog, "exec", fake_exec)
    page._add_to_existing()
    assert [p.id for p in window.ctx.photos.for_sighting(target.id)] != []
    assert window.ctx.photos.inbox_count() == 0


def test_choose_sighting_dialog_lists_that_days_sightings_first(window):
    near = add_sighting(window.ctx)
    dialog = choose_sighting.ChooseSightingDialog(window.ctx, window.theme, TODAY, window)
    assert dialog.chosen == near.id
    dialog.search.setText("zzz")
    dialog._fill()
    assert dialog.chosen is None
    dialog.close()


def test_delete_from_inbox_with_undo_and_recycle_bin(window, qtbot):
    from wildlife.ui.pages.settings_page import RecycleBinDialog

    import_into_inbox(window, qtbot, [FIXTURES / "sample.jpg"])
    page = window.photos_page
    page._inbox_grids[0].select_all()
    page._delete_selected()
    assert window.ctx.photos.inbox_count() == 0
    window._undo()
    assert window.ctx.photos.inbox_count() == 1
    page.refresh()
    page._inbox_grids[0].select_all()
    page._delete_selected()
    dialog = RecycleBinDialog(window.ctx, window)
    assert dialog.list.item(0).text() == "Photo: sample.jpg"
    dialog.list.item(0).setSelected(True)
    dialog._restore()
    assert window.ctx.photos.inbox_count() == 1


def test_library_shows_photos_of_sightings_and_follows_the_filter(window, qtbot):
    from wildlife.domain.filters import SightingFilter

    ctx = window.ctx
    a, b = ctx.photos.import_files([FIXTURES / "sample.jpg", FIXTURES / "sample.heic"]).imported
    robin, fox = add_sighting(ctx), add_sighting(ctx, "Vulpes vulpes")
    ctx.photos.attach(robin.id, [a.id])
    ctx.photos.attach(fox.id, [b.id])
    window.go("photos")
    page = window.photos_page
    page.show_tab("library")
    assert len(page.library_grid.items) == 2
    page.set_filter(SightingFilter(category_ids=frozenset({2})))
    assert [i.title for i in page.library_grid.items] == ["Red Fox"]
    page.size_slider.setValue(250)
    assert page.library_grid.tile == 250


def test_viewer_keys_rotate_info_zoom_and_caption(window, qtbot):
    ctx = window.ctx
    photos = ctx.photos.import_files([FIXTURES / "sample.jpg", FIXTURES / "sample.heic"]).imported
    viewer = PhotoViewer(ctx, window.theme, photos, 0, parent=window)
    viewer.open_full()
    qtbot.waitUntil(lambda: viewer.stage.picture is not None, timeout=5000)
    qtbot.keyClick(viewer, Qt.Key.Key_Right)
    assert viewer.index == 1
    qtbot.keyClick(viewer, Qt.Key.Key_Right)  # stays on the last photo
    assert viewer.index == 1
    qtbot.keyClick(viewer, Qt.Key.Key_R)
    assert ctx.photos.get(photos[1].id).rotation == 90
    qtbot.keyClick(viewer, Qt.Key.Key_I)
    assert viewer.info.isVisibleTo(viewer)
    assert viewer.facts["Camera"].text() == "Apple iPhone 16"
    viewer.caption.setText("Preening")
    viewer.caption.editingFinished.emit()
    assert ctx.photos.get(photos[1].id).caption == "Preening"
    qtbot.keyClick(viewer, Qt.Key.Key_Z)
    assert viewer.stage.actual
    qtbot.waitUntil(lambda: viewer.stage.picture is not None, timeout=5000)
    qtbot.keyClick(viewer, Qt.Key.Key_Escape)
    assert not viewer.isVisible()


def test_viewer_from_a_sighting_can_make_the_cover(window, qtbot):
    ctx = window.ctx
    a, b = ctx.photos.import_files([FIXTURES / "sample.jpg", FIXTURES / "sample.heic"]).imported
    s = add_sighting(ctx)
    ctx.photos.attach(s.id, [a.id, b.id])
    window.open_sighting(s.id)
    window.panel.current().view_photo.emit(s.id, 1)
    viewer = next(w for w in window.findChildren(PhotoViewer) if w.isVisible())
    assert viewer.cover_btn.isVisibleTo(viewer) and viewer.index == 1
    viewer.make_cover()
    assert [p.id for p in ctx.photos.for_sighting(s.id)] == [b.id, a.id]
    viewer.close()


def test_missing_file_can_be_located_in_the_viewer(window, qtbot, monkeypatch):
    ctx = window.ctx
    photo = ctx.photos.import_files([FIXTURES / "sample.jpg"]).imported[0]
    ctx.photos.path_of(photo).unlink()
    viewer = PhotoViewer(ctx, window.theme, [photo], 0, parent=window)
    viewer.open_full()
    assert viewer.missing_bar.isVisibleTo(viewer) and not viewer.rotate_btn.isEnabled()
    monkeypatch.setattr(
        QFileDialog, "getOpenFileName", lambda *a, **k: (str(FIXTURES / "sample.jpg"), "")
    )
    viewer.locate()
    assert not viewer.missing_bar.isVisibleTo(viewer) and ctx.photos.missing() == []
    viewer.close()


def test_missing_files_are_reported_on_the_library(window, qtbot):
    ctx = window.ctx
    photo = ctx.photos.import_files([FIXTURES / "sample.jpg"]).imported[0]
    ctx.photos.attach(add_sighting(ctx).id, [photo.id])
    ctx.photos.path_of(photo).unlink()
    window.go("photos")
    page = window.photos_page
    page.show_tab("library")
    qtbot.waitUntil(lambda: page.missing_note.isVisibleTo(page), timeout=5000)


def test_dashboard_inbox_row_opens_the_inbox(window, qtbot):
    window.ctx.photos.import_files([FIXTURES / "sample.jpg"])
    window.dashboard.refresh()
    window.dashboard.open_inbox.emit()
    assert window.current_page() == "photos" and window.photos_page.current_tab() == "inbox"


# ---- the grid itself ------------------------------------------------------------------
@pytest.fixture
def grid(window, qtbot, tmp_path):
    from wildlife.ui.components.photo_grid import GridItem, PhotoGrid

    # different names: files sharing a name in one folder are a RAW + JPEG pair (one photo)
    files = []
    for name, target in (
        ("sample.jpg", "a.jpg"),
        ("sample.heic", "b.heic"),
        ("sample.dng", "c.dng"),
    ):
        shutil.copy(FIXTURES / name, tmp_path / target)
        files.append(tmp_path / target)
    photos = window.ctx.photos.import_files(files).imported
    assert len(photos) == 3
    g = PhotoGrid(
        window.photos_page.loader, window.theme, selectable=True, tile=120, captions=False
    )
    g.set_items([GridItem(p) for p in photos])
    g.resize(400, g.heightForWidth(400))
    g.show()
    qtbot.waitExposed(g)
    yield g
    g.close()


def test_grid_selection_by_click_shift_click_and_keys(grid, qtbot):
    centre = lambda i: grid.tile_rect(i).center().toPoint()  # noqa: E731
    qtbot.mouseClick(grid, Qt.MouseButton.LeftButton, pos=centre(0))
    assert grid.selected == {0}
    qtbot.mouseClick(
        grid, Qt.MouseButton.LeftButton, Qt.KeyboardModifier.ShiftModifier, pos=centre(2)
    )
    assert grid.selected == {0, 1, 2}
    qtbot.mouseClick(grid, Qt.MouseButton.LeftButton, pos=centre(1))
    assert grid.selected == {0, 2}
    grid.setFocus()
    grid.current = 0
    qtbot.keyClick(grid, Qt.Key.Key_Right)
    qtbot.keyClick(grid, Qt.Key.Key_Space)
    assert grid.selected == {0, 1, 2}
    assert grid.index_at(QPoint(399, 399)) is None
    grid.loader.wait_idle()


def test_grid_activates_on_double_click(grid, qtbot):
    opened = []
    grid.activated.connect(opened.append)
    qtbot.mouseDClick(grid, Qt.MouseButton.LeftButton, pos=grid.tile_rect(2).center().toPoint())
    assert opened == [2] and 2 not in grid.selected
    grid.loader.wait_idle()


def test_photos_can_be_put_in_order_in_the_editor(window, tmp_path):
    from datetime import date

    from helpers import jpeg_with_gps, taxon_id
    from wildlife.domain.models import SightingDraft

    ctx = window.ctx
    robin = ctx.sightings.save(
        SightingDraft(taxon_id(ctx, "Erithacus rubecula"), date(2026, 5, 3))
    ).sighting
    a = ctx.photos.import_files([jpeg_with_gps(tmp_path / "a.jpg", (200, 0, 0))]).imported[0]
    b = ctx.photos.import_files([jpeg_with_gps(tmp_path / "b.jpg", (0, 0, 200))]).imported[0]
    ctx.photos.attach(robin.id, [a.id, b.id])
    window.edit_sighting(robin.id)
    editor = window.panel.current()
    editor._move_photo(editor._photos[1], -1)  # b becomes the cover
    editor.save()
    assert [p.id for p in ctx.photos.for_sighting(robin.id)] == [b.id, a.id]


def test_thumbnails_scrolled_past_are_not_made(qtbot):
    """Scrolling fast past thousands of photos must not leave a queue of thumbnails to make."""
    import threading
    import time as _time
    from types import SimpleNamespace

    from wildlife.ui.components.thumbnails import ThumbnailLoader

    made, gate = [], threading.Event()

    class SlowPhotos:
        def thumbnail(self, photo, size):
            gate.wait(5)
            made.append(photo.id)
            return None

    loader = ThumbnailLoader(SlowPhotos())
    grid, other = object(), object()
    photos = [SimpleNamespace(id=i, rotation=0) for i in range(40)]
    for p in photos:
        loader.get(p, 256, owner=grid)
    loader.get(SimpleNamespace(id=99, rotation=0), 256, owner=other)
    keep = {loader.key(photos[-1], 256)}  # the grid now shows only the last photo
    dropped = loader.cancel_except(grid, keep)
    assert dropped >= 30  # all but the few already being made
    gate.set()
    assert loader.wait_idle(5000)
    _time.sleep(0.05)
    assert 39 in made and 99 in made  # what's on screen, and the other grid's photo
    assert len(made) <= 10
