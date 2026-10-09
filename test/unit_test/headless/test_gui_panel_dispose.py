"""``dispose()`` on the remote-desktop panels and on the tabs that start a worker on demand.

Offscreen Qt with fake viewers, hosts and backends; nothing opens a socket,
shows a window or reaches a model. ``RemoteDesktopTab.dispose()`` used to stop
timers only: a connect still out went on, the pop-out windows stayed, and a
WebRTC host kept sharing the screen with no panel left to stop it. The tabs
that start a worker only when asked (computer use, DAG, VLM, USB browser) had
no ``dispose()`` at all, so a released tab's agent run kept going.
"""
import os
import threading
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QObject, QTimer, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget  # noqa: E402

from je_auto_control.gui import _dispose, computer_use_tab, dag_tab, usb_browser_tab, vlm_tab  # noqa: E402
from je_auto_control.gui._worker_thread import cancel_workers, start_worker  # noqa: E402
from je_auto_control.gui.remote_desktop import connection_screen, host_panel, viewer_panel  # noqa: E402
from je_auto_control.gui.remote_desktop.remote_screen_window import RemoteScreenWindow  # noqa: E402
from je_auto_control.utils.remote_desktop.address_book import AddressBook  # noqa: E402
from je_auto_control.utils.remote_desktop.connect_coordinator import parse_target  # noqa: E402
from je_auto_control.utils.remote_desktop.registry import SLOT_HOST, SLOT_VIEWER, registry  # noqa: E402
from headless._qt_settle import deleting, pump_until, settle, settle_op  # noqa: E402


class _Viewer:
    remote_host_id = None
    gate = None
    made = []

    def __init__(self, **kwargs):
        self.kwargs, self.connected, self.disconnects = kwargs, False, 0
        _Viewer.made.append(self)

    def connect(self, timeout=5.0):
        if _Viewer.gate is not None:
            _Viewer.gate.wait(30.0)
        self.connected = True

    def disconnect(self, timeout=2.0):
        self.connected = False
        self.disconnects += 1

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
    for box in ("warning", "information", "question", "critical"):
        monkeypatch.setattr(QMessageBox, box, lambda *args: None)
    for attr in ("_host", "_viewer", "_ws_host", "_ws_viewer"):
        monkeypatch.setattr(registry, attr, None)
    monkeypatch.setattr(registry, "_claims", {})
    monkeypatch.setattr(_Viewer, "gate", None)
    monkeypatch.setattr(_Viewer, "made", [])
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
    return app


@pytest.fixture(autouse=True)
def _panels_deleted():
    """Each test deletes the parentless panels it built (see ``_qt_settle.deleting``)."""
    with deleting(viewer_panel._ViewerPanel, host_panel._HostPanel, connection_screen.QuickConnectScreen,
                  computer_use_tab.ComputerUseTab, dag_tab.DagTab, vlm_tab.VLMTab,
                  usb_browser_tab.UsbBrowserTab, _Owner):
        yield


def _active_timers(widget):
    return sum(1 for timer in widget.findChildren(QTimer) if timer.isActive())


def _viewer_tab():
    panel = viewer_panel._ViewerPanel()
    panel._host_field.setText("desk")
    panel._port.setValue(5555)
    panel._token.setText("tok")
    panel._connect()
    return panel


# --- remote desktop: the panels that keep their session in the registry ------------------------------------------

def test_the_viewer_panel_closes_its_window_and_leaves_the_session_in_the_registry():
    panel = _viewer_tab()
    assert settle(panel)
    viewer = panel._own_viewer()
    assert viewer.connected
    assert panel._screen_window is not None
    panel.dispose()
    assert panel._screen_window is None
    assert _active_timers(panel) == 0
    assert registry.owned(SLOT_VIEWER, panel._owner) is viewer
    assert viewer.connected
    panel.dispose()                         # safe to call twice
    assert viewer.connected


def test_the_viewer_panel_gives_up_a_connect_that_has_not_answered(monkeypatch):
    monkeypatch.setattr(_Viewer, "gate", threading.Event())
    panel = _viewer_tab()
    assert panel._connect_task is not None
    panel.dispose()
    assert panel._connect_task is None
    _Viewer.gate.set()
    # The viewer that connects anyway is disconnected, and never adopted.
    assert pump_until(lambda: _Viewer.made[-1].disconnects == 1)
    assert registry.owner_of(SLOT_VIEWER) is None
    assert panel._screen_window is None


