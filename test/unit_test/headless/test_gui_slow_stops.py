"""Stops that join a thread no longer hold the GUI thread (offscreen Qt, fakes only).

Every Stop here used to call a backend ``stop()`` that joins a thread for 2-6 s
from the slot itself. Each fake ``stop`` below waits until the test lets it go,
so a handler that still blocks fails by never returning in time. No test opens
a socket, a device or a window.
"""
import gc
import os
import threading
import time
import types

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
pytest.importorskip("PySide6.QtWidgets", exc_type=ImportError)

from PySide6.QtCore import QEvent  # noqa: E402
from PySide6.QtWidgets import QApplication, QMessageBox, QWidget  # noqa: E402

from je_auto_control.gui import (  # noqa: E402
    email_triggers_tab, hotkeys_tab, rest_api_tab, scheduler_tab, triggers_tab,
    usb_passthrough_panel, webhooks_tab,
)
from je_auto_control.gui._slow_op import SlowOp, StopQueue, stop_each  # noqa: E402
from je_auto_control.gui.language_wrapper.multi_language_wrapper import language_wrapper  # noqa: E402
from je_auto_control.gui.remote_desktop import host_panel  # noqa: E402
from je_auto_control.gui.task_controller import TaskUsageError  # noqa: E402
from je_auto_control.utils.remote_desktop.registry import SLOT_HOST, registry  # noqa: E402
from headless._qt_settle import deleting, pump_until, settle_op  # noqa: E402

#: A handler that returns within this is not waiting for the 30 s fake join.
_PROMPT_S = 5.0
_JOIN_S = 30.0


def _t(key):
    return language_wrapper.translate(key, key)


@pytest.fixture(autouse=True)
def qapp(monkeypatch):
    app = QApplication.instance() or QApplication([])
    messages = []
    for box in ("warning", "information", "question", "critical"):
        monkeypatch.setattr(QMessageBox, box, lambda *args: messages.append(args[-1]))
    app.messages = messages
    return app


@pytest.fixture(autouse=True)
def _panels_deleted():
    """Each test deletes the parentless panels it built (see ``_qt_settle.deleting``)."""
    with deleting(scheduler_tab.SchedulerTab, triggers_tab.TriggersTab, hotkeys_tab.HotkeysTab,
                  email_triggers_tab.EmailTriggersTab, webhooks_tab.WebhooksTab, rest_api_tab.RestApiTab,
                  usb_passthrough_panel.UsbPassthroughPanel, host_panel._HostPanel):
        yield


class _Owner(QWidget):
    def __init__(self):
        super().__init__()
        self.op, self.stops, self.seen = SlowOp(self), StopQueue(self), []

    def done(self, *values):
        self.seen.append(("done", self.op.busy, *values))

    def failed(self, *values):
        self.seen.append(("failed", self.op.busy, *values))


@pytest.fixture
def owner():
    widget = _Owner()
    yield widget
    widget.deleteLater()


class _Gate:
    """A blocking backend call: records who ran it and waits to be let go."""

    def __init__(self):
        self.entered, self.release = threading.Event(), threading.Event()
        self.calls, self.threads = 0, []

    def __call__(self, *_args, **_kwargs):
        self.calls += 1
        self.threads.append(threading.current_thread())
        self.entered.set()
        self.release.wait(_JOIN_S)


class _Engine:
    """Stands in for a scheduler / trigger engine / hotkey daemon / watcher / webhook server."""

    bound_address = ("127.0.0.1", 1)

    def __init__(self):
        self.is_running, self.starts, self.gate = True, 0, _Gate()

    def start(self, *_args, **_kwargs):
        self.starts += 1
        self.is_running = True
        return self.bound_address

    def stop(self, timeout=2.0):
        self.gate()
        self.is_running = False

    def _rows(self):
        return []

    list_jobs = list_triggers = list_bindings = list_webhooks = _rows


def _timed(call):
    started = time.monotonic()
    call()
    return time.monotonic() - started


_ENGINE_TABS = [
    (scheduler_tab, "SchedulerTab", "default_scheduler", "_engine_op", "_status", "sch_status_stopped"),
    (triggers_tab, "TriggersTab", "default_trigger_engine", "_engine_op", "_status", "tr_engine_stopped"),
    (hotkeys_tab, "HotkeysTab", "default_hotkey_daemon", "_engine_op", "_status", "hk_daemon_stopped"),
    (email_triggers_tab, "EmailTriggersTab", "default_email_trigger_watcher", "_watcher_op",
     "_status_label", "eml_stopped"),
    (webhooks_tab, "WebhooksTab", "default_webhook_server", "_server_op", "_status_label", "wh_stopped"),
]


