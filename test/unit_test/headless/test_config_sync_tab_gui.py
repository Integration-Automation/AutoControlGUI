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
    assert len(specs) == 1 and specs[0].class_name == "ConfigSyncTab"
    actions = tab.menu_actions()
    assert [key for key, _handler in actions] == [
        "config_sync_run_btn", "config_sync_cancel_btn", "config_sync_refresh_btn",
        "config_sync_resolve_btn", "config_sync_resync_btn"]
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
    keys |= {f"config_sync_state_{state}" for state in (
        "never", "syncing", "synced", "pending", "conflict", "offline", "cancelled",
        "resync_required")}
    keys.discard("config_sync_state_")
    for module in (english, japanese, simplified_chinese, traditional_chinese):
        catalogue = next(value for value in vars(module).values()
                         if isinstance(value, dict) and "tab_presence" in value)
        missing = sorted(key for key in keys if key not in catalogue)
        assert not missing, f"{module.__name__} lacks {missing}"


def test_refresh_shows_revision_pending_and_conflicts(tab):
    tab.refresh_status()
    assert "7" in tab._detail.text() and "2" in tab._detail.text()  # noqa: SLF001
    table = tab._conflicts  # noqa: SLF001
    assert table.rowCount() == 2
    assert table.item(0, 0).text() == "hotkeys/hk1" and table.item(1, 2).text() == "desktop"


def test_server_and_user_are_required(tab, monkeypatch):
    called = []
    monkeypatch.setattr(tab_module.session, "config_sync_run",
                        lambda *args, **kwargs: called.append(args))
    tab._inputs["server"].setText("")  # noqa: SLF001
    tab.sync_now()
    assert called == [] and not tab.is_busy()


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
    assert seen["options"] == {"secret": "s3cret"}

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
    assert ran == [] and not tab.is_busy()
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