def test_quick_connect_stops_polling_and_leaves_its_host_and_session_running():
    screen = connection_screen.QuickConnectScreen()
    screen._host_token.setText("tok")
    screen._start_hosting()
    screen._dispatch_target(parse_target("desk:5555"), "tok")
    assert settle(screen)
    host, viewer = registry.host, screen._own_viewer()
    assert host.is_running
    assert viewer.connected
    assert screen._screen_window is not None
    assert _active_timers(screen) == 1
    screen.dispose()
    assert _active_timers(screen) == 0
    assert screen._screen_window is None
    assert registry.owner_of(SLOT_HOST) == screen._owner
    assert host.is_running
    assert registry.owned(SLOT_VIEWER, screen._owner) is viewer
    assert viewer.connected
    screen.dispose()


def test_quick_connect_gives_up_a_connect_that_has_not_answered(monkeypatch):
    monkeypatch.setattr(_Viewer, "gate", threading.Event())
    screen = connection_screen.QuickConnectScreen()
    screen._dispatch_target(parse_target("desk:5555"), "tok")
    assert screen._connect_task is not None
    screen.dispose()
    assert screen._connect_task is None
    _Viewer.gate.set()
    assert pump_until(lambda: _Viewer.made[-1].disconnects == 1)
    assert screen._own_viewer() is None
    assert screen._screen_window is None


# --- remote desktop: the WebRTC panels, whose session nobody else could reach -------------------------------------

class _Gate:
    def __init__(self):
        self.entered, self.release, self.threads = threading.Event(), threading.Event(), []

    def __call__(self, *_args, **_kwargs):
        self.threads.append(threading.current_thread())
        self.entered.set()
        self.release.wait(30.0)


@pytest.fixture
def webrtc():
    pytest.importorskip("av", exc_type=ImportError)
    pytest.importorskip("aiortc", exc_type=ImportError)
    from je_auto_control.gui.remote_desktop import webrtc_panel
    with deleting(webrtc_panel._WebRTCHostPanel, webrtc_panel._WebRTCViewerPanel):
        yield webrtc_panel


def test_the_webrtc_host_panel_stops_the_host_only_it_could_stop(webrtc):
    panel = webrtc._WebRTCHostPanel()
    gate = _Gate()
    panel._multi_host = types.SimpleNamespace(stop_all=gate, session_count=lambda: 0)
    panel.dispose()
    assert panel._multi_host is None
    assert gate.entered.wait(10.0)
    assert gate.threads[0] is not threading.main_thread()
    panel.dispose()                         # safe to call twice: no host left
    gate.release.set()
    assert settle_op(panel._stops)
    assert len(gate.threads) == 1


def test_the_webrtc_viewer_panel_ends_its_session_and_cancels_the_reconnect(webrtc):
    panel = webrtc._WebRTCViewerPanel()
    gate = _Gate()
    panel._viewer = types.SimpleNamespace(stop=gate, authenticated=False, _pc=None)
    panel._reconnect_timer.start(60_000)
    panel.dispose()
    assert panel._viewer is None
    assert not panel._reconnect_timer.isActive()
    assert gate.entered.wait(10.0)
    assert gate.threads[0] is not threading.main_thread()
    panel._maybe_schedule_auto_reconnect()  # a late "disconnected" from the session that was ended
    assert not panel._reconnect_timer.isActive()
    gate.release.set()
    assert settle_op(panel._stops)
    panel.dispose()


def test_the_remote_desktop_tab_disposes_every_sub_panel(webrtc, monkeypatch):
    from je_auto_control.gui.remote_desktop import tab as tab_module
    with deleting(tab_module.RemoteDesktopTab):
        tab = tab_module.RemoteDesktopTab()
        assert len(tab._sub_panels) == 5
        called = []
        for panel in tab._sub_panels:
            assert callable(getattr(panel, "dispose", None)), type(panel).__name__
            monkeypatch.setattr(panel, "dispose", lambda name=type(panel).__name__: called.append(name))
        tab.dispose()
        assert called == ["QuickConnectScreen", "_HostPanel", "_ViewerPanel", "_WebRTCHostPanel",
                          "_WebRTCViewerPanel"]
        assert _active_timers(tab) == 0


# --- tabs that start a worker only when asked --------------------------------------------------------------------

