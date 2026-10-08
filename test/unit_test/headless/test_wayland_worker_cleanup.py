"""The libei helper process: its wire, its limits, and what it leaves behind.

The helper exists so that a libei session lives in a process nothing else
shares. These tests run the helper's real loop (``ei_worker.serve``) on a
thread, over real pipes, against a fake libei backend — so the framing, the
request ids, the cancellation path and the cleanup are the code that ships,
and only libei itself is pretend. One test starts a real child process.

What they cannot say is whether libei crashes on teardown, which is the
question the helper is for. ``docker/libei_verify.py`` and
``docker/eis_verify.py`` measure that on Linux.
"""
import io
import os
import subprocess  # nosec B404  # reason: starts this interpreter with a fixed argv
import sys
import threading
import time

import pytest

from je_auto_control.linux_wayland import _select_input as select_mod
from je_auto_control.linux_wayland import ei_transport as transport
from je_auto_control.linux_wayland import ei_client
from je_auto_control.linux_wayland import ei_worker
from je_auto_control.linux_wayland import libei as libei_mod
from je_auto_control.linux_wayland.input_events import (
    EV_ABS, EV_KEY, EV_REL, EV_SYN, InputEvent,
)
from je_auto_control.utils.exception.exceptions import AutoControlException

KEY_A = 30
KEY_B = 48
BTN_LEFT = 272


class FakeBackend:
    """Stands in for ``LibeiBackend`` inside the helper."""

    def __init__(self, available=True, connect_error=None):
        self.is_available = available
        self._connect_error = connect_error
        self.calls = []
        self.connected_with = None
        #: When set, the named call waits here — a stuck emission.
        self.gate = None
        self.fail = {}

    def connect(self, timeout, socket_path=None):
        self.connected_with = (timeout, socket_path)
        if self._connect_error is not None:
            raise self._connect_error

    def disconnect(self):
        self.calls.append(("disconnect",))

    def _call(self, name, *args):
        if self.gate is not None and self.gate[0] == (name,) + args:
            self.gate[1].wait(10)
        if name in self.fail:
            raise self.fail[name]
        self.calls.append((name,) + args)

    def press_key(self, code):
        self._call("press_key", code)

    def release_key(self, code):
        self._call("release_key", code)

    def press_button(self, code):
        self._call("press_button", code)

    def release_button(self, code):
        self._call("release_button", code)

    def set_position(self, x, y):
        self._call("set_position", x, y)

    def scroll(self, dx, dy):
        self._call("scroll", dx, dy)


class ThreadWorker:
    """A helper "process" that is really ``serve`` on a thread, over pipes."""

    def __init__(self, backend):
        to_child_r, to_child_w = os.pipe()
        from_child_r, from_child_w = os.pipe()
        self.stdin = os.fdopen(to_child_w, "wb", buffering=0)
        self.stdout = os.fdopen(from_child_r, "rb", buffering=0)
        self._child_in = os.fdopen(to_child_r, "rb", buffering=0)
        self._child_out = os.fdopen(from_child_w, "wb", buffering=0)
        self.returncode = None
        self._thread = threading.Thread(
            target=self._run, args=(backend,), daemon=True)
        self._thread.start()

    def _run(self, backend):
        try:
            code = ei_worker.serve(self._child_in, self._child_out,
                                   lambda: backend)
        finally:
            for stream in (self._child_out, self._child_in):
                try:
                    stream.close()
                except OSError:
                    pass
        self.returncode = code

    def crash(self):
        """Die the way a segfault does: the pipe just ends."""
        self._child_out.close()

    def streams(self):
        return (self.stdin, self.stdout, self._child_in, self._child_out)

    def poll(self):
        return self.returncode

    def wait(self, timeout=None):
        self._thread.join(timeout)
        if self._thread.is_alive():
            raise subprocess.TimeoutExpired("fake-worker", timeout)
        return self.returncode

    def terminate(self):
        """Nothing to signal; closing its stdin already ends the loop."""

    kill = terminate


