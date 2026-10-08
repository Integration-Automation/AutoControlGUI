"""GUI background work: the window keeps ticking, cancel and owner death release what the work holds.

Plan F task F3 (offscreen Qt, fakes only -- no network, device or window). A
tab that waited on the network in a slot froze the window for the whole wait;
work handed to a thread had no way to be cancelled, so a session it had opened
stayed open after the tab was closed; and a result that arrived after its tab
was destroyed had nowhere safe to go.
"""
import functools
import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QEvent, QObject, QThread, QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication, QLabel, QWidget  # noqa: E402

from je_auto_control.gui import _worker_thread  # noqa: E402
from je_auto_control.gui.task_controller import (  # noqa: E402
    CancellationToken, TaskCancelled, TaskController, TaskTimeout, TaskUsageError,
    task_controller,
)
from je_auto_control.utils.exception.exceptions import AutoControlException  # noqa: E402


@pytest.fixture()
def qapp():
    return QApplication.instance() or QApplication([])


def _pump(app, predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while not predicate() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    return predicate()


def _destroy(app, widget):
    widget.deleteLater()
    app.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    app.processEvents()


class _FakeNetwork:
    """A backend whose sessions are counted, and whose connect waits like a slow host."""

    def __init__(self):
        self.active = 0
        self.lock = threading.Lock()
        self.release = threading.Event()     # set: the "host" answers
        self.entered = threading.Event()

    def open(self):
        with self.lock:
            self.active += 1
        return _FakeSession(self)

    def connect(self, token: CancellationToken):
        """Open a session, then wait for the host; the session is the result."""
        session = self.open()
        token.on_cancel(session.close)
        self.entered.set()
        while not self.release.wait(0.01):
            token.raise_if_cancelled()
        return session


class _FakeSession:
    def __init__(self, network):
        self._network = network
        self._closed = False

    def close(self):
        with self._network.lock:
            if not self._closed:
                self._closed = True
                self._network.active -= 1


def test_ui_tick_continues_during_network_wait(qapp):
    network = _FakeNetwork()
    owner = QWidget()
    ticks, results = [], []
    timer = QTimer(owner)
    timer.setInterval(5)
    timer.timeout.connect(lambda: ticks.append(time.monotonic()))
    timer.start()
    handle = TaskController().submit(network.connect, owner=owner)
    handle.result.connect(results.append)
    assert network.entered.wait(3.0), "the work never started"
    # The "network" is still waiting: the event loop must keep delivering ticks.
    assert _pump(qapp, lambda: len(ticks) >= 5), "the GUI thread did not tick during the wait"
    ui_ticks_during_work = len(ticks)
    assert ui_ticks_during_work > 0 and results == [] and handle.isRunning()
    network.release.set()
    assert _pump(qapp, lambda: bool(results))
    assert handle.state == "done" and network.active == 1
    results[0].close()
    timer.stop()
    _destroy(qapp, owner)


def test_cancel_releases_session(qapp):
    network = _FakeNetwork()
    owner = QWidget()
    controller = TaskController()
    outcomes = []
    handle = controller.submit(network.connect, owner=owner)
    handle.result.connect(lambda value: outcomes.append(("result", value)))
    handle.error.connect(lambda error: outcomes.append(("error", error)))
    assert network.entered.wait(3.0) and network.active == 1
    handle.cancel()
    # Released at once, on the cancelling thread -- not when the backend gives up.
    assert network.active == 0
    assert handle.wait(3.0), "the work ignored the cancellation"
    assert _pump(qapp, lambda: not controller.active_count())
    active_sessions_after_close = network.active
    assert active_sessions_after_close == 0
    assert outcomes == [] and handle.state == "cancelled"
    _destroy(qapp, owner)


def test_a_result_finished_before_cancel_is_discarded_not_delivered(qapp):
    network = _FakeNetwork()
    network.release.set()                      # the host answers at once
    owner = QWidget()
    delivered = []
    handle = TaskController().submit(network.connect, owner=owner,
                                     discard=lambda session: session.close())
    handle.result.connect(delivered.append)
    assert handle.wait(3.0) and network.active == 1
    handle.cancel()                            # the result is done but not delivered yet
    qapp.processEvents()
    assert delivered == [] and network.active == 0


def test_owner_death_drops_result(qapp):
    network = _FakeNetwork()
    owner = QLabel("owner")
    received = []

    def on_result(session):
        received.append(session)
        owner.setText("connected")             # would raise on a deleted widget

    handle = TaskController().submit(network.connect, owner=owner,
                                     discard=lambda session: session.close())
    handle.result.connect(on_result)
    assert network.entered.wait(3.0)
    _destroy(qapp, owner)
    network.release.set()                      # the answer arrives after the tab is gone
    assert _pump(qapp, lambda: not _worker_thread.running_threads())
    result_after_owner_death = received[0] if received else None
    assert result_after_owner_death is None
    assert network.active == 0, "the session the dead tab asked for stayed open"


def test_owner_death_after_completion_discards_the_undelivered_result(qapp):
    network = _FakeNetwork()
    network.release.set()
    owner = QWidget()
    received = []
    handle = TaskController().submit(network.connect, owner=owner,
                                     discard=lambda session: session.close())
    handle.result.connect(received.append)
    assert handle.wait(3.0) and network.active == 1     # done; the delivery is still queued
    owner.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    qapp.processEvents()
    assert received == [] and network.active == 0


def test_no_worker_touches_widget(qapp):
    owner = QLabel("idle")
    gui_thread = qapp.thread()
    seen = {}

    def work(token):
        seen["work_on_gui"] = QThread.currentThread() is gui_thread
        seen["args"] = type(token)
        token.report_progress(40)
        return "payload"

    handle = TaskController().submit(work, owner=owner)
    # Lambdas: a signal emitted on a worker thread would run these there.
    handle.progress.connect(lambda value: seen.update(progress=value,
                                                      progress_gui=QThread.currentThread() is gui_thread))
    handle.result.connect(lambda value: (owner.setText(value),
                                         seen.update(result_gui=QThread.currentThread() is gui_thread)))
    handle.finished.connect(lambda: seen.update(finished_gui=QThread.currentThread() is gui_thread))
    assert _pump(qapp, lambda: "finished_gui" in seen)
    assert seen["work_on_gui"] is False and seen["args"] is CancellationToken
    assert seen["progress"] == 40 and seen["progress_gui"] and seen["result_gui"] and seen["finished_gui"]
    assert owner.text() == "payload"

    # Work that could reach a widget is refused before it starts.
    with pytest.raises(TaskUsageError):
        TaskController().submit(owner.setText, owner=owner)                  # a widget's own method
    with pytest.raises(TaskUsageError):
        TaskController().submit(lambda _token: owner.text(), owner=owner)    # closes over the widget
    with pytest.raises(TaskUsageError):
        TaskController().submit(functools.partial(lambda label, _token: label, owner), owner=owner)
    assert issubclass(TaskUsageError, AutoControlException)
    _destroy(qapp, owner)


def test_errors_arrive_typed_on_the_gui_thread(qapp):
    owner = QWidget()
    errors = []

    class BackendDown(AutoControlException):
        pass

    def work(_token):
        raise BackendDown("host unreachable")

    handle = TaskController().submit(work, owner=owner)
    handle.error.connect(lambda error: errors.append((error, QThread.currentThread() is qapp.thread())))
    assert _pump(qapp, lambda: bool(errors))
    assert isinstance(errors[0][0], BackendDown) and errors[0][1] is True
    assert handle.state == "failed"
    _destroy(qapp, owner)


def test_a_timeout_cancels_the_work_and_reports_it(qapp):
    network = _FakeNetwork()
    owner = QWidget()
    errors, deadlines = [], []

    def work(token):
        deadlines.append(token.remaining(default=99.0))
        return network.connect(token)

    handle = TaskController().submit(work, owner=owner, timeout_s=0.1)
    handle.error.connect(errors.append)
    assert _pump(qapp, lambda: bool(errors))
    assert isinstance(errors[0], TaskTimeout) and isinstance(errors[0], TimeoutError)
    assert handle.state == "timed_out" and handle.wait(3.0)
    assert network.active == 0 and 0 < deadlines[0] <= 0.1
    _destroy(qapp, owner)


def test_the_token_wakes_a_waiting_backend_and_raises_typed():
    token = CancellationToken()
    assert token.remaining(default=7.0) == pytest.approx(7.0)
    released = []
    token.on_cancel(lambda: released.append("a"))
    threading.Timer(0.05, token.cancel).start()
    started = time.monotonic()
    assert token.wait(5.0) is True and time.monotonic() - started < 2.0
    assert released == ["a"] and token.cancelled
    token.on_cancel(lambda: released.append("late"))       # already cancelled: released at once
    assert released == ["a", "late"]
    with pytest.raises(TaskCancelled):
        token.raise_if_cancelled()
    assert issubclass(TaskCancelled, AutoControlException)


def test_a_failing_release_callback_does_not_stop_the_others():
    token = CancellationToken()
    released = []

    def broken():
        raise OSError("already closed")

    token.on_cancel(lambda: released.append("first"))
    token.on_cancel(broken)
    token.on_cancel(lambda: released.append("last"))
    token.cancel()
    assert released == ["last", "first"]


def test_cancel_all_for_an_owner_leaves_other_owners_running(qapp):
    one, other = _FakeNetwork(), _FakeNetwork()
    closing, staying = QWidget(), QWidget()
    controller = TaskController()
    controller.submit(one.connect, owner=closing)
    kept = controller.submit(other.connect, owner=staying)
    assert one.entered.wait(3.0) and other.entered.wait(3.0)
    controller.cancel_all(closing)
    assert one.active == 0 and other.active == 1 and kept.isRunning()
    controller.cancel_all()
    assert other.active == 0
    assert _pump(qapp, lambda: controller.active_count() == 0)
    _destroy(qapp, closing)
    _destroy(qapp, staying)


def test_the_old_helper_and_the_controller_share_one_registry(qapp):
    """``start_worker`` is the thread layer under the controller, not a rival."""
    network = _FakeNetwork()
    owner = QObject()
    before = _worker_thread.running_threads()
    handle = task_controller().submit(network.connect, owner=owner)
    assert network.entered.wait(3.0)
    assert _worker_thread.running_threads() == before + 1
    handle.cancel()
    assert _pump(qapp, lambda: _worker_thread.running_threads() == before)
    assert task_controller() is task_controller()
    owner.deleteLater()


# --- the tabs moved onto the controller ---------------------------------------------------------------------

class _SlowViewer:
    """A remote-desktop viewer whose connect waits like a host that accepts and says nothing."""

    remote_host_id = None
    made = []
    refuse = False

    def __init__(self, **kwargs):
        self.kwargs, self.connected, self.disconnects = kwargs, False, 0
        self.answer = threading.Event()
        self.timeout = None
        type(self).made.append(self)

    def connect(self, timeout=5.0):
        self.timeout = timeout
        if not self.answer.wait(5.0) or self.refuse:
            raise OSError("refused")
        self.connected = True

    def disconnect(self, timeout=2.0):
        self.disconnects += 1
        self.connected = False

    def set_file_receiver(self, receiver):
        self.receiver = receiver


@pytest.fixture()
def remote_panels(qapp, monkeypatch, tmp_path):
    from PySide6.QtWidgets import QMessageBox
    from je_auto_control.gui.remote_desktop import connection_screen, viewer_panel
    from je_auto_control.utils.remote_desktop.address_book import AddressBook
    from je_auto_control.utils.remote_desktop.registry import registry
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[-1]))
    for slot in ("_viewer", "_ws_viewer", "_host"):
        monkeypatch.setattr(registry, slot, None)
    monkeypatch.setattr(_SlowViewer, "made", [])
    monkeypatch.setattr(viewer_panel, "RemoteDesktopViewer", _SlowViewer)
    monkeypatch.setattr(connection_screen, "RemoteDesktopViewer", _SlowViewer)
    monkeypatch.setattr(viewer_panel, "is_audio_backend_available", lambda: False)
    book = AddressBook(tmp_path / "book.json")           # never the operator's own address book
    monkeypatch.setattr(connection_screen, "default_address_book", lambda: book)
    return viewer_panel, connection_screen, registry, warnings


