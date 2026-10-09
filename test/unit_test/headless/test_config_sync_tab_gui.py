"""The Config Sync tab: status view, Actions-menu commands, cancellable worker."""
import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QCoreApplication, QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from je_auto_control.gui import config_sync_tab as tab_module  # noqa: E402
from je_auto_control.gui.config_sync_tab import ConfigSyncTab  # noqa: E402

_CONFLICTED = {
    "state": "conflict", "revision": 7, "pending": 2, "last_success": 1_700_000_000.0,
    "error": "", "conflicts": ["hotkeys/hk1"],
    "conflict_details": [{"section": "hotkeys", "key": "hk1", "choices": [
        {"origin": "laptop", "deleted": False, "value": {"combo": "ctrl+l"}},
        {"origin": "desktop", "deleted": True, "value": None}]}],
}


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def tab(qapp, monkeypatch):
    monkeypatch.setattr(tab_module.session, "config_sync_status",
                        lambda _url, _user: dict(_CONFLICTED))
    widget = ConfigSyncTab()
    widget._inputs["server"].setText("https://sync.invalid")  # noqa: SLF001
    widget._inputs["user"].setText("alice")  # noqa: SLF001
    yield widget
    widget.cancel()
    widget.deleteLater()


def _pump(qapp, done, timeout_s=5.0):
    deadline = time.monotonic() + timeout_s
    while not done() and time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.01)
    qapp.processEvents()
    return done()


def test_the_tab_is_registered_once_and_exposes_its_commands(tab):
    from je_auto_control.gui.tab_registry import TAB_SPECS
    specs = [spec for spec in TAB_SPECS if spec.key == "config_sync"]
    assert len(specs) == 1
    assert specs[0].class_name == "ConfigSyncTab"
    actions = tab.menu_actions()
    assert [key for key, _handler in actions] == [
        "config_sync_run_btn", "config_sync_cancel_btn", "config_sync_refresh_btn",
        "config_sync_resolve_btn", "config_sync_resync_btn", "config_sync_collect_btn"]
    assert all(callable(handler) for _key, handler in actions)


def test_every_text_exists_in_all_four_languages(tab):
    import re
    from pathlib import Path
    from je_auto_control.gui.language_wrapper import (
        english, japanese, simplified_chinese, traditional_chinese)
    source = Path(tab_module.__file__).read_text(encoding="utf-8")
    keys = set(re.findall(r'"((?:tab_)?config_sync_[a-z_]+)"', source))
    keys |= {f"config_sync_{name}_label" for name in tab_module._FIELDS}  # noqa: SLF001
    keys |= {f"config_sync_col_{name}" for name in tab_module._COLUMNS}  # noqa: SLF001
    keys |= {f"config_sync_section_{name}" for name in tab_module.session.SYNCABLE_SECTIONS}
    keys |= {f"config_sync_state_{state}" for state in (
        "never", "syncing", "synced", "pending", "conflict", "offline", "backing_off",
        "cancelled", "resync_required")}
    keys.discard("config_sync_state_")
    for module in (english, japanese, simplified_chinese, traditional_chinese):
        catalogue = next(value for value in vars(module).values()
                         if isinstance(value, dict) and "tab_presence" in value)
        missing = sorted(key for key in keys if key not in catalogue)
        assert not missing, f"{module.__name__} lacks {missing}"


def test_refresh_shows_revision_pending_and_conflicts(tab):
    tab.refresh_status()
    assert "7" in tab._detail.text()
    assert "2" in tab._detail.text()  # noqa: SLF001
    table = tab._conflicts  # noqa: SLF001
    assert table.rowCount() == 2
    assert table.item(0, 0).text() == "hotkeys/hk1"
    assert table.item(1, 2).text() == "desktop"


def test_server_and_user_are_required(tab, monkeypatch):
    called = []
    monkeypatch.setattr(tab_module.session, "config_sync_run",
                        lambda *args, **kwargs: called.append(args))
    tab._inputs["server"].setText("")  # noqa: SLF001
    tab.sync_now()
    assert called == []
    assert not tab.is_busy()


def test_sync_runs_off_the_gui_thread_and_can_be_cancelled(tab, qapp, monkeypatch):
    seen = {}

    def slow_sync(server_url, user_id, cancel=None, **options):
        seen.update(server_url=server_url, user_id=user_id, options=options,
                    thread=threading.current_thread())
        cancelled = cancel.wait(10)
        return {"state": "cancelled" if cancelled else "synced", "revision": 7, "pending": 2}

    monkeypatch.setattr(tab_module.session, "config_sync_run", slow_sync)
    tab._inputs["secret"].setText("s3cret")  # noqa: SLF001
    tab.sync_now()
    assert tab.is_busy()
    tab.sync_now()            # a second request while one runs is refused
    assert _pump(qapp, lambda: "thread" in seen)
    assert seen["thread"] is not threading.main_thread()
    # "Sync now" is a person asking: it skips a retry delay once.
    assert seen["options"] == {"secret": "s3cret", "force": True}

    tab.cancel()
    assert _pump(qapp, lambda: not tab.is_busy() and tab._worker is None)  # noqa: SLF001
    assert tab._cancel_slot == []  # noqa: SLF001