@pytest.mark.parametrize("module, cls, backend, op_name, label, stopped_key", _ENGINE_TABS,
                         ids=[case[1] for case in _ENGINE_TABS])
def test_stop_returns_at_once_shows_stopping_and_ignores_a_second_click(  # noqa: PLR0913
        monkeypatch, module, cls, backend, op_name, label, stopped_key):
    engine = _Engine()
    monkeypatch.setattr(module, backend, engine)
    tab = getattr(module, cls)()
    op, status = getattr(tab, op_name), getattr(tab, label)
    try:
        assert _timed(tab._on_stop) < _PROMPT_S, "Stop waited for the join on the GUI thread"
        assert engine.gate.entered.wait(10.0)
        assert engine.gate.threads[0] is not threading.main_thread()
        assert op.busy
        assert status.text() == _t("gui_op_stopping")
        tab._on_stop()                      # a second click
        tab._on_start()                     # and a Start while the join is still out
        assert engine.gate.calls == 1
        assert engine.starts == 0
        assert status.text() == _t("gui_op_stopping")
    finally:
        engine.gate.release.set()
    assert settle_op(op)
    assert status.text() == _t(stopped_key).replace("{host}", "127.0.0.1").replace("{port}", "1")
    timer = getattr(tab, "_timer", None)
    if cls in ("SchedulerTab", "TriggersTab", "HotkeysTab"):
        assert not timer.isActive()         # nothing left to poll
    tab._on_start()                         # usable again once the stop reported
    assert engine.starts == 1
    if timer is not None:
        timer.stop()


# --- REST API --------------------------------------------------------------------------------------------------

class _RestRegistry:
    """The REST registry: ``status()`` waits for the lock ``start()`` holds, as the real one does."""

    def __init__(self):
        self.lock, self.gate, self.running, self.status_calls = threading.Lock(), _Gate(), True, 0
        self.starts = []

    def start(self, **kwargs):
        with self.lock:
            self.gate()
            self.starts.append(kwargs)
            self.running = True
        return self.status()

    def stop(self, timeout=2.0):
        with self.lock:
            self.gate()
            self.running = False

    def status(self):
        self.status_calls += 1
        with self.lock:
            return {"running": self.running, "url": "http://127.0.0.1:1", "token": "tok", "rbac": False}


@pytest.fixture
def rest(monkeypatch):
    fake = _RestRegistry()
    monkeypatch.setattr(rest_api_tab, "rest_api_registry", fake)
    tab = rest_api_tab.RestApiTab()
    yield tab, fake
    fake.gate.release.set()
    settle_op(tab._server_op)
    tab._timer.stop()


def test_rest_stop_is_off_the_gui_thread_and_the_refresh_timer_does_not_wait_for_the_lock(rest):
    tab, fake = rest
    assert _timed(tab._on_stop) < _PROMPT_S
    assert fake.gate.entered.wait(10.0)
    assert fake.gate.threads[0] is not threading.main_thread()
    assert tab._status_label.text() == _t("gui_op_stopping")
    assert tab._url_value.text() == "-"
    asked = fake.status_calls
    assert _timed(tab._refresh_status) < _PROMPT_S      # what the 2 s timer calls
    assert fake.status_calls == asked, "status() would have waited for the registry's lock"
    tab._on_stop()
    tab._on_start()
    assert fake.gate.calls == 1
    fake.gate.release.set()
    assert settle_op(tab._server_op)
    assert tab._status_label.text() == _t("rest_stopped")


def test_rest_start_replaces_the_server_off_the_gui_thread(rest):
    tab, fake = rest
    tab._port_input.setValue(4321)
    tab._token_input.setText("tok")
    assert _timed(tab._on_start) < _PROMPT_S
    assert fake.gate.entered.wait(10.0)
    assert tab._status_label.text() == _t("gui_op_starting")
    fake.gate.release.set()
    assert settle_op(tab._server_op)
    assert fake.starts[0]["port"] == 4321
    assert fake.starts[0]["token"] == "tok"
    assert tab._status_label.text() == _t("rest_running")
    assert tab._shared_token == "tok"


