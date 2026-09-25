"""WebRTC host / viewer panels and Quick Connect sessions (offscreen Qt, fakes).

Remote annotations raised on bad numbers and grew without bound; installing the
tray kept the app alive with no host; a host stopped under the approval dialog
raised AttributeError, as did the stats thread racing a stop; imports raised on
files of the wrong shape; Stop could not cancel a pending reconnect; a new
window ignored the pen; an empty recording was reported saved; Quick Connect
ignored ws:// sessions on close and in its badge, left the session up after an
error, and kept a timed-out approval box open.
"""
import os
import time
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
pytest.importorskip("av")
pytest.importorskip("aiortc")

from PySide6.QtWidgets import QApplication, QFileDialog, QMessageBox, QSystemTrayIcon  # noqa: E402

from je_auto_control.gui.remote_desktop import connection_screen, tray_icon, webrtc_panel  # noqa: E402
from je_auto_control.gui.remote_desktop._helpers import _t  # noqa: E402
from je_auto_control.utils.remote_desktop.registry import registry  # noqa: E402
from je_auto_control.utils.remote_desktop.webrtc_stats import StatsSnapshot  # noqa: E402


@pytest.fixture(autouse=True)
def qapp(monkeypatch):
    app = QApplication.instance() or QApplication([])
    messages = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: messages.append(args[-1]))
    monkeypatch.setattr(QMessageBox, "information", lambda *args: messages.append(args[-1]))
    monkeypatch.setattr(registry, "_viewer", None)
    monkeypatch.setattr(registry, "_ws_viewer", None)
    app.messages = messages
    yield app


# --- host side -------------------------------------------------------------------------------------------

def test_remote_annotations_are_checked_and_bounded():
    panel = webrtc_panel._WebRTCHostPanel()
    panel._on_annotation_event({"action": "begin", "x": "left", "y": 1})
    panel._on_annotation_event({"action": "begin", "x": 1, "y": 2, "width": 10 ** 9})
    for step in range(6000):
        panel._on_annotation_event({"action": "point", "x": step, "y": step})
    strokes = panel._annotation_overlay._strokes
    assert len(strokes) == 1 and strokes[0]["width"] == 32
    assert len(strokes[0]["points"]) == 5000
    panel._annotation_overlay.hide()


def test_the_tray_keeps_the_app_alive_only_while_hosting(monkeypatch):
    monkeypatch.setattr(QSystemTrayIcon, "isSystemTrayAvailable", staticmethod(lambda: True))
    tray = tray_icon.install_host_tray(on_open=lambda: None, on_stop=lambda: None, on_quit=lambda: None)
    try:
        assert QApplication.quitOnLastWindowClosed()
        tray.set_hosting(True)
        assert not QApplication.quitOnLastWindowClosed()
        tray.set_hosting(False)
        assert QApplication.quitOnLastWindowClosed()
    finally:
        QApplication.setQuitOnLastWindowClosed(True)
        tray.hide()


def test_a_host_stopped_under_the_approval_dialog_is_not_an_error(monkeypatch):
    panel = webrtc_panel._WebRTCHostPanel()
    panel._multi_host = types.SimpleNamespace(session_count=lambda: 1)

    class Dialog:
        AcceptAndTrust, AcceptOnce = 2, 1

        def __init__(self, *args, **kwargs):
            return None

        def exec(self):
            panel._multi_host = None     # Stop, or the tray's Stop, while it is open

        def choice(self):
            return Dialog.AcceptOnce

    monkeypatch.setattr(webrtc_panel, "PendingViewerDialog", Dialog)
    panel._on_pending_viewer("session-1", "viewer")


def test_the_stats_thread_reads_the_host_once():
    panel = webrtc_panel._WebRTCHostPanel()

    class Host:
        def __bool__(self):
            panel._multi_host = None     # the GUI thread stops the host meanwhile
            return True

        def session_count(self):
            return 1

    panel._multi_host = Host()
    panel._make_session_stats_handler("s")(StatsSnapshot())


@pytest.mark.parametrize("content", [b'{"viewers": 5}', b"\xff\xfe\x00binary"])
def test_a_trust_import_of_the_wrong_shape_is_reported(monkeypatch, tmp_path, qapp, content):
    path = tmp_path / "trust.json"
    path.write_bytes(content)
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    webrtc_panel._WebRTCHostPanel()._on_import_trust()
    assert len(qapp.messages) == 1