def _viewer_tab(viewer_panel):
    panel = viewer_panel._ViewerPanel()
    panel._host_field.setText("desk")
    panel._port.setValue(5555)
    panel._token.setText("tok")
    return panel


def test_the_viewer_tab_connects_without_holding_the_gui_thread(qapp, remote_panels):
    viewer_panel, _screen, registry, warnings = remote_panels
    panel = _viewer_tab(viewer_panel)
    started = time.monotonic()
    panel._connect()
    assert time.monotonic() - started < 1.0, "the slot waited for the host"
    viewer = _SlowViewer.made[0]
    ticks = []
    timer = QTimer(panel)
    timer.timeout.connect(lambda: ticks.append(1))
    timer.start(5)
    assert _pump(qapp, lambda: len(ticks) >= 5) and panel._connect_task is not None
    assert registry.owned("viewer", panel._owner) is None and panel._screen_window is None
    viewer.answer.set()
    assert _pump(qapp, lambda: panel._connect_task is None)
    assert registry.owned("viewer", panel._owner) is viewer and panel._screen_window is not None
    assert viewer.timeout == pytest.approx(5.0) and warnings == []
    timer.stop()
    panel._disconnect()


def test_disconnect_during_a_connect_drops_the_viewer_that_answers_late(qapp, remote_panels):
    viewer_panel, _screen, registry, warnings = remote_panels
    panel = _viewer_tab(viewer_panel)
    panel._connect()
    viewer = _SlowViewer.made[0]
    assert _pump(qapp, lambda: viewer.timeout is not None)
    panel._disconnect()                       # the operator gives up
    assert panel._connect_task is None
    viewer.answer.set()                       # ... and then the host answers
    assert _pump(qapp, lambda: viewer.disconnects >= 1), "the late session stayed open"
    assert not viewer.connected and registry.owned("viewer", panel._owner) is None
    assert panel._screen_window is None and warnings == []