def _client(backend, **options):
    workers = []

    def spawn():
        workers.append(ThreadWorker(backend))
        return workers[-1]

    client = ei_client.EiWorkerClient(spawn=spawn, start_timeout_s=5.0,
                                      **options)
    return client, workers


def _open_descriptors():
    """How many descriptors this process holds, where the OS will say."""
    try:
        return len(os.listdir("/proc/self/fd"))
    except OSError:
        return None


@pytest.fixture(autouse=True)
def _no_worker_left_behind():
    yield
    ei_client.reset_default_backend()
    assert ei_client.active_worker_count() == 0


# === the three behaviours the plan names ====================================

def test_half_open_worker_exit_reclaims_resources():
    """A handshake that never completes costs the parent nothing at all.

    In-process this state is the deliberate leak: one context and one
    descriptor that ``ei_unref`` cannot be trusted with. In a helper the
    child simply exits, and what the parent held was two pipes.
    """
    backend = FakeBackend(connect_error=libei_mod.LibeiUnavailable(
        "libei connected but no seat offered both a keyboard and an "
        "absolute pointer within the handshake timeout"))
    fd_count_before = _open_descriptors()
    streams = []

    for _attempt in range(5):
        client, workers = _client(backend)
        with pytest.raises(transport.EiWorkerError) as failed:
            client.start()
        assert "handshake timeout" in str(failed.value)
        assert client.is_alive is False
        streams.extend(workers[-1].streams())
        assert workers[-1].wait(5) == 1

    active_workers = ei_client.active_worker_count()
    fd_count_after = _open_descriptors()
    assert active_workers == 0
    assert fd_count_after == fd_count_before
    assert all(stream.closed for stream in streams)
    # The child never released a context it could not safely release: the
    # backend's own connect() failure path already dealt with it.
    assert ("disconnect",) not in backend.calls


def test_worker_death_releases_pressed_keys():
    """Whichever way the helper goes, a held key is accounted for."""
    # 1. A clean close: the helper lets go of everything on the way out.
    backend = FakeBackend()
    client, workers = _client(backend)
    client.start()
    client.send([InputEvent(EV_KEY, KEY_A, 1),
                 InputEvent(EV_KEY, BTN_LEFT, 1)], timeout_s=5.0)
    assert client.pressed == (KEY_A, BTN_LEFT)
    client.close()
    assert backend.calls[-3:] == [("release_button", BTN_LEFT),
                                  ("release_key", KEY_A), ("disconnect",)]
    assert workers[0].returncode == 0

    # 2. The parent vanishes without a word: the pipe ending is enough.
    backend = FakeBackend()
    client, workers = _client(backend)
    client.start()
    client.send([InputEvent(EV_KEY, KEY_A, 1)], timeout_s=5.0)
    workers[0].stdin.close()
    assert workers[0].wait(5) == 0
    assert ("release_key", KEY_A) in backend.calls
    client.close()

    # 3. The helper dies without warning: the parent says which keys were
    #    down, to whoever asked to be told, and in the error it raises.
    backend = FakeBackend()
    orphaned = []
    client, workers = _client(backend, on_orphaned_keys=orphaned.append)
    client.start()
    client.send([InputEvent(EV_KEY, KEY_A, 1)], timeout_s=5.0)
    workers[0].crash()
    with pytest.raises(transport.EiWorkerDied) as died:
        client.send([InputEvent(EV_KEY, KEY_B, 1)], timeout_s=5.0)
    assert died.value.pressed_keys == (KEY_A,)
    assert orphaned == [[KEY_A]]
    assert client.pressed == ()
    assert client.is_alive is False
    # Not a LibeiUnavailable: the request's fate is unknown, so no other
    # backend may quietly replay it.
    assert not isinstance(died.value, libei_mod.LibeiUnavailable)
    assert isinstance(died.value, AutoControlException)
    with pytest.raises(transport.EiWorkerDied):
        client.send([InputEvent(EV_KEY, KEY_B, 1)], timeout_s=5.0)


