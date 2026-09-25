"""GUI workers that never ran, widgets touched off the GUI thread, dropped QThreads.

Found by the 2026-09-24 GUI audit (offscreen, fakes only; no network):

* Admin Console refresh / thumbnails and the USB browser / passthrough
  fetches kept their worker in a local variable. It was collected before
  ``run()``, the ``QThread`` stayed up and the one-at-a-time guard meant the
  feature never worked again.
* Results were delivered to lambdas, which run on the emitting worker thread.
* Quick Connect handed its widget methods to the viewer's receiver thread.
* The WebRTC panel dropped signaling QThreads mid-long-poll, which aborts the
  process.
"""
import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QObject, QThread, Signal  # noqa: E402
from PySide6.QtWidgets import QApplication, QWidget  # noqa: E402


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _pump(app, predicate, timeout=5.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.01)
    return predicate()


class _Worker(QObject):
    finished = Signal(object)
    failed = Signal(str)

    def __init__(self, value, fail=False):
        super().__init__()
        self._value, self._fail = value, fail

    def run(self):
        if self._fail:
            self.failed.emit("boom")
        else:
            self.finished.emit(self._value)


def test_an_inline_worker_runs_and_reports_on_the_gui_thread(qapp):
    from je_auto_control.gui._worker_thread import start_worker
    owner = QWidget()
    seen = {}
    thread = start_worker(
        owner, _Worker(42),
        on_done=lambda value: seen.update(value=value,
                                          gui=QThread.currentThread() is qapp.thread()),
        on_thread_done=lambda: seen.update(done=True))
    assert _pump(qapp, lambda: seen.get("done")), "the worker never ran"
    assert seen["value"] == 42 and seen["gui"] is True
    assert thread is not None
    failures = []
    start_worker(owner, _Worker(0, fail=True), on_done=lambda _v: None,
                 on_fail=failures.append, on_thread_done=lambda: failures.append("end"))
    assert _pump(qapp, lambda: "end" in failures)
    assert failures[0] == "boom"
    owner.deleteLater()


def test_admin_console_refresh_actually_polls(qapp, tmp_path, monkeypatch):
    from je_auto_control.gui import admin_console_tab as tab_mod
    from je_auto_control.utils.admin.admin_client import AdminConsoleClient
    client = AdminConsoleClient(persist_path=tmp_path / "hosts.json")
    polled = []
    monkeypatch.setattr(client, "poll_all", lambda *_a, **_k: polled.append(1) or [])
    monkeypatch.setattr(client, "fetch_thumbnails", lambda *_a, **_k: polled.append(2) or {})
    monkeypatch.setattr(tab_mod, "default_admin_console", lambda: client)
    tab = tab_mod.AdminConsoleTab()
    tab._thumb_timer.stop()  # noqa: SLF001
    tab._on_refresh()  # noqa: SLF001
    tab._refresh_thumbnails()  # noqa: SLF001
    assert _pump(qapp, lambda: tab._poll_thread is None and tab._thumb_thread is None)  # noqa: SLF001
    assert sorted(polled) == [1, 2], "the workers were collected before run()"
    tab._on_refresh()  # noqa: SLF001  # and the guard lets a second refresh run
    assert _pump(qapp, lambda: tab._poll_thread is None)  # noqa: SLF001
    assert polled.count(1) == 2
    tab.deleteLater()


def test_usb_open_result_is_applied_on_the_gui_thread(qapp, monkeypatch):
    from je_auto_control.gui import usb_browser_tab as tab_mod
    monkeypatch.setattr(tab_mod, "open_local_descriptor", lambda **_k: b"\x12\x01")
    where = {}
    monkeypatch.setattr(
        tab_mod.UsbBrowserTab, "_on_local_opened",
        lambda self, vid, pid, descriptor: where.update(
            args=(vid, pid, descriptor), gui=QThread.currentThread() is qapp.thread()))
    tab = tab_mod.UsbBrowserTab()
    tab._start_local_open("1234", "5678", None)  # noqa: SLF001
    assert _pump(qapp, lambda: "args" in where), "the open worker never ran"
    assert where == {"args": ("1234", "5678", b"\x12\x01"), "gui": True}
    tab.deleteLater()


def test_quick_connect_viewer_callbacks_reach_the_gui_thread(qapp, monkeypatch):
    from je_auto_control.gui.remote_desktop import connection_screen as screen_mod
    seen = []
    for name in ("_on_frame", "_on_error", "_on_remote_cursor"):
        monkeypatch.setattr(
            screen_mod.QuickConnectScreen, name,
            lambda self, *args, _n=name: seen.append(
                (_n, QThread.currentThread() is qapp.thread())))
    screen = screen_mod.QuickConnectScreen()
    receiver = threading.Thread(target=lambda: (
        screen._frame_arrived.emit(b"jpeg"),  # noqa: SLF001
        screen._error_arrived.emit("dropped"),  # noqa: SLF001
        screen._cursor_moved.emit(3, 4)))  # noqa: SLF001
    receiver.start()
    receiver.join()
    assert _pump(qapp, lambda: len(seen) == 3)
    assert seen == [("_on_frame", True), ("_on_error", True), ("_on_remote_cursor", True)]
    screen.deleteLater()


class _Blocking(QThread):
    failed = Signal(str)

    def __init__(self, gate):
        super().__init__()
        self._gate = gate

    def run(self):
        self._gate.wait(5)
        self.failed.emit("late answer")


def test_a_retired_worker_outlives_its_owner_reference_and_stays_quiet(qapp):
    from je_auto_control.gui.remote_desktop import webrtc_workers
    gate = threading.Event()
    late = []
    worker = _Blocking(gate)
    worker.failed.connect(late.append)
    worker.start()
    webrtc_workers.retire_worker(worker)
    del worker          # the panel's reference is gone while run() blocks
    assert len(webrtc_workers._RETIRED) == 1  # noqa: SLF001
    gate.set()
    assert _pump(qapp, lambda: not webrtc_workers._RETIRED)  # noqa: SLF001
    assert late == [], "a retired worker delivered its result"
    webrtc_workers.retire_worker(None)
