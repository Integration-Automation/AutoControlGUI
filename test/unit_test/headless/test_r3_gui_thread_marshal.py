"""Round-3 GUI audit regressions for worker-thread -> GUI-thread hand-off.

* ``QTimer.singleShot`` fired from a non-Qt thread never runs (no event loop
  there); the LAN browser, presence roster and WebRTC file-received callbacks
  must marshal via a Qt Signal instead (finding 8);
* the admin-console thumbnail poll must ``deleteLater`` its QThread/worker each
  tick instead of leaking one per interval (finding 9).

Each test drives the real method from a background ``threading.Thread`` and
pumps the GUI event loop, so a queued signal is required for the effect to
appear (a thread-affine ``singleShot`` would not fire).
"""
import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets")

import shiboken6  # noqa: E402
from PySide6.QtCore import QEvent, QObject, QThread  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _pump_until(qapp, predicate, timeout=3.0):
    deadline = time.time() + timeout
    while not predicate() and time.time() < deadline:
        qapp.processEvents()
        time.sleep(0.005)
    return predicate()


def _run_off_thread(target):
    thread = threading.Thread(target=target)
    thread.start()
    thread.join(3.0)


# --- Finding 8: LAN browse dialog ------------------------------------------

def test_lan_browse_services_marshaled_to_gui(qapp, monkeypatch):
    import je_auto_control.utils.remote_desktop.lan_discovery as lan
    # Keep the dialog hermetic: no real mDNS browser.
    monkeypatch.setattr(lan, "is_discovery_available", lambda: False)
    from je_auto_control.gui.remote_desktop.webrtc_dialogs import LanBrowseDialog

    dialog = LanBrowseDialog()
    try:
        assert dialog._table.rowCount() == 0
        services = {"h1": {"host_id": "h1", "ip": "10.0.0.1",
                           "signaling_url": "wss://x", "name": "Host One"}}
        _run_off_thread(lambda: dialog._update_services(services))
        assert _pump_until(qapp, lambda: dialog._table.rowCount() == 1)
    finally:
        dialog.close()
        dialog.deleteLater()


# --- Finding 8: presence roster --------------------------------------------

def test_presence_registry_event_marshaled_to_gui(qapp):
    from je_auto_control.gui.presence_tab import PresenceTab

    tab = PresenceTab()
    try:
        tab._timer.stop()  # only the marshaled signal may refresh the roster
        tab._status.setText("SENTINEL")
        _run_off_thread(lambda: tab._on_registry_event("viewer-x", None))
        assert _pump_until(qapp, lambda: tab._status.text() != "SENTINEL")
    finally:
        tab._timer.stop()
        tab._registry.remove_listener(tab._on_registry_event)
        tab.deleteLater()


# --- Finding 8: WebRTC file-received callback ------------------------------

def test_panel_signals_expose_file_received():
    from je_auto_control.gui.remote_desktop.webrtc_panel import _PanelSignals
    assert hasattr(_PanelSignals(), "file_received")


def test_webrtc_received_file_marshaled_to_gui(qapp):
    import types
    from je_auto_control.gui.remote_desktop.webrtc_panel import (
        _PanelSignals, _WebRTCViewerPanel,
    )

    signals = _PanelSignals()

    class _Receiver(QObject):
        def __init__(self):
            super().__init__()
            self.got = None

        def on_file(self, path):
            self.got = path

    recv = _Receiver()
    signals.file_received.connect(recv.on_file)
    stub = types.SimpleNamespace(_signals=signals)

    _run_off_thread(lambda: _WebRTCViewerPanel._on_received_file(stub, "file-123"))
    assert _pump_until(qapp, lambda: recv.got == "file-123")


# --- Finding 9: thumbnail poll thread is reaped on finish ------------------

def test_thumbnail_poll_thread_is_reaped(qapp, monkeypatch, tmp_path):
    import je_auto_control.gui.admin_console_tab as admin_mod
    from je_auto_control.utils.admin.admin_client import AdminConsoleClient

    client = AdminConsoleClient(persist_path=tmp_path / "hosts.json")
    monkeypatch.setattr(admin_mod, "default_admin_console", lambda: client)
    # Don't run a real background thread: the reaping wiring is what matters,
    # and this keeps the test deterministic (no timing, no dangling threads).
    monkeypatch.setattr(admin_mod.QThread, "start", lambda self: None)

    tab = admin_mod.AdminConsoleTab()
    try:
        tab._thumb_timer.stop()
        tab._refresh_thumbnails()
        thread = tab._thumb_thread
        assert thread is not None
        assert thread in tab.findChildren(QThread)

        thread.finished.emit()  # simulate the QThread finishing
        assert tab._thumb_thread is None  # _on_thumb_thread_done ran
        # Flush the deferred deletions the finished signal scheduled.
        qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
        # Without the deleteLater wiring the QThread would linger as a child of
        # the tab, accumulating one per poll tick.
        assert not shiboken6.Shiboken.isValid(thread)
        assert tab.findChildren(QThread) == []
    finally:
        tab.deleteLater()