def test_a_failed_sync_is_shown_not_raised(tab, qapp, monkeypatch):
    def broken(*_args, **_kwargs):
        raise RuntimeError("the server predates revision-checked writes")

    monkeypatch.setattr(tab_module.session, "config_sync_run", broken)
    tab.sync_now()
    assert _pump(qapp, lambda: tab._worker is None)  # noqa: SLF001
    assert "predates" in tab._detail.text()  # noqa: SLF001


def test_resolving_sends_the_selected_candidate(tab, monkeypatch):
    resolved = []
    monkeypatch.setattr(tab_module.session, "config_sync_resolve",
                        lambda *args, **options: resolved.append(args))
    tab.resolve_selected()
    assert resolved == [], "nothing selected yet"
    tab.refresh_status()
    tab._conflicts.selectRow(1)  # noqa: SLF001
    tab.resolve_selected()
    assert resolved == [("https://sync.invalid", "alice", "hotkeys", "hk1", 1)]


def test_a_full_resync_needs_confirmation(tab, qapp, monkeypatch):
    ran = []
    monkeypatch.setattr(tab_module.session, "config_sync_full_resync",
                        lambda *args, **options: ran.append(args) or {"state": "synced"})
    monkeypatch.setattr(ConfigSyncTab, "_confirm", lambda _self, _question: False)
    tab.full_resync()
    assert ran == []
    assert not tab.is_busy()
    monkeypatch.setattr(ConfigSyncTab, "_confirm", lambda _self, _question: True)
    tab.full_resync()
    assert _pump(qapp, lambda: tab._worker is None)  # noqa: SLF001
    assert ran == [("https://sync.invalid", "alice")]


def test_closing_the_tab_releases_a_running_sync(qapp, monkeypatch):
    released = threading.Event()

    def slow_sync(_url, _user, cancel=None, **_options):
        if cancel.wait(10):
            released.set()
        return {"state": "cancelled"}

    monkeypatch.setattr(tab_module.session, "config_sync_run", slow_sync)
    monkeypatch.setattr(tab_module.session, "config_sync_status", lambda _url, _user: {})
    widget = ConfigSyncTab()
    widget._inputs["server"].setText("https://sync.invalid")  # noqa: SLF001
    widget._inputs["user"].setText("alice")  # noqa: SLF001
    widget.sync_now()
    widget.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    assert released.wait(5), "the worker was still waiting after its tab was destroyed"


def test_a_retry_delay_reads_as_waiting_not_as_offline(tab, monkeypatch):
    from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
    monkeypatch.setattr(tab_module.session, "config_sync_status", lambda _url, _user: {
        "state": "backing_off", "retry_in_s": 41.2, "pending": 1, "revision": 3,
        "error": "config sync: connection refused"})
    tab.refresh_status()
    shown = tab._state.text()  # noqa: SLF001
    waiting = language_wrapper.translate("config_sync_state_backing_off", "")
    offline = language_wrapper.translate("config_sync_state_offline", "")
    assert waiting
    assert waiting in shown
    assert offline not in shown
    assert "42" in shown, "the seconds until the next automatic attempt, rounded up"
    monkeypatch.setattr(tab_module.session, "config_sync_status",
                        lambda _url, _user: {"state": "synced", "retry_in_s": 0.0})
    tab.refresh_status()
    assert "42" not in tab._state.text()  # noqa: SLF001


# --- the section picker and the assets_server switch -------------------------------

def _options_of_a_sync(widget, qapp, monkeypatch):
    """Run "Sync now" against a fake session; the options it was given (``None`` if not run)."""
    seen = []
    monkeypatch.setattr(tab_module.session, "config_sync_run",
                        lambda _url, _user, cancel=None, **options: seen.append(options) or {})
    widget.sync_now()
    _pump(qapp, lambda: widget._worker is None)  # noqa: SLF001
    return seen[0] if seen else None


def test_every_section_ticked_leaves_the_choice_to_the_session(tab, qapp, monkeypatch):
    assert list(tab._sections) == list(tab_module.session.SYNCABLE_SECTIONS)  # noqa: SLF001
    assert all(box.isChecked() for box in tab._sections.values())  # noqa: SLF001
    options = _options_of_a_sync(tab, qapp, monkeypatch)
    assert "sections" not in options
    assert "assets_server" not in options


def test_unticking_a_section_names_the_rest(tab, qapp, monkeypatch, tmp_path):
    tab._sections["hotkeys"].setChecked(False)  # noqa: SLF001
    options = _options_of_a_sync(tab, qapp, monkeypatch)
    assert options["sections"] == ["triggers", "address_book"], "no path: scripts, locators out"
    tab._inputs["scripts"].setText(str(tmp_path))  # noqa: SLF001
    tab._inputs["locators"].setText(str(tmp_path / "locators.json"))  # noqa: SLF001
    options = _options_of_a_sync(tab, qapp, monkeypatch)
    assert options["sections"] == ["triggers", "address_book", "scripts", "locators"]
    assert options["scripts_dir"] == str(tmp_path)
    assert options["locators_path"] == str(tmp_path / "locators.json")
    # What the picker passes is what the session accepts.
    assert tab_module.session.resolve_sections(
        options["sections"], scripts_dir=options["scripts_dir"],
        locators_path=options["locators_path"]) == options["sections"]