def test_missing_dependency_is_typed():
    """No libei where the helper runs is a named error, not a dead pipe."""
    client, _workers = _client(FakeBackend(available=False))
    with pytest.raises(transport.EiDependencyMissing) as missing:
        client.start()
    error = missing.value
    unavailable_capability = "input"
    assert error.capability == unavailable_capability
    assert error.dependency == "libei"
    assert isinstance(error, libei_mod.LibeiUnavailable)
    assert isinstance(error, AutoControlException)


# === limits, ids, deadlines =================================================

def test_a_batch_is_bounded_before_anything_is_written():
    backend = FakeBackend()
    client, _workers = _client(backend)
    client.start()
    too_many = [InputEvent(EV_KEY, KEY_A, 1)] * (transport.MAX_BATCH + 1)
    with pytest.raises(transport.EiProtocolError):
        client.send(too_many, timeout_s=1.0)
    with pytest.raises(transport.EiProtocolError):
        client.send([], timeout_s=1.0)
    with pytest.raises(transport.EiProtocolError):
        client.send([InputEvent(99, 1, 1)], timeout_s=1.0)
    assert backend.calls == []
    full = [InputEvent(EV_KEY, KEY_A, index % 2 ^ 1)
            for index in range(transport.MAX_BATCH)]
    assert client.send(full, timeout_s=5.0).applied == transport.MAX_BATCH
    client.close()


def test_a_frame_is_bounded_in_both_directions():
    oversized = transport._LENGTH.pack(transport.MAX_FRAME_BYTES + 1)
    with pytest.raises(transport.EiProtocolError):
        transport.read_frame(io.BytesIO(oversized + b"x"))
    with pytest.raises(transport.EiProtocolError):
        transport.write_frame(io.BytesIO(),
                              {"pad": "x" * transport.MAX_FRAME_BYTES})
    with pytest.raises(transport.EiProtocolError):
        transport.read_frame(io.BytesIO(transport._LENGTH.pack(10) + b"abc"))
    with pytest.raises(transport.EiProtocolError):
        transport.read_frame(io.BytesIO(transport._LENGTH.pack(2) + b"[]"))
    assert transport.read_frame(io.BytesIO(b"")) is None

    stream = io.BytesIO()
    transport.write_frame(stream, {"op": "ack", "id": 7})
    stream.seek(0)
    assert transport.read_frame(stream) == {"op": "ack", "id": 7}


def test_a_bad_batch_is_refused_whole_by_the_helper():
    with pytest.raises(transport.EiProtocolError):
        transport.decode_batch([[EV_KEY, KEY_A, 1], [EV_KEY, "x", 1]])
    with pytest.raises(transport.EiProtocolError):
        transport.decode_batch([[EV_KEY, KEY_A, True]])
    with pytest.raises(transport.EiProtocolError):
        transport.decode_batch([[EV_KEY, KEY_A]])
    with pytest.raises(transport.EiProtocolError):
        transport.decode_batch("not a list")


def test_a_deadline_stops_the_batch_and_a_late_answer_is_dropped():
    """The request that timed out must not be mistaken for the next one."""
    backend = FakeBackend()
    release_stuck = threading.Event()
    backend.gate = (("press_key", KEY_A), release_stuck)
    client, _workers = _client(backend)
    client.start()

    started = time.monotonic()
    with pytest.raises(transport.EiWorkerTimeout) as late:
        client.send([InputEvent(EV_KEY, KEY_A, 1),
                     InputEvent(EV_KEY, KEY_B, 1)], timeout_s=0.2)
    assert time.monotonic() - started < 5.0
    assert not isinstance(late.value, libei_mod.LibeiUnavailable)
    # Nothing came back, so the worst is assumed about what is down.
    assert client.pressed == (KEY_A, KEY_B)

    backend.gate = None
    release_stuck.set()
    ack = client.send([InputEvent(EV_KEY, BTN_LEFT, 1)], timeout_s=5.0)

    assert ack.request_id == 2
    assert ack.applied == 1
    # The helper stopped between events and let go of what that batch held;
    # the second key of the abandoned batch was never pressed.
    assert backend.calls == [("press_key", KEY_A), ("release_key", KEY_A),
                             ("press_button", BTN_LEFT)]
    assert client.pressed == (BTN_LEFT,)
    client.close()