def test_a_rest_start_that_fails_is_reported_once_it_fails(rest, qapp):
    tab, fake = rest

    def refuse(**_kwargs):
        raise OSError("address already in use")

    fake.start = refuse
    tab._on_start()
    assert settle_op(tab._server_op)
    assert qapp.messages == ["address already in use"]
    assert not tab._server_op.busy


# --- USB sharing -----------------------------------------------------------------------------------------------

def test_usb_sharing_closes_its_loopback_off_the_gui_thread(monkeypatch, tmp_path):
    from je_auto_control.utils.usb.passthrough import UsbAcl
    gate, switched = _Gate(), []
    monkeypatch.setattr(usb_passthrough_panel, "enable_usb_passthrough", switched.append)
    opened = []

    def factory():
        opened.append(types.SimpleNamespace(close=gate))
        return opened[-1]

    panel = usb_passthrough_panel.UsbPassthroughPanel(acl=UsbAcl(path=tmp_path / "acl.json"),
                                                      loopback_factory=factory)
    panel._enable_sharing()
    try:
        assert _timed(panel._disable_sharing) < _PROMPT_S
        assert gate.entered.wait(10.0)
        assert gate.threads[0] is not threading.main_thread()
        assert panel._loopback is None, "the panel lets go at once: nothing opens a device through it"
        assert panel._host_badge.text() == _t("gui_op_stopping")
        panel._disable_sharing()
        panel._enable_sharing()             # ignored until the close reported
        assert gate.calls == 1
        assert len(opened) == 1
        assert switched == [True]
    finally:
        gate.release.set()
    assert settle_op(panel._share_op)
    assert switched == [True, False]
    assert panel._host_badge.text() == _t("usb_share_sharing_off")
    panel._enable_sharing()
    assert len(opened) == 2
    opened[-1].close = lambda: None
    panel._disable_sharing()
    assert settle_op(panel._share_op)


# --- remote desktop host panel ---------------------------------------------------------------------------------

class _Host:
    port, connected_clients, host_id = 4321, 0, "123456789"
    gate = None
    order = []

    def __init__(self, **kwargs):
        self.kwargs, self.is_running = kwargs, False

    def start(self):
        _Host.order.append(("start", self.kwargs["token"]))
        self.is_running = True

    def stop(self, timeout=2.0):
        _Host.order.append(("stop", self.kwargs["token"]))
        if _Host.gate is not None:
            _Host.gate()
        self.is_running = False

    def latest_frame(self):
        return None


@pytest.fixture
def host(monkeypatch):
    for attr in ("_host", "_viewer", "_ws_host", "_ws_viewer"):
        monkeypatch.setattr(registry, attr, None)
    monkeypatch.setattr(registry, "_claims", {})
    monkeypatch.setattr(host_panel, "RemoteDesktopHost", _Host)
    monkeypatch.setattr(host_panel, "WebSocketDesktopHost", _Host)
    monkeypatch.setattr(host_panel, "is_audio_backend_available", lambda: False)
    monkeypatch.setattr(_Host, "gate", None)
    monkeypatch.setattr(_Host, "order", [])
    panel = host_panel._HostPanel()
    yield panel
    if _Host.gate is not None:
        _Host.gate.release.set()
    settle_op(panel._host_op)
    panel._refresh_timer.stop()
    panel._preview_timer.stop()


def _start(panel, token):
    panel._token.setText(token)
    panel._start()
    assert settle_op(panel._host_op)


def test_host_stop_joins_off_the_gui_thread_and_clears_the_slot_when_it_reports(host, monkeypatch):
    _start(host, "one")
    running = registry.host
    monkeypatch.setattr(_Host, "gate", _Gate())
    assert _timed(host._stop) < _PROMPT_S
    assert _Host.gate.entered.wait(10.0)
    assert _Host.gate.threads[0] is not threading.main_thread()
    assert host._badge.text() == _t("gui_op_stopping")
    assert not host._start_btn.isEnabled()
    assert not host._stop_btn.isEnabled()
    host._stop()
    host._start()                           # ignored: the port is not free yet
    assert _Host.gate.calls == 1
    assert _Host.order == [("start", "one"), ("stop", "one")]
    _Host.gate.release.set()
    assert settle_op(host._host_op)
    assert not running.is_running
    assert registry.host is None
    assert host._shared is None
    assert host._badge.text() == _t("rd_badge_stopped")
    assert host._start_btn.isEnabled()
    assert host._stop_btn.isEnabled()