def test_a_second_connect_supersedes_the_first(qapp, remote_panels):
    viewer_panel, _screen, registry, _warnings = remote_panels
    panel = _viewer_tab(viewer_panel)
    panel._connect()
    panel._connect()
    first, second = _SlowViewer.made
    first.answer.set()
    second.answer.set()
    assert _pump(qapp, lambda: panel._connect_task is None and first.disconnects >= 1)
    assert registry.owned("viewer", panel._owner) is second and not first.connected
    panel._disconnect()


def test_quick_connect_does_not_hold_the_gui_thread(qapp, remote_panels):
    from je_auto_control.utils.remote_desktop.connect_coordinator import parse_target
    _panel, connection_screen, registry, warnings = remote_panels
    screen = connection_screen.QuickConnectScreen()
    started = time.monotonic()
    screen._dispatch_target(parse_target("desk:5555"), "tok")
    assert time.monotonic() - started < 1.0
    viewer = _SlowViewer.made[0]
    assert screen._connect_task is not None and registry.owned("viewer", screen._owner) is None
    viewer.answer.set()
    assert _pump(qapp, lambda: screen._connect_task is None)
    assert registry.owned("viewer", screen._owner) is viewer and screen._screen_window is not None
    screen._disconnect()
    # A refusal arrives as a warning, on the GUI thread, and adopts nothing.
    monkeypatch_refuse = _SlowViewer.refuse
    _SlowViewer.refuse = True
    try:
        screen._dispatch_target(parse_target("desk:5555"), "tok")
        _SlowViewer.made[1].answer.set()
        assert _pump(qapp, lambda: screen._connect_task is None)
    finally:
        _SlowViewer.refuse = monkeypatch_refuse
    assert warnings == ["refused"] and registry.owned("viewer", screen._owner) is None
    screen._refresh_timer.stop()


