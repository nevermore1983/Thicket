from wildlife.config.settings import Settings, Theme
from wildlife.services.events import EventHub
from wildlife.services.settings import SettingsService


def test_defaults_when_nothing_stored(db):
    assert SettingsService(db, EventHub()).current == Settings()


def test_change_is_saved_and_announced(db):
    events = EventHub()
    seen = []
    events.subscribe(seen.append)
    SettingsService(db, events).update(theme=Theme.DARK, recorder_name="Sam")
    reloaded = SettingsService(db, EventHub()).current
    assert reloaded.theme is Theme.DARK and reloaded.recorder_name == "Sam"
    assert [e.topic for e in seen] == ["settings"]


def test_setting_back_to_default_removes_the_override(db):
    service = SettingsService(db, EventHub())
    service.update(theme=Theme.DARK)
    service.update(theme=Theme.SYSTEM)
    with db.connection() as conn:
        assert conn.execute("SELECT COUNT(*) FROM setting").fetchone()[0] == 0


def test_bad_stored_values_fall_back_to_defaults():
    s = Settings.from_stored(
        {
            "theme": "purple",
            "remember_place_hours": "abc",
            "unknown": 1,
            "count_probable_ids": "yes",
        }
    )
    assert s == Settings()