def test_host_start_stops_the_old_host_before_the_new_one_binds(host, monkeypatch):
    _start(host, "one")
    monkeypatch.setattr(_Host, "gate", _Gate())
    host._token.setText("two")
    assert _timed(host._start) < _PROMPT_S
    assert _Host.gate.entered.wait(10.0)
    assert host._badge.text() == _t("gui_op_starting")
    assert _Host.order == [("start", "one"), ("stop", "one")], "the new host waits for the old one's port"
    _Host.gate.release.set()
    assert settle_op(host._host_op)
    assert _Host.order == [("start", "one"), ("stop", "one"), ("start", "two")]
    assert registry.host.kwargs["token"] == "two"
    assert registry.owner_of(SLOT_HOST) == host._owner
    assert host._shared["host"] is registry.host
    assert host._shared["token"] == "two"


def test_a_host_that_comes_up_for_a_panel_that_is_gone_is_stopped(qapp, host, monkeypatch):
    _start(host, "one")
    monkeypatch.setattr(_Host, "gate", _Gate())
    panel = host_panel._HostPanel()
    panel._token.setText("two")
    panel._start()
    assert _Host.gate.entered.wait(10.0)
    panel._refresh_timer.stop()
    panel._preview_timer.stop()
    panel.deleteLater()
    qapp.sendPostedEvents(None, QEvent.Type.DeferredDelete.value)
    _Host.gate.release.set()
    assert pump_until(lambda: ("stop", "two") in _Host.order)
    assert registry.host is None


# --- the helpers themselves ------------------------------------------------------------------------------------

def test_slow_op_reports_once_idle_again_and_passes_leading_arguments(owner):
    changes = []
    owner.op.busy_changed.connect(changes.append)
    assert owner.op.run(lambda: 7, on_done=owner.done, on_error=owner.failed, args=("ctx",))
    assert owner.op.busy
    assert not owner.op.run(lambda: 8)
    assert settle_op(owner.op)
    assert owner.seen == [("done", False, "ctx", 7)]
    assert changes == [True, False]
    error = OSError("no")

    def fail():
        raise error

    assert owner.op.run(fail, on_done=owner.done, on_error=owner.failed)
    assert settle_op(owner.op)
    assert owner.seen[-1] == ("failed", False, error)


def test_work_that_holds_a_widget_is_refused(owner):
    with pytest.raises(TaskUsageError):
        owner.op.run(owner.close)
    with pytest.raises(TaskUsageError):
        owner.stops.retire(owner.close)
    assert not owner.op.busy
    assert owner.stops.pending == 0


def test_a_stop_queue_counts_what_is_out_and_says_when_it_drained(owner):
    first, second, drained = _Gate(), _Gate(), []
    owner.stops.drained.connect(lambda: drained.append(owner.stops.pending))
    owner.stops.retire(first, on_done=owner.done, args=("first",))
    owner.stops.retire(second)
    assert owner.stops.pending == 2
    first.release.set()
    assert pump_until(lambda: owner.stops.pending == 1)
    assert drained == []
    second.release.set()
    assert settle_op(owner.stops)
    assert drained == [0]
    assert owner.seen == [("done", False, "first", None)]


def test_stop_each_runs_every_stop_even_after_one_failed():
    ran = []

    def broken():
        raise RuntimeError("already closed")

    stop_each(lambda: ran.append(1), broken, lambda: ran.append(2))
    assert ran == [1, 2]


def test_a_dropped_owner_is_not_kept_alive_by_its_callbacks(qapp):
    """The callbacks are weak: a tab nobody holds is freed by its last reference, not by a child's destructor.

    Held strongly, a parentless panel was destroyed from inside the destructor of its own grandchild
    (the task handle, when Qt ran its deferred delete) and the process aborted.
    """
    import weakref
    owner = _Owner()
    gate = _Gate()
    owner.op.run(gate, on_done=owner.done, on_error=owner.failed)
    owner.stops.retire(gate, on_done=owner.done)
    seen = weakref.ref(owner)
    del owner
    gc.collect()
    gate.release.set()
    assert seen() is None
    assert gate.entered.wait(10.0)
    pump_until(lambda: False, timeout=0.2)      # the outcome has nobody to go to, and nothing crashes
