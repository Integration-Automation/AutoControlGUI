"""WebRTC panels: closing a session, a recording or a folder sync no longer holds the GUI thread.

Offscreen Qt with fake hosts, viewers, recorders and sync engines whose
``stop`` waits until the test lets it go. Nothing here opens a peer connection.
"""
import os
import threading
import time
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
pytest.importorskip("av")
pytest.importorskip("aiortc")

from PySide6.QtCore import Qt  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QTableWidgetItem  # noqa: E402

from je_auto_control.gui.remote_desktop import webrtc_panel  # noqa: E402
from je_auto_control.gui.remote_desktop._helpers import _t  # noqa: E402
from headless._qt_settle import deleting, pump_until, settle_op  # noqa: E402

_PROMPT_S = 5.0
_JOIN_S = 30.0


@pytest.fixture(autouse=True)
def qapp(monkeypatch):
    app = QApplication.instance() or QApplication([])
    messages = []
    for box in ("warning", "information", "question", "critical"):
        monkeypatch.setattr(QMessageBox, box, lambda *args: messages.append(args[-1]))
    app.messages = messages
    yield app


@pytest.fixture(autouse=True)
def _panels_deleted():
    """Each test deletes the parentless panels it built (see ``_qt_settle.deleting``)."""
    with deleting(webrtc_panel._WebRTCHostPanel, webrtc_panel._WebRTCViewerPanel):
        yield


class _Gate:
    def __init__(self, name="", log=None):
        self.entered, self.release = threading.Event(), threading.Event()
        self.calls, self.threads, self.name, self.log = 0, [], name, log

    def __call__(self, *args, **_kwargs):
        self.calls += 1
        self.threads.append(threading.current_thread())
        if self.log is not None:
            self.log.append((self.name, *args))
        self.entered.set()
        self.release.wait(_JOIN_S)


def _off(button):
    """Whether the button itself was disabled (its group may be collapsed, which disables it too)."""
    return button.testAttribute(Qt.WidgetAttribute.WA_ForceDisabled)


def _timed(call):
    started = time.monotonic()
    call()
    return time.monotonic() - started


def test_host_stop_lets_go_at_once_and_closes_the_sessions_in_the_background():
    panel = webrtc_panel._WebRTCHostPanel()
    gate = _Gate()
    panel._multi_host = types.SimpleNamespace(stop_all=gate, session_count=lambda: 0)
    try:
        assert _timed(panel._on_stop) < _PROMPT_S
        assert gate.entered.wait(10.0) and gate.threads[0] is not threading.main_thread()
        assert panel._multi_host is None
        assert panel._status_label.text() == _t("gui_op_stopping")
        panel._on_stop()                    # a second click has no host left to stop
        assert gate.calls == 1 and panel._status_label.text() == _t("gui_op_stopping")
    finally:
        gate.release.set()
    assert settle_op(panel._stops)
    assert panel._status_label.text() == _t("rd_webrtc_status_idle")


def test_a_host_started_while_the_old_one_closes_keeps_its_own_status():
    panel = webrtc_panel._WebRTCHostPanel()
    gate = _Gate()
    panel._multi_host = types.SimpleNamespace(stop_all=gate, session_count=lambda: 0)
    panel._on_stop()
    panel._status_label.setText(_t("rd_webrtc_publishing_offer"))      # the next session is already up
    gate.release.set()
    assert settle_op(panel._stops)
    assert panel._status_label.text() == _t("rd_webrtc_publishing_offer")


def test_disconnecting_one_session_is_off_the_gui_thread_and_not_repeated():
    panel = webrtc_panel._WebRTCHostPanel()
    gate, counts = _Gate(), []
    panel._multi_host = types.SimpleNamespace(stop_session=gate, session_count=lambda: 0)
    panel._signals.session_count.disconnect()
    panel._signals.session_count.connect(counts.append)
    panel._sessions_table.setRowCount(1)
    item = QTableWidgetItem("s")
    item.setData(Qt.ItemDataRole.UserRole, "session-1")
    panel._sessions_table.setItem(0, 1, item)
    panel._sessions_table.setCurrentCell(0, 1)
    try:
        assert _timed(panel._on_disconnect_selected) < _PROMPT_S
        assert gate.entered.wait(10.0) and gate.threads[0] is not threading.main_thread()
        panel._on_disconnect_selected()     # the same row, clicked again
        assert gate.calls == 1 and counts == []
    finally:
        gate.release.set()
    assert settle_op(panel._stops)
    assert counts == [0] and panel._stopping_sessions == set()


def test_viewer_stop_hands_sync_recorder_and_viewer_to_the_background_in_order():
    panel = webrtc_panel._WebRTCViewerPanel()
    log = []
    gates = [_Gate(name, log) for name in ("sync", "recorder", "viewer")]
    panel._sync_engine = types.SimpleNamespace(stop=gates[0])
    panel._recorder = types.SimpleNamespace(stop=gates[1], has_output=True, output_path="x.mp4")
    panel._viewer = types.SimpleNamespace(stop=gates[2], authenticated=False)
    try:
        assert _timed(panel._on_stop) < _PROMPT_S
        assert gates[0].entered.wait(10.0) and gates[0].threads[0] is not threading.main_thread()
        assert panel._viewer is None and panel._recorder is None and panel._sync_engine is None
        assert panel._status_label.text() == _t("gui_op_stopping")
        panel._on_stop()
    finally:
        for gate in gates:
            gate.release.set()
    assert settle_op(panel._stops)
    assert log == [("sync",), ("recorder",), ("viewer",)]
    assert panel._status_label.text() == _t("rd_webrtc_status_idle")


def test_stopping_a_recording_reports_when_the_file_is_finalised(qapp):
    panel = webrtc_panel._WebRTCViewerPanel()
    gate = _Gate()
    panel._recorder = types.SimpleNamespace(stop=gate, has_output=True, output_path="out.mp4")
    try:
        assert _timed(lambda: panel._on_toggle_recording(False)) < _PROMPT_S
        assert gate.entered.wait(10.0) and gate.threads[0] is not threading.main_thread()
        assert not panel._record_btn.isEnabled() and panel._record_btn.text() == _t("gui_op_stopping")
        assert qapp.messages == [], "saved was announced before the file was finalised"
        panel._on_toggle_recording(False)
        assert gate.calls == 1
    finally:
        gate.release.set()
    assert settle_op(panel._stops)
    assert qapp.messages == [_t("rd_webrtc_recording_saved").format(path="out.mp4")]
    assert panel._record_btn.isEnabled() and panel._record_btn.text() == _t("rd_webrtc_start_recording")


def test_stopping_folder_sync_joins_the_watcher_off_the_gui_thread():
    panel = webrtc_panel._WebRTCViewerPanel()
    gate = _Gate()
    panel._sync_engine = types.SimpleNamespace(stop=gate)
    try:
        assert _timed(lambda: panel._on_toggle_sync(False)) < _PROMPT_S
        assert gate.entered.wait(10.0) and gate.threads[0] is not threading.main_thread()
        assert panel._sync_engine is None and _off(panel._sync_btn)
        assert panel._sync_btn.text() == _t("gui_op_stopping")
        panel._on_toggle_sync(False)
        assert gate.calls == 1
    finally:
        gate.release.set()
    assert settle_op(panel._stops)
    assert not _off(panel._sync_btn) and panel._sync_btn.text() == _t("rd_webrtc_sync_start")
    assert pump_until(lambda: panel._stops.pending == 0)