@pytest.fixture()
def webrtc_panel(qapp, monkeypatch):
    pytest.importorskip("av")
    pytest.importorskip("aiortc")
    from PySide6.QtWidgets import QMessageBox
    from je_auto_control.gui.remote_desktop import webrtc_panel as module
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[-1]))
    module.warnings = warnings
    yield module
    del module.warnings


class _SlowSdp:
    """Stands in for a WebRTC host or viewer whose SDP step waits on ICE gathering."""

    def __init__(self):
        self.release, self.entered = threading.Event(), threading.Event()
        self.stopped, self.on_gui, self.fail = [], [], None

    def _wait(self):
        self.on_gui.append(QThread.currentThread() is QApplication.instance().thread())
        self.entered.set()
        self.release.wait(5.0)
        if self.fail is not None:
            raise self.fail

    def create_session_offer(self):
        self._wait()
        return "session-1", "v=0 offer"

    def process_offer(self, offer_sdp, expected_dtls_fingerprint=None):
        self._wait()
        return f"answer to {offer_sdp}"

    def stop_session(self, session_id):
        self.stopped.append(session_id)


def test_the_webrtc_host_makes_its_offer_off_the_gui_thread(qapp, webrtc_panel):
    panel = webrtc_panel._WebRTCHostPanel()
    host = _SlowSdp()
    panel._multi_host = host
    started = time.monotonic()
    panel._produce_offer()
    assert time.monotonic() - started < 1.0 and host.entered.wait(3.0)
    assert panel._offer_view.toPlainText() == ""
    host.release.set()
    assert _pump(qapp, lambda: panel._offer_view.toPlainText() == "v=0 offer")
    assert panel._manual_session_id == "session-1" and host.on_gui == [False]

    # Stopped while the offer was being made: the session is ended, nothing is shown or reported.
    for failure in (None, RuntimeError("the host is shutting down")):
        late = _SlowSdp()
        late.fail = failure
        panel._multi_host = late
        panel._offer_view.setPlainText("")
        panel._produce_offer()
        assert late.entered.wait(3.0)
        panel._multi_host = None
        late.release.set()
        assert _pump(qapp, lambda: not task_controller().active_count())
        assert panel._offer_view.toPlainText() == "" and webrtc_panel.warnings == []
        assert late.stopped == ([] if failure else ["session-1"])
    panel._annotation_overlay = None


