"""Remote-desktop panels and their own registry slots (offscreen Qt, fakes only).

Each panel treated the registry's one viewer as its own: a connect elsewhere
left its popup on the last frame, its badge live and its Disconnect pointed at
the other side's session. No test here opens a socket or shows a window.
"""
import gc
import os
import threading

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QCoreApplication, QEvent, QThread  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from je_auto_control.gui.remote_desktop import connection_screen, host_panel, viewer_panel  # noqa: E402
from je_auto_control.gui.remote_desktop._helpers import _t, displaced_notifier  # noqa: E402
from je_auto_control.gui.remote_desktop.remote_screen_window import RemoteScreenWindow  # noqa: E402
from je_auto_control.utils.remote_desktop.address_book import AddressBook  # noqa: E402
from je_auto_control.utils.remote_desktop.connect_coordinator import parse_target  # noqa: E402
from je_auto_control.utils.remote_desktop.registry import (  # noqa: E402
    SCRIPT_OWNER, SLOT_HOST, SLOT_VIEWER, SLOT_WS_VIEWER, registry,
)
from headless._qt_settle import settle, settle_op  # noqa: E402


class _Viewer:
    remote_host_id = None

    def __init__(self, **kwargs):
        self.kwargs, self.connected, self.sent = kwargs, False, []

    def connect(self, timeout=5.0):
        self.connected = True

    def disconnect(self, timeout=2.0):
        self.connected = False

    def send_input(self, action):
        self.sent.append(action)

    def set_file_receiver(self, receiver):
        self.receiver = receiver


class _Host:
    port, connected_clients, host_id = 4321, 0, "123456789"

    def __init__(self, **kwargs):
        self.kwargs, self.is_running = kwargs, False

    def start(self):
        self.is_running = True

    def stop(self, timeout=2.0):
        self.is_running = False

    def latest_frame(self):
        return None


class _Window(RemoteScreenWindow):
    """The popup, never shown: these tests put nothing on a screen."""

    def show(self):
        return None

    def raise_(self):
        return None

    def activateWindow(self):  # noqa: N802  # reason: Qt override
        return None


@pytest.fixture(autouse=True)
def qapp(monkeypatch, tmp_path):
    app = QApplication.instance() or QApplication([])
    messages = []
    # Every box a slot may open is replaced: a modal exec() would block the run.
    for box in ("warning", "information", "question", "critical"):
        monkeypatch.setattr(QMessageBox, box, lambda *args: messages.append(args[-1]))
    for attr in ("_host", "_viewer", "_ws_host", "_ws_viewer"):
        monkeypatch.setattr(registry, attr, None)
    monkeypatch.setattr(registry, "_claims", {})
    for module in (connection_screen, viewer_panel):
        monkeypatch.setattr(module, "RemoteDesktopViewer", _Viewer)
        monkeypatch.setattr(module, "WebSocketDesktopViewer", _Viewer)
        monkeypatch.setattr(module, "RemoteScreenWindow", _Window)
    monkeypatch.setattr(connection_screen, "RemoteDesktopHost", _Host)
    monkeypatch.setattr(host_panel, "RemoteDesktopHost", _Host)
    monkeypatch.setattr(host_panel, "WebSocketDesktopHost", _Host)
    monkeypatch.setattr(viewer_panel, "is_audio_backend_available", lambda: False)
    monkeypatch.setattr(host_panel, "is_audio_backend_available", lambda: False)
    book = AddressBook(tmp_path / "book.json")        # never the operator's own address book
    monkeypatch.setattr(connection_screen, "default_address_book", lambda: book)
    app.messages = messages
    yield app


def _quick(target="tcp"):
    screen = connection_screen.QuickConnectScreen()
    address = {"tcp": "desk:5555", "ws": "ws://desk:8080/"}[target]
    screen._dispatch_target(parse_target(address), "tok")
    settle(screen)
    return screen


def _tab(transport="TCP"):
    panel = viewer_panel._ViewerPanel()
    panel._host_field.setText("desk")
    panel._port.setValue(5555)
    panel._token.setText("tok")
    panel._transport.setCurrentText(transport)
    panel._connect()
    settle(panel)
    return panel


def _script_connect(monkeypatch):
    registry_module = __import__("importlib").import_module(registry.__class__.__module__)
    monkeypatch.setattr(registry_module, "RemoteDesktopViewer", _Viewer)
    monkeypatch.setattr(registry_module, "RemoteDesktopHost", _Host)
    return registry_module