def test_a_caller_can_cancel_a_request():
    backend = FakeBackend()
    release_stuck = threading.Event()
    backend.gate = (("press_key", KEY_A), release_stuck)
    client, _workers = _client(backend)
    client.start()
    cancel = threading.Event()
    threading.Timer(0.1, cancel.set).start()

    with pytest.raises(transport.EiWorkerCancelled):
        client.send([InputEvent(EV_KEY, KEY_A, 1),
                     InputEvent(EV_KEY, KEY_B, 1)], timeout_s=30.0,
                    cancel=cancel)

    release_stuck.set()
    client.close()
    assert ("press_key", KEY_B) not in backend.calls


# === what libei says, said again in the parent ==============================

def test_a_refusal_in_the_helper_is_a_refusal_in_the_parent():
    backend = FakeBackend()
    backend.fail["set_position"] = libei_mod.LibeiUnavailable(
        "(9000, 9000) lies outside every region this pointer accepts")
    client, _workers = _client(backend)
    client.start()
    served = ei_client.WorkerBackend(client, timeout_s=5.0)
    with pytest.raises(transport.EiEmitRefused) as refused:
        served.set_position(9000, 9000)
    assert "outside every region" in str(refused.value)
    # The same type the in-process backend raises, so `emitted` hands the
    # move to ydotool exactly as it does today.
    assert select_mod.emitted(served, lambda b: b.set_position(1, 1)) is False
    client.close()


def test_a_revoked_session_in_the_helper_is_revoked_in_the_parent():
    backend = FakeBackend()
    backend.fail["press_key"] = libei_mod.LibeiSessionRevoked(
        "the compositor disconnected the sender")
    client, _workers = _client(backend)
    client.start()
    with pytest.raises(libei_mod.LibeiSessionRevoked):
        ei_client.WorkerBackend(client, timeout_s=5.0).press_key(KEY_A)
    client.close()


def test_a_refused_consent_keeps_its_meaning_across_the_pipe():
    backend = FakeBackend(connect_error=libei_mod.LibeiConsentNotGranted(
        "the desktop portal disconnected the remote-desktop session: "
        "Portal denied Start", "disconnected", True))
    client, _workers = _client(backend)
    with pytest.raises(libei_mod.LibeiConsentNotGranted) as refused:
        client.start()
    assert refused.value.declined is True
    assert refused.value.outcome == "disconnected"


def test_the_backend_surface_matches_what_keyboard_and_mouse_call():
    backend = FakeBackend()
    client, _workers = _client(backend, socket_path="/run/user/1000/eis-0")
    client.start()
    assert backend.connected_with == (libei_mod.HANDSHAKE_TIMEOUT,
                                      b"/run/user/1000/eis-0")
    served = ei_client.WorkerBackend(client, timeout_s=5.0)
    served.press_key(KEY_A)
    served.release_key(KEY_A)
    served.click_button(BTN_LEFT)
    served.set_position(640, 400)
    served.scroll(0, 1)
    served.scroll(-2, 0)
    served.disconnect()
    assert backend.calls == [
        ("press_key", KEY_A), ("release_key", KEY_A),
        ("press_button", BTN_LEFT), ("release_button", BTN_LEFT),
        ("set_position", 640, 400), ("scroll", 0, 1), ("scroll", -2, 0),
        ("disconnect",),
    ]
    assert served.is_connected is False
    public = {name for name in dir(libei_mod.LibeiBackend)
              if not name.startswith("_") and name not in {"connect"}}
    assert public <= set(dir(served))


