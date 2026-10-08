"""The Config Sync tab remembers its form between runs -- except the secret (offscreen Qt, temp files)."""
import os

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import QApplication  # noqa: E402

from je_auto_control.gui import config_sync_tab  # noqa: E402
from je_auto_control.gui.window_settings import WindowSettings, WindowState  # noqa: E402

#: What the test types into the secret field; it must never reach the settings file.
_NEVER_SAVED = "phrase-0451-never-on-disk"


@pytest.fixture()
def qapp(monkeypatch):
    monkeypatch.setattr(config_sync_tab.session, "config_sync_status", lambda _url, _user: {})
    return QApplication.instance() or QApplication([])


def test_a_form_round_trips_beside_the_window_state(tmp_path):
    store = WindowSettings(tmp_path / "gui.ini")
    assert store.load_form("config_sync") == {}
    assert store.save(WindowState(theme="light", text_size=14))
    assert store.save_form("config_sync", {"server": "https://sync.invalid", "user": "alice"})
    again = WindowSettings(tmp_path / "gui.ini")
    assert again.load_form("config_sync") == {"server": "https://sync.invalid", "user": "alice"}
    assert again.load().theme == "light" and again.load().text_size == 14
    assert again.load_form("another") == {}


def test_saving_a_form_replaces_its_fields_and_leaves_other_forms(tmp_path):
    store = WindowSettings(tmp_path / "gui.ini")
    store.save_form("one", {"a": "1", "b": "2"})
    store.save_form("two", {"a": "x"})
    store.save_form("one", {"a": "3"})
    assert store.load_form("one") == {"a": "3"} and store.load_form("two") == {"a": "x"}


def test_a_store_that_is_off_remembers_nothing(tmp_path):
    store = WindowSettings(None)
    assert store.save_form("config_sync", {"server": "x"}) is False
    assert store.load_form("config_sync") == {} and list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("name", ["", "has space", "a/b", "1st", "x" * 80])
def test_form_and_field_names_are_checked(tmp_path, name):
    store = WindowSettings(tmp_path / "gui.ini")
    with pytest.raises(ValueError):
        store.save_form(name, {"a": "1"})
    with pytest.raises(ValueError):
        store.load_form(name)
    with pytest.raises(ValueError):
        store.save_form("form", {name: "1"})


def test_an_edited_file_gives_back_only_short_text(tmp_path):
    path = tmp_path / "gui.ini"
    store = WindowSettings(path)
    store.save_form("config_sync", {"server": "ok", "user": "x" * 5000})
    assert len(store.load_form("config_sync")["user"]) == 2048      # cut on the way in
    text = path.read_text(encoding="utf-8").replace("server=ok", "server=" + "y" * 5000)
    path.write_text(text, encoding="utf-8")
    assert "server" not in WindowSettings(path).load_form("config_sync")


def test_the_tab_restores_what_it_saved_and_never_the_secret(qapp, tmp_path):
    path = tmp_path / "gui.ini"
    first = config_sync_tab.ConfigSyncTab(settings=WindowSettings(path))
    values = {"server": "https://sync.invalid", "user": "alice", "secret": _NEVER_SAVED,
              "scripts": "C:/scripts", "assets": "C:/assets"}
    for name, value in values.items():
        first._inputs[name].setText(value)
    first._inputs["server"].editingFinished.emit()      # a field lost focus
    assert _NEVER_SAVED not in path.read_text(encoding="utf-8")
    first.deleteLater()
    second = config_sync_tab.ConfigSyncTab(settings=WindowSettings(path))
    shown = {name: field.text() for name, field in second._inputs.items()}
    assert shown == {**values, "secret": ""}
    second.deleteLater()


def test_starting_a_sync_saves_the_form(qapp, tmp_path, monkeypatch):
    monkeypatch.setattr(config_sync_tab.session, "config_sync_run", lambda *_args, **_kwargs: {})
    path = tmp_path / "gui.ini"
    tab = config_sync_tab.ConfigSyncTab(settings=WindowSettings(path))
    tab._inputs["server"].setText("https://sync.invalid")
    tab._inputs["user"].setText("bob")
    tab._inputs["secret"].setText(_NEVER_SAVED)
    tab.sync_now()
    saved = WindowSettings(path).load_form("config_sync")
    assert saved["user"] == "bob" and "secret" not in saved
    assert _NEVER_SAVED not in path.read_text(encoding="utf-8")
    worker = tab._worker
    assert worker is None or worker.wait(10.0)
    qapp.processEvents()
    tab.deleteLater()


def test_the_default_store_is_off_in_the_suite(qapp):
    tab = config_sync_tab.ConfigSyncTab()
    assert tab._settings_store.path is None, "a test wrote to the user's settings file"
    tab.deleteLater()