# --- viewer side ------------------------------------------------------------------------------------------

def test_stop_cancels_a_pending_reconnect(monkeypatch, qapp):
    reconnects = []
    monkeypatch.setattr(webrtc_panel._WebRTCViewerPanel, "_on_connect_via_server",
                        lambda self: reconnects.append(self))
    panel = webrtc_panel._WebRTCViewerPanel()
    panel._auto_reconnect_check.setChecked(True)
    panel._server_edit.setText("http://127.0.0.1:9")  # NOSONAR never contacted
    panel._host_id_edit.setText("123456789")
    panel._token_edit.setText("tok")
    panel._reconnect_delay_spin.value = lambda: 0
    panel._maybe_schedule_auto_reconnect()
    panel._on_stop()
    deadline = time.monotonic() + 0.3
    while time.monotonic() < deadline:
        qapp.processEvents()
        time.sleep(0.02)
    assert reconnects == []


def test_a_new_window_opens_with_the_pen_already_on():
    panel = webrtc_panel._WebRTCViewerPanel()
    panel._pen_btn.setChecked(True)
    panel._on_toggle_pen(True)
    assert panel._ensure_screen_window().display._pen_mode is True


def test_an_empty_recording_is_not_reported_saved(qapp):
    panel = webrtc_panel._WebRTCViewerPanel()
    panel._recorder = types.SimpleNamespace(stop=lambda: None, has_output=False, output_path="out.mp4")
    panel._on_toggle_recording(False)
    assert qapp.messages == [_t("rd_webrtc_recording_empty").format(path="out.mp4")]


def test_an_address_book_import_takes_strings_only(monkeypatch, tmp_path):
    path = tmp_path / "book.json"
    path.write_text('{"entries": [{"host_id": 5, "server_url": "u"}, '
                    '{"host_id": "h", "server_url": "u", "mac_address": 7}]}', encoding="utf-8")
    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *args: (str(path), ""))
    panel = webrtc_panel._WebRTCViewerPanel()
    upserts = []
    panel._address_book = types.SimpleNamespace(upsert=lambda **kwargs: upserts.append(kwargs),
                                                list_entries=lambda: [], all_tags=lambda: [])
    panel._on_ab_import()
    assert [(entry["host_id"], entry["mac_address"]) for entry in upserts] == [("h", None)]


# --- Quick Connect --------------------------------------------------------------------------------------------

class _WsViewer:
    connected = True
    remote_host_id = None

    def __init__(self):
        self.disconnected = False

    def disconnect(self, timeout=2.0):
        self.disconnected = True


def test_quick_connect_treats_a_ws_session_as_a_session(monkeypatch):
    viewer = _WsViewer()
    monkeypatch.setattr(registry, "_ws_viewer", viewer)
    screen = connection_screen.QuickConnectScreen()
    screen._refresh_viewer_status()
    assert screen._viewer_badge.text() == _t("rd_quick_connected")
    screen._on_window_closed()
    assert viewer.disconnected


def test_a_session_error_ends_the_quick_connect_session(monkeypatch, qapp):
    viewer = _WsViewer()
    monkeypatch.setattr(registry, "_ws_viewer", viewer)
    screen = connection_screen.QuickConnectScreen()
    screen._open_screen_window("desk")
    screen._on_error("connection reset")
    assert viewer.disconnected and screen._screen_window is None
    assert qapp.messages == ["connection reset"]


def test_an_approval_box_closes_when_the_host_stops_waiting(monkeypatch, qapp):
    from PySide6.QtCore import QTimer
    monkeypatch.setattr(connection_screen, "_APPROVAL_TIMEOUT_S", 0.05)
    # A backstop for the old behaviour, which would otherwise wait forever.
    QTimer.singleShot(5000, lambda: QApplication.activeModalWidget() and QApplication.activeModalWidget().reject())
    request = connection_screen._ApprovalRequest(types.SimpleNamespace(address=("10.0.0.2", 5), transport="tcp"))
    started = time.monotonic()
    connection_screen.QuickConnectScreen()._show_approval_dialog(request)
    assert time.monotonic() - started < 3 and request.decision == "denied" and request.event.is_set()