def test_the_webrtc_viewer_answers_off_the_gui_thread(qapp, webrtc_panel):
    panel = webrtc_panel._WebRTCViewerPanel()
    viewer = _SlowSdp()
    panel._viewer = viewer
    started = time.monotonic()
    panel._produce_answer("v=0 offer")
    assert time.monotonic() - started < 1.0 and viewer.entered.wait(3.0)
    viewer.release.set()
    assert _pump(qapp, lambda: panel._answer_view.toPlainText() == "answer to v=0 offer")
    assert viewer.on_gui == [False]

    replaced = _SlowSdp()
    panel._viewer = replaced
    panel._answer_view.setPlainText("")
    panel._produce_answer("stale offer")
    assert replaced.entered.wait(3.0)
    panel._viewer = None                         # Stop, while the answer is being made
    replaced.release.set()
    assert _pump(qapp, lambda: not task_controller().active_count())
    assert panel._answer_view.toPlainText() == "" and webrtc_panel.warnings == []

    failing = _SlowSdp()
    failing.fail = ValueError("fingerprint mismatch")
    failing.release.set()
    panel._viewer = failing
    panel._produce_answer("bad offer")
    assert _pump(qapp, lambda: webrtc_panel.warnings == ["fingerprint mismatch"])
    panel._viewer = None