def test_a_choice_that_leaves_nothing_is_said_not_synced(tab, qapp, monkeypatch):
    from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper
    for name in ("hotkeys", "triggers", "address_book"):
        tab._sections[name].setChecked(False)  # noqa: SLF001
    assert _options_of_a_sync(tab, qapp, monkeypatch) is None
    assert tab._detail.text() == language_wrapper.translate(  # noqa: SLF001
        "config_sync_no_sections", "")
    tab.refresh_status()                # reading the status needs no section
    assert "7" in tab._detail.text()  # noqa: SLF001


def test_the_assets_server_switch_replaces_the_shared_folder(tab, qapp, monkeypatch, tmp_path):
    tab._inputs["assets"].setText(str(tmp_path))  # noqa: SLF001
    assert _options_of_a_sync(tab, qapp, monkeypatch)["assets_dir"] == str(tmp_path)
    tab._assets_server.setChecked(True)  # noqa: SLF001
    assert not tab._inputs["assets"].isEnabled()  # noqa: SLF001
    options = _options_of_a_sync(tab, qapp, monkeypatch)
    assert options["assets_server"] is True
    assert "assets_dir" not in options
    tab._assets_server.setChecked(False)  # noqa: SLF001
    assert tab._inputs["assets"].isEnabled()  # noqa: SLF001


def test_the_picker_and_the_switch_are_remembered_but_never_the_secret(qapp, tmp_path):
    from je_auto_control.gui.window_settings import WindowSettings
    ini = tmp_path / "gui.ini"
    first = ConfigSyncTab(settings=WindowSettings(ini))
    first._inputs["server"].setText("https://sync.invalid")  # noqa: SLF001
    first._inputs["secret"].setText("do-not-store-me")  # noqa: SLF001
    first._inputs["locators"].setText("locators.json")  # noqa: SLF001
    first._sections["triggers"].setChecked(False)  # noqa: SLF001
    first._assets_server.setChecked(True)  # noqa: SLF001
    first._remember_form()  # noqa: SLF001
    first.deleteLater()
    assert "do-not-store-me" not in ini.read_text(encoding="utf-8")

    again = ConfigSyncTab(settings=WindowSettings(ini))
    ticked = {name: box.isChecked() for name, box in again._sections.items()}  # noqa: SLF001
    assert ticked == {"hotkeys": True, "triggers": False, "address_book": True,
                      "scripts": True, "locators": True}
    assert again._assets_server.isChecked()  # noqa: SLF001
    assert not again._inputs["assets"].isEnabled()  # noqa: SLF001
    assert again._inputs["locators"].text() == "locators.json"  # noqa: SLF001
    assert again._inputs["secret"].text() == ""  # noqa: SLF001
    again.deleteLater()
    # Nothing saved yet: every section ticked, the switch off.
    fresh = ConfigSyncTab(settings=WindowSettings(tmp_path / "none.ini"))
    assert all(box.isChecked() for box in fresh._sections.values())  # noqa: SLF001
    assert not fresh._assets_server.isChecked()  # noqa: SLF001
    fresh.deleteLater()


def test_the_status_lists_the_sections_the_last_sync_covered(tab, monkeypatch):
    monkeypatch.setattr(tab_module.session, "config_sync_status", lambda _url, _user: {
        "state": "synced", "sections": ["triggers", "scripts"]})
    tab.refresh_status()
    assert "triggers, scripts" in tab._detail.text()  # noqa: SLF001


def test_collecting_blobs_needs_confirmation_and_reports_what_it_did(tab, qapp, monkeypatch):
    ran = []

    def collect(server_url, user_id, **options):
        ran.append((server_url, user_id, options))
        return {"deleted": ["a" * 64, "b" * 64], "freed": 4096, "kept": 3, "recent": ["c" * 64]}

    monkeypatch.setattr(tab_module.session, "config_sync_collect_blobs", collect)
    monkeypatch.setattr(ConfigSyncTab, "_confirm", lambda _self, _question: False)
    tab.collect_blobs()
    assert ran == []
    assert not tab.is_busy()
    monkeypatch.setattr(ConfigSyncTab, "_confirm", lambda _self, _question: True)
    tab._inputs["secret"].setText("s3cret")  # noqa: SLF001
    for box in tab._sections.values():  # noqa: SLF001
        box.setChecked(False)           # housekeeping does not depend on the section choice
    tab.collect_blobs()
    assert _pump(qapp, lambda: tab._worker is None and ran)  # noqa: SLF001
    assert ran == [("https://sync.invalid", "alice", {"secret": "s3cret"})]
    shown = tab._detail.text()  # noqa: SLF001
    assert "4096" in shown
    assert "2" in shown
    assert "3" in shown