def _idle(panel):
    return panel._screen_window is None and panel._own_viewer() is None


# --- each panel owns what it opened ----------------------------------------------------------------------------

def test_each_panel_registers_under_its_own_owner():
    first, second = _quick(), connection_screen.QuickConnectScreen()
    assert first._owner != second._owner
    assert registry.owner_of(SLOT_VIEWER) == first._owner
    assert first._own_viewer().connected and first._screen_window is not None
    assert first._viewer_badge.text() == _t("rd_quick_connected")
    # A second Quick Connect screen does not take the first one's session for its own.
    second._refresh_status()
    assert second._own_viewer() is None
    assert second._viewer_badge.text() == _t("rd_quick_disconnected")


def test_quick_connect_disconnect_leaves_the_viewer_tabs_session_alone():
    tab = _tab()
    screen = connection_screen.QuickConnectScreen()
    screen._disconnect()
    screen._on_window_closed()
    screen._on_error("stale error from an earlier session")
    assert tab._own_viewer().connected and tab._screen_window is not None


def test_the_viewer_tabs_disconnect_leaves_quick_connects_session_alone():
    screen = _quick()
    tab = viewer_panel._ViewerPanel()
    tab._disconnect()
    tab._on_error_main("stale error")
    assert screen._own_viewer().connected and screen._screen_window is not None


def test_a_panel_only_drives_its_own_viewer():
    screen = _quick()
    theirs = screen._own_viewer()
    tab = viewer_panel._ViewerPanel()
    tab._send({"action": "type", "text": "x"})
    tab._push_clipboard_to_host()
    assert theirs.sent == []
    screen._send_input({"action": "type", "text": "y"})
    assert theirs.sent == [{"action": "type", "text": "y"}]


# --- being replaced --------------------------------------------------------------------------------------------

def test_the_viewer_tab_connecting_closes_quick_connects_session():
    screen = _quick()
    old = screen._own_viewer()
    tab = _tab()
    assert not old.connected and _idle(screen)
    assert screen._viewer_badge.text() == _t("rd_quick_disconnected")
    # Its Disconnect no longer reaches the session that replaced it.
    screen._disconnect()
    assert tab._own_viewer().connected and tab._screen_window is not None


def test_quick_connect_connecting_closes_the_viewer_tabs_session():
    tab = _tab()
    old = tab._own_viewer()
    screen = _quick()
    assert not old.connected and _idle(tab) and tab._connected is False
    assert tab._status.text() == _t("rd_viewer_displaced")
    assert tab._badge.text() == _t("rd_badge_idle")
    tab._disconnect()
    assert screen._own_viewer().connected


def test_a_ws_quick_connect_session_survives_a_tcp_connect_elsewhere():
    screen = _quick("ws")
    tab = _tab()
    assert registry.owner_of(SLOT_WS_VIEWER) == screen._owner
    assert screen._own_viewer().connected and screen._screen_window is not None
    assert tab._own_viewer().connected


def test_quick_connect_changing_transport_ends_its_previous_session():
    screen = _quick("ws")
    first = screen._own_viewer()
    screen._dispatch_target(parse_target("desk:5555"), "tok")
    settle(screen)
    assert not first.connected and registry.owner_of(SLOT_WS_VIEWER) is None
    assert registry.owner_of(SLOT_VIEWER) == screen._owner and screen._screen_window is not None


def test_a_panel_reconnecting_keeps_its_window():
    tab = _tab()
    first = tab._own_viewer()
    tab._connect()
    settle(tab)
    assert not first.connected and tab._own_viewer().connected
    assert tab._screen_window is not None and tab._status.text() != _t("rd_viewer_displaced")


def test_a_late_notice_about_an_old_session_does_not_close_the_new_one():
    tab = _tab()
    tab._on_displaced(SLOT_VIEWER, SCRIPT_OWNER)      # queued before the reconnect, delivered after
    assert tab._own_viewer().connected and tab._screen_window is not None
    screen = _quick("ws")
    screen._on_displaced(SLOT_VIEWER, SCRIPT_OWNER)
    assert screen._own_viewer().connected and screen._screen_window is not None


def test_a_script_connect_closes_the_panels_session(monkeypatch):
    _script_connect(monkeypatch)
    tab = _tab()
    registry.connect_viewer("desk", 5555, "tok")
    assert _idle(tab) and tab._status.text() == _t("rd_viewer_displaced")
    assert registry.viewer_status()["owner"] == SCRIPT_OWNER
    tab._disconnect()
    assert registry.viewer_status()["connected"] is True