def test_a_released_computer_use_tab_stops_its_run_and_drops_the_outcome(monkeypatch):
    seen = []

    def run(stop_event=None, **_params):
        seen.append(stop_event)
        assert stop_event.wait(30.0)
        return "stopped"

    monkeypatch.setattr(computer_use_tab, "run_computer_use", run)
    monkeypatch.setattr(computer_use_tab, "result_to_dict", lambda result: {"succeeded": True, "result": result})
    tab = computer_use_tab.ComputerUseTab()
    tab._spawn_worker({"goal": "anything"})
    assert pump_until(lambda: bool(seen))
    before = tab._status.text()
    tab.dispose()
    assert seen[0].is_set()
    assert pump_until(lambda: tab._thread is None)      # the thread's end is still booked
    assert tab._status.text() == before
    assert tab._output.toPlainText() == ""
    tab.dispose()


def test_a_released_dag_tab_stops_its_run_and_drops_the_outcome(monkeypatch):
    seen = []

    def run(_definition, max_parallel=1, stop_event=None):
        seen.append(stop_event)
        assert stop_event.wait(30.0)
        return types.SimpleNamespace(succeeded=True, elapsed_s=0.0, nodes={"a": None})

    monkeypatch.setattr(dag_tab, "run_dag", run)
    tab = dag_tab.DagTab()
    tab._spawn_worker({"nodes": []})
    assert pump_until(lambda: bool(seen))
    tab.dispose()
    assert seen[0].is_set()
    assert pump_until(lambda: tab._thread is None)
    assert tab._table.rowCount() == 0


def test_a_released_vlm_tab_drops_the_answer_of_the_request_still_out(monkeypatch):
    release = threading.Event()

    def locate(_description, model=None):
        release.wait(30.0)
        return (10, 20)

    monkeypatch.setattr(vlm_tab, "locate_by_description", locate)
    tab = vlm_tab.VLMTab()
    tab._description.setText("the button")
    tab._on_locate()
    assert tab._vlm_thread is not None
    tab.dispose()
    release.set()
    assert pump_until(lambda: tab._vlm_thread is None)
    assert tab._last_result.text() == ""
    assert tab._status.text() == ""


def test_a_released_usb_browser_tab_drops_the_open_still_out(monkeypatch):
    release = threading.Event()

    def open_local(**_kwargs):
        release.wait(30.0)
        return b"\x12\x01"

    monkeypatch.setattr(usb_browser_tab, "open_local_descriptor", open_local)
    tab = usb_browser_tab.UsbBrowserTab()
    tab._start_local_open("1234", "5678", None)
    before = tab._status_label.text()
    tab.dispose()
    release.set()
    assert pump_until(lambda: tab._open_thread is None)
    assert tab._status_label.text() == before


# --- the helper --------------------------------------------------------------------------------------------------

class _Worker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, fail=False):
        super().__init__()
        self.stop, self._fail = threading.Event(), fail

    def request_stop(self):
        self.stop.set()

    def run(self):
        self.stop.wait(30.0)
        if self._fail:
            self.failed.emit("broken")
        else:
            self.finished.emit("value")


class _Owner(QWidget):
    def __init__(self):
        super().__init__()
        self.seen = []

    def done(self, value):
        self.seen.append(("done", value))

    def fail(self, message):
        self.seen.append(("fail", message))

    def ended(self):
        self.seen.append("ended")


@pytest.mark.parametrize("fail", [False, True])
def test_cancelling_an_owners_workers_stops_them_and_keeps_only_the_end(fail):
    owner, other = _Owner(), _Owner()
    worker, bystander = _Worker(fail), _Worker()
    start_worker(owner, worker, on_done=owner.done, on_fail=owner.fail, on_thread_done=owner.ended)
    start_worker(other, bystander, on_done=other.done, on_fail=other.fail, on_thread_done=other.ended)
    assert cancel_workers(owner) == 1
    assert worker.stop.is_set()
    assert not bystander.stop.is_set()
    assert pump_until(lambda: owner.seen == ["ended"])
    bystander.stop.set()
    assert pump_until(lambda: other.seen == [("done", "value"), "ended"])
    assert cancel_workers(owner) == 0


def test_release_resources_cancels_the_owners_bare_workers():
    owner, worker = _Owner(), _Worker()
    start_worker(owner, worker, on_done=owner.done, on_fail=owner.fail, on_thread_done=owner.ended)
    _dispose.release_resources(owner)
    assert worker.stop.is_set()
    assert pump_until(lambda: owner.seen == ["ended"])
