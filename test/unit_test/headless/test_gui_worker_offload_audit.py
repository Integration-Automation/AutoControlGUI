"""USB enumeration, email polls and admin broadcasts run off the GUI thread; the USB watcher is held by count.

The USB tabs enumerated through PowerShell (~5 s) in their constructors and on
every 2 s refresh, on the GUI thread; one tab turning auto-refresh off stopped
the watcher the other was using; Poll now and Admin broadcast blocked the
window on the network.
"""
import os
import threading
import time
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


def _pump(app, predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    app.processEvents()
    return predicate()


class _FakeWatcher:
    def __init__(self, running=False):
        self.running = running
        self.stops = 0

    @property
    def is_running(self):
        return self.running

    def start(self):
        self.running = True

    def stop(self):
        self.stops += 1
        self.running = False

    def recent_events(self, since=0, limit=10):
        return []


@pytest.fixture()
def watcher(monkeypatch):
    from je_auto_control.utils.usb import usb_watcher
    fake = _FakeWatcher()
    monkeypatch.setattr(usb_watcher, "default_usb_watcher", lambda: fake)
    monkeypatch.setattr(usb_watcher, "_holders", 0)
    monkeypatch.setattr(usb_watcher, "_holders_started", False)
    return fake


def test_the_watcher_stops_with_its_last_holder(watcher):
    from je_auto_control.utils.usb.usb_watcher import hold_default_watcher, release_default_watcher
    hold_default_watcher()
    hold_default_watcher()
    release_default_watcher()
    assert watcher.running
    release_default_watcher()
    assert not watcher.running and watcher.stops == 1
    release_default_watcher()                       # an extra release is ignored
    assert watcher.stops == 1


def test_holders_never_stop_a_watcher_something_else_started(watcher):
    from je_auto_control.utils.usb.usb_watcher import hold_default_watcher, release_default_watcher
    watcher.running = True                          # the executor's AC_usb_watch_start
    hold_default_watcher()
    release_default_watcher()
    assert watcher.running and watcher.stops == 0


def test_the_usb_tab_enumerates_off_the_gui_thread_and_only_when_shown(qapp, monkeypatch, watcher):
    from je_auto_control.gui import usb_devices_tab
    threads = []

    def listing():
        threads.append(threading.get_ident())
        return types.SimpleNamespace(backend="fake", error=None, devices=[
            types.SimpleNamespace(vendor_id="1050", product_id="0407", manufacturer="Yubico", product="Key",
                                  serial="S", bus_location="1-1")])

    monkeypatch.setattr(usb_devices_tab, "list_usb_devices", listing)
    tab = usb_devices_tab.UsbDevicesTab()
    try:
        assert threads == []                        # not at construction
        tab.show()
        assert _pump(qapp, lambda: tab._table.rowCount() == 1)
        assert threads and threads[0] != threading.get_ident()
    finally:
        tab.hide()
        tab.deleteLater()


def test_two_usb_views_share_the_watcher(qapp, monkeypatch, watcher):
    from je_auto_control.gui import usb_devices_tab
    from je_auto_control.gui.usb_passthrough_panel import _ShareState
    monkeypatch.setattr(usb_devices_tab, "list_usb_devices",
                        lambda: types.SimpleNamespace(backend="fake", error=None, devices=[]))
    tab = usb_devices_tab.UsbDevicesTab()
    share = _ShareState()
    try:
        tab._auto_check.setChecked(True)
        share.watch()
        tab._auto_check.setChecked(False)
        assert watcher.running, "turning the tab's refresh off stopped the panel's watcher"
        share.unwatch()
        assert _pump(qapp, lambda: not watcher.running)
    finally:
        tab.deleteLater()


def test_poll_now_runs_off_the_gui_thread(qapp, monkeypatch):
    from je_auto_control.gui import email_triggers_tab
    threads, shown = [], []
    fake = types.SimpleNamespace(
        poll_once=lambda: threads.append(threading.get_ident()) or 2,
        list_triggers=lambda: [types.SimpleNamespace(trigger_id="t1", last_error="TimeoutError()")],
        is_running=False, running=False)
    monkeypatch.setattr(email_triggers_tab, "default_email_trigger_watcher", fake)
    monkeypatch.setattr(email_triggers_tab.QMessageBox, "information", lambda *args: shown.append(args[-1]))
    monkeypatch.setattr(email_triggers_tab.EmailTriggersTab, "_refresh", lambda self: None)
    tab = email_triggers_tab.EmailTriggersTab()
    try:
        tab._on_poll_now()
        assert _pump(qapp, lambda: bool(shown))
        assert threads[0] != threading.get_ident()
        assert "TimeoutError" in shown[0]
    finally:
        tab.deleteLater()