def test_the_ocr_tab_reads_off_the_gui_thread(qapp, monkeypatch):
    from PySide6.QtWidgets import QMessageBox
    from je_auto_control.gui import ocr_tab
    from je_auto_control.utils.ocr.ocr_engine import TextMatch
    warnings = []
    monkeypatch.setattr(QMessageBox, "warning", lambda *args: warnings.append(args[-1]))
    release, calls = threading.Event(), []

    def slow_read(**options):
        calls.append((options, QThread.currentThread() is qapp.thread()))
        release.wait(5.0)
        return [TextMatch("Order#7", 1, 2, 3, 4, 91.0)]

    def failing_find(**options):
        raise RuntimeError("tesseract is not installed")

    monkeypatch.setattr(ocr_tab, "read_text_in_region", slow_read)
    monkeypatch.setattr(ocr_tab, "find_text_regex", failing_find)
    tab = ocr_tab.OCRReaderTab()
    tab._region.setText("1, 2, 30, 40")
    started = time.monotonic()
    tab._on_dump()
    assert time.monotonic() - started < 1.0 and tab._task is not None
    tab._on_dump()                                         # one read at a time
    assert _pump(qapp, lambda: bool(calls)) and tab._result.toPlainText() == ""
    release.set()
    assert _pump(qapp, lambda: tab._task is None)
    assert calls == [({"region": [1, 2, 30, 40], "min_confidence": 60.0, "lang": "eng"}, False)]
    assert "Order#7" in tab._result.toPlainText()
    tab._regex.setText(r"Order#\d+")
    tab._on_find_regex()
    assert _pump(qapp, lambda: tab._task is None)
    assert warnings == ["tesseract is not installed"]
    tab._min_conf.setText("high")
    tab._on_dump()                                         # bad input never leaves the GUI thread
    assert tab._task is None and len(calls) == 1


def test_the_device_matrix_run_leaves_the_gui_thread(qapp, monkeypatch):
    from je_auto_control.gui import device_matrix_tab
    release, threads = threading.Event(), []

    class _Report:
        def to_dict(self):
            return {"results": [{"device_id": "a", "platform": "android", "success": True,
                                 "duration_s": 0.5, "error": None}],
                    "passed": 1, "failed": 0, "total": 1}

    def slow_run(actions, devices, max_parallel=4):
        threads.append(QThread.currentThread() is qapp.thread())
        release.wait(5.0)
        if not devices:
            raise ValueError("devices must be a non-empty list of device specs")
        return _Report()

    monkeypatch.setattr(device_matrix_tab.ac, "run_on_devices", slow_run)
    tab = device_matrix_tab.DeviceMatrixTab()
    tab._devices.setPlainText('[{"platform": "android", "serial": "a"}]')
    tab._actions.setPlainText("[]")
    started = time.monotonic()
    tab._on_run()
    assert time.monotonic() - started < 1.0 and tab._table.rowCount() == 0
    release.set()
    assert _pump(qapp, lambda: tab._task is None)
    assert threads == [False] and tab._table.rowCount() == 1
    tab._devices.setPlainText("[]")
    tab._on_run()
    assert _pump(qapp, lambda: tab._task is None)
    assert "non-empty" in tab._summary.text()
    tab._devices.setPlainText("{not json")
    tab._on_run()
    assert tab._task is None and len(threads) == 2
