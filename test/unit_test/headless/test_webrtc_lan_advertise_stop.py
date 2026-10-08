"""WebRTC host panel: the LAN advertiser is registered and unregistered off the GUI thread.

``HostAdvertiser.stop()`` sends zeroconf's goodbye packets and joins its
thread, and building one probes the name first; both ran in the Publish / Stop
slots. Offscreen Qt with a fake advertiser whose calls wait until the test lets
them go -- nothing here opens a socket. The stats pollers' ``stop()`` stays on
the GUI thread, and the last test pins why that is safe: it only schedules a
cancel on the asyncio bridge.
"""
import os
import threading
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)
pytest.importorskip("av")
pytest.importorskip("aiortc")

from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox  # noqa: E402

from je_auto_control.gui.remote_desktop import webrtc_panel  # noqa: E402
from je_auto_control.utils.remote_desktop import lan_discovery, webrtc_stats, webrtc_transport  # noqa: E402
from headless._qt_settle import deleting, pump_until, settle_op  # noqa: E402

_PROMPT_S = 5.0


@pytest.fixture(autouse=True)
def qapp(monkeypatch):
    app = QApplication.instance() or QApplication([])
    for box in ("warning", "information", "question", "critical"):
        monkeypatch.setattr(QMessageBox, box, lambda *args: None)
    yield app


@pytest.fixture(autouse=True)
def _panels_deleted():
    with deleting(webrtc_panel._WebRTCHostPanel):
        yield


class _Advertisers:
    """Stands in for ``lan_discovery``: records every build and stop, each of which can be held."""

    def __init__(self):
        self.log, self.lock = [], threading.Lock()
        self.hold_stop, self.hold_build = threading.Event(), threading.Event()
        self.hold_stop.set()
        self.hold_build.set()
        self.stop_entered = threading.Event()

    def build(self, *, host_id, signaling_url=None):
        self.hold_build.wait(30.0)
        advertiser = _Advertiser(self, host_id)
        with self.lock:
            self.log.append(("build", host_id, threading.current_thread() is threading.main_thread()))
        return advertiser


class _Advertiser:
    def __init__(self, owner, host_id):
        self._owner, self.host_id = owner, host_id

    def stop(self):
        self._owner.stop_entered.set()
        self._owner.hold_stop.wait(30.0)
        with self._owner.lock:
            self._owner.log.append(("stop", self.host_id, threading.current_thread() is threading.main_thread()))


@pytest.fixture()
def advertisers(monkeypatch):
    fake = _Advertisers()
    monkeypatch.setattr(lan_discovery, "HostAdvertiser", fake.build)
    monkeypatch.setattr(lan_discovery, "is_discovery_available", lambda: True)
    yield fake
    fake.hold_stop.set()
    fake.hold_build.set()


def _panel(host_id="host-1"):
    panel = webrtc_panel._WebRTCHostPanel()
    panel._host_id_edit.setText(host_id)
    return panel


def _timed(call):
    started = time.monotonic()
    call()
    return time.monotonic() - started


def test_the_advertiser_is_built_off_the_gui_thread_and_kept(advertisers):
    panel = _panel()
    advertisers.hold_build.clear()
    assert _timed(panel._start_lan_advertise) < _PROMPT_S
    assert panel._lan_advertiser is None            # still probing the name
    advertisers.hold_build.set()
    assert pump_until(lambda: panel._lan_advertiser is not None)
    assert advertisers.log == [("build", "host-1", False)]


def test_stop_lets_go_of_the_advertiser_at_once_and_closes_it_in_the_background(advertisers):
    panel = _panel()
    panel._start_lan_advertise()
    assert pump_until(lambda: panel._lan_advertiser is not None)
    advertisers.hold_stop.clear()
    assert _timed(panel._stop_lan_advertise) < _PROMPT_S
    assert panel._lan_advertiser is None and panel._stops.pending == 1
    assert advertisers.stop_entered.wait(10.0)
    panel._stop_lan_advertise()                     # nothing left to stop
    assert panel._stops.pending == 1
    advertisers.hold_stop.set()
    assert settle_op(panel._stops)
    assert advertisers.log == [("build", "host-1", False), ("stop", "host-1", False)]


def test_a_new_advertiser_registers_only_after_the_old_one_has_unregistered(advertisers):
    """The same host id is published again: registering it while the old one still holds the name fails."""
    panel = _panel()
    panel._start_lan_advertise()
    assert pump_until(lambda: panel._lan_advertiser is not None)
    first = panel._lan_advertiser
    advertisers.hold_stop.clear()
    panel._start_lan_advertise()                    # what Publish does: stop the old one, start the new
    assert advertisers.stop_entered.wait(10.0)
    assert not pump_until(lambda: len(advertisers.log) > 1, timeout=0.3)
    advertisers.hold_stop.set()
    assert pump_until(lambda: panel._lan_advertiser not in (None, first))
    assert [entry[0] for entry in advertisers.log] == ["build", "stop", "build"]


def test_an_advertiser_that_comes_up_after_stop_is_closed(advertisers):
    panel = _panel()
    advertisers.hold_build.clear()
    panel._start_lan_advertise()
    panel._stop_lan_advertise()                     # Stop while the name is still being probed
    advertisers.hold_build.set()
    assert pump_until(lambda: [entry[0] for entry in advertisers.log] == ["build", "stop"])
    assert panel._lan_advertiser is None and settle_op(panel._stops)


def test_an_advertiser_that_comes_up_for_a_panel_that_is_gone_is_closed(advertisers, qapp):
    panel = _panel()
    advertisers.hold_build.clear()
    panel._start_lan_advertise()
    panel.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    advertisers.hold_build.set()
    assert pump_until(lambda: [entry[0] for entry in advertisers.log] == ["build", "stop"])


def test_a_stats_poller_stop_only_schedules_a_cancel(monkeypatch):
    """Why the pollers' ``stop()`` may stay on the GUI thread: no join, no future to wait for."""
    scheduled = []

    class _Bridge:
        def call_soon(self, callback, *args):
            scheduled.append(callback)

        def submit(self, _coroutine):
            raise AssertionError("stop() must not wait for the loop")

    class _Task:
        def cancel(self):
            raise AssertionError("cancelled on the calling thread instead of the loop's")

    monkeypatch.setattr(webrtc_transport, "get_bridge", _Bridge)
    poller = webrtc_stats.StatsPoller(None, lambda _snapshot: None)
    poller.stop()                                   # never started: nothing to schedule
    assert scheduled == []
    task = _Task()
    poller._task = task
    poller.stop()
    assert scheduled == [task.cancel] and poller._task is None