def test_evdev_events_map_onto_libei_calls():
    """Auto-repeat is ignored, and a move is one call once both axes are in."""
    backend = FakeBackend()
    client, _workers = _client(backend)
    client.start()
    client.send([
        InputEvent(EV_KEY, KEY_A, 1), InputEvent(EV_KEY, KEY_A, 2),
        InputEvent(EV_ABS, transport.ABS_X, 10),
        InputEvent(EV_ABS, transport.ABS_Y, 20), InputEvent(EV_SYN, 0, 0),
        InputEvent(EV_REL, transport.REL_WHEEL, 1), InputEvent(EV_SYN, 0, 0),
        InputEvent(EV_KEY, KEY_A, 0),
    ], timeout_s=5.0)
    client.close()
    assert backend.calls[:-1] == [
        ("press_key", KEY_A), ("set_position", 10, 20),
        # REL_WHEEL up is positive in the kernel's frame, negative in libei's.
        ("scroll", 0, -1), ("release_key", KEY_A),
    ]


# === the switch =============================================================

def test_the_helper_is_off_unless_asked_for(monkeypatch):
    monkeypatch.delenv(select_mod.WORKER_ENV, raising=False)
    assert select_mod.worker_enabled() is False
    assert select_mod._backend_source() is libei_mod
    for value in ("0", "", "no", "off"):
        assert select_mod.worker_enabled({select_mod.WORKER_ENV: value}) is False
    monkeypatch.setenv(select_mod.WORKER_ENV, "1")
    assert select_mod.worker_enabled() is True
    assert select_mod._backend_source() is ei_client


def test_the_selector_uses_the_helper_when_asked(monkeypatch):
    from je_auto_control.linux_wayland import authorisation as auth
    auth.ledger.reset()
    backend = FakeBackend()
    client, _workers = _client(backend)
    monkeypatch.setenv(select_mod.WORKER_ENV, "1")
    monkeypatch.setattr(select_mod, "_libei_loadable", lambda: True)
    monkeypatch.setattr(ei_client, "EiWorkerClient", lambda: client)
    try:
        served = select_mod.active_backend()
        assert isinstance(served, ei_client.WorkerBackend)
        assert select_mod.emitted(served, lambda b: b.press_key(KEY_A))
        assert backend.calls == [("press_key", KEY_A)]
        assert auth.ledger.get(auth.INPUT).state.value == "granted"
    finally:
        select_mod.reset_input_authorisation()
    assert backend.calls[-2:] == [("release_key", KEY_A), ("disconnect",)]
    assert auth.ledger.get(auth.INPUT).state.value == "not_requested"


def test_the_in_process_teardown_is_untouched():
    """The default path still abandons a half-open context — on purpose.

    The helper is an alternative behind a switch, not a replacement, so the
    measured workaround in ``LibeiBackend._teardown`` must read as it did.
    """
    backend = libei_mod.LibeiBackend(symbols=object())
    backend._ei = 0xEEEE
    backend._backend_open = True
    assert backend._safe_to_unref() is False
    backend._handshake_complete = True
    assert backend._safe_to_unref() is True
    backend._backend_open = False
    backend._handshake_complete = False
    assert backend._safe_to_unref() is True


# === one real process =======================================================

_CHILD = (
    "from je_auto_control.linux_wayland import ei_worker, libei\n"
    "libei._load_symbols = lambda: None\n"
    "ei_worker.run_as_helper()\n"
)


def test_a_real_helper_process_reports_a_missing_library():
    """The same conversation across a real pipe to a real child process.

    The child is told libei is not installed, so it never reaches for a
    display, a portal or a device on any host — it answers and exits.
    """
    children = []

    def spawn():
        argv = [sys.executable, "-c", _CHILD]
        children.append(subprocess.Popen(  # nosec B603  # nosemgrep  # reason: fixed argv
            argv, stdin=subprocess.PIPE, stdout=subprocess.PIPE))
        return children[-1]

    client = ei_client.EiWorkerClient(spawn=spawn, start_timeout_s=120.0)
    with pytest.raises(transport.EiDependencyMissing) as missing:
        client.start()
    assert missing.value.capability == "input"
    assert children[0].poll() == 1
    assert ei_client.active_worker_count() == 0
    assert children[0].stdin.closed and children[0].stdout.closed