def test_a_script_disconnect_closes_the_panels_session():
    screen = _quick()
    registry.disconnect_viewer()
    assert _idle(screen) and screen._viewer_badge.text() == _t("rd_quick_disconnected")


def test_a_panel_takes_over_a_scripts_session(monkeypatch):
    _script_connect(monkeypatch)
    registry.connect_viewer("desk", 5555, "tok")
    scripted = registry.viewer
    screen = connection_screen.QuickConnectScreen()
    screen._refresh_status()
    assert screen._viewer_badge.text() == _t("rd_quick_disconnected")   # not its session
    screen._disconnect()
    assert scripted.connected
    screen._dispatch_target(parse_target("desk:5555"), "tok")
    settle(screen)
    assert not scripted.connected and registry.owner_of(SLOT_VIEWER) == screen._owner


# --- hosts -----------------------------------------------------------------------------------------------------

def _host_tab():
    panel = host_panel._HostPanel()
    panel._token.setText("tok")
    panel._start()
    assert settle_op(panel._host_op)
    return panel


def test_starting_a_host_leaves_every_viewer_alone():
    tab, screen = _tab(), _quick("ws")
    _host_tab()
    connection_screen.QuickConnectScreen()._start_hosting()
    assert tab._own_viewer().connected and screen._own_viewer().connected


def test_quick_connect_hosting_replaces_the_host_tabs_host_and_tells_it(qapp):
    tab = _host_tab()
    first = registry.host
    assert tab._shared is not None and registry.owner_of(SLOT_HOST) == tab._owner
    screen = connection_screen.QuickConnectScreen()
    screen._start_hosting()
    assert not first.is_running and registry.owner_of(SLOT_HOST) == screen._owner
    assert tab._shared is None                       # no share text for a host it does not run
    tab._copy_share_text()
    assert qapp.messages == [_t("rd_host_copy_share_unavailable")] and registry.host.is_running


def test_stop_stops_the_host_on_show_and_tells_its_owner():
    tab = _host_tab()
    running = registry.host
    screen = connection_screen.QuickConnectScreen()
    assert screen._host_id_label.text() != "---"     # it shows the host as running
    screen._stop_hosting()
    assert not running.is_running and registry.host is None and tab._shared is None


def test_a_script_stopping_the_host_clears_the_panels_share_text():
    tab = _host_tab()
    registry.stop_host()
    assert tab._shared is None and registry.host_status()["running"] is False


# --- delivery --------------------------------------------------------------------------------------------------

def _pump_until(app, predicate, rounds=200):
    for _ in range(rounds):
        app.processEvents()
        if predicate():
            return True
        QThread.msleep(5)
    return predicate()


def test_a_notice_from_another_thread_is_handled_on_the_gui_thread(qapp, monkeypatch):
    tab = _tab()
    handled = []
    original = tab._on_displaced
    monkeypatch.setattr(tab, "_on_displaced", lambda slot, by: (
        handled.append(threading.current_thread()), original(slot, by)))
    tab._displaced.disconnect()
    tab._displaced.connect(tab._on_displaced)
    worker = threading.Thread(target=registry.disconnect_viewer, daemon=True)
    worker.start()
    worker.join(5.0)
    assert handled == [] and tab._screen_window is not None      # nothing touched off the GUI thread
    assert _pump_until(qapp, lambda: bool(handled))
    assert handled == [threading.main_thread()] and _idle(tab)


def test_a_notice_for_a_destroyed_panel_is_dropped(qapp):
    import shiboken6
    tab = _tab()
    notify = displaced_notifier(tab)
    registry.release(SLOT_VIEWER, tab._owner)
    tab._close_screen_window()
    shiboken6.delete(tab)                             # the Qt object goes, the wrapper stays
    notify(SLOT_VIEWER, SCRIPT_OWNER)
    del tab
    gc.collect()
    notify(SLOT_VIEWER, SCRIPT_OWNER)                 # and with the wrapper collected too
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    qapp.processEvents()


def test_a_session_outliving_its_panel_can_still_be_replaced(qapp, monkeypatch):
    _script_connect(monkeypatch)
    tab = _tab()
    orphan = registry.viewer
    tab._close_screen_window()
    tab.deleteLater()
    del tab
    gc.collect()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    assert registry.connect_viewer("desk", 5555, "tok")["connected"] is True
    assert not orphan.connected
