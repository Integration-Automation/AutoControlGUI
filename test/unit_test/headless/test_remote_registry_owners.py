"""Who owns the remote-desktop registry's host and viewer slots (fakes, no Qt).

Quick Connect, the viewer tab and ``AC_remote_connect`` wrote the same slot
and each cleared it first, so one side's connect cut the other's session
without telling it, and its Disconnect then cut a session it never opened.
"""
import importlib
import threading

import pytest

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.remote_desktop.registry import (
    SCRIPT_OWNER, SLOT_HOST, SLOT_VIEWER, SLOT_WS_HOST, SLOT_WS_VIEWER,
    _RemoteDesktopRegistry, new_owner,
)

# The package rebinds its ``registry`` attribute to the singleton, so the
# module itself has to be asked for by name.
registry_module = importlib.import_module("je_auto_control.utils.remote_desktop.registry")

VIEWER_SLOTS = (SLOT_VIEWER, SLOT_WS_VIEWER)
HOST_SLOTS = (SLOT_HOST, SLOT_WS_HOST)
ALL_SLOTS = VIEWER_SLOTS + HOST_SLOTS


class _Viewer:
    remote_host_id = "123456789"

    def __init__(self, **kwargs):
        self.kwargs, self.connected, self.sent = kwargs, False, []

    def connect(self, timeout=5.0):
        self.connected = True

    def disconnect(self, timeout=2.0):
        self.connected = False

    def send_input(self, action):
        self.sent.append(action)


class _Host:
    port, connected_clients, host_id = 4321, 0, "987654321"

    def __init__(self, **kwargs):
        self.kwargs, self.is_running = kwargs, False

    def start(self):
        self.is_running = True

    def stop(self, timeout=2.0):
        self.is_running = False


def _live(slot):
    """A started fake of the kind ``slot`` holds."""
    if slot in HOST_SLOTS:
        made = _Host()
        made.start()
    else:
        made = _Viewer()
        made.connect()
    return made


def _is_up(resource):
    return getattr(resource, "is_running", None) or getattr(resource, "connected", False)


@pytest.fixture
def reg(monkeypatch):
    monkeypatch.setattr(registry_module, "RemoteDesktopViewer", _Viewer)
    monkeypatch.setattr(registry_module, "WebSocketDesktopViewer", _Viewer)
    monkeypatch.setattr(registry_module, "RemoteDesktopHost", _Host)
    monkeypatch.setattr(registry_module, "WebSocketDesktopHost", _Host)
    return _RemoteDesktopRegistry()


class _Panel:
    """A GUI panel as the registry sees it: an owner token and a callback."""

    def __init__(self, label="panel"):
        self.owner = new_owner(label)
        self.displaced = []

    def on_displaced(self, slot, by):
        self.displaced.append((slot, by))


_SCRIPT_OPEN = {
    SLOT_VIEWER: lambda reg: reg.connect_viewer("h", 1, "t"),
    SLOT_WS_VIEWER: lambda reg: reg.connect_ws_viewer("h", 1, "t"),
    SLOT_HOST: lambda reg: reg.start_host("t"),
    SLOT_WS_HOST: lambda reg: reg.start_ws_host("t"),
}
_SCRIPT_CLOSE = {
    SLOT_VIEWER: "disconnect_viewer", SLOT_WS_VIEWER: "disconnect_ws_viewer",
    SLOT_HOST: "stop_host", SLOT_WS_HOST: "stop_ws_host",
}
_STATUS = {
    SLOT_VIEWER: "viewer_status", SLOT_WS_VIEWER: "ws_viewer_status",
    SLOT_HOST: "host_status", SLOT_WS_HOST: "ws_host_status",
}


def _occupant(reg, slot):
    return getattr(reg, "_" + slot)


# --- owner tokens ------------------------------------------------------------------------------------------

def test_owner_tokens_are_unique_and_never_the_script_owner():
    first, second = new_owner("viewer-tab"), new_owner("viewer-tab")
    assert first != second
    assert SCRIPT_OWNER not in (first, second)
    assert first.startswith("viewer-tab#")


@pytest.mark.parametrize("call", ["owner_of", "owned", "evict", "release", "adopt"])
def test_an_unknown_slot_is_refused(reg, call):
    args = {"owner_of": (), "owned": ("me",), "evict": ("me",), "release": ("me",),
            "adopt": (object(), "me")}[call]
    method = getattr(reg, call)
    with pytest.raises(AutoControlException):
        method("webrtc", *args)


# --- a panel's own session ---------------------------------------------------------------------------------

@pytest.mark.parametrize("slot", ALL_SLOTS)
def test_a_panel_reads_and_closes_what_it_adopted(reg, slot):
    panel, made = _Panel(), _live(slot)
    reg.adopt(slot, made, panel.owner, panel.on_displaced)
    assert reg.owner_of(slot) == panel.owner
    assert reg.owned(slot, panel.owner) is made
    assert getattr(reg, _STATUS[slot])()["owner"] == panel.owner
    assert reg.release(slot, panel.owner) is True
    assert not _is_up(made)
    assert reg.owner_of(slot) is None
    assert panel.displaced == []            # it asked for this itself


@pytest.mark.parametrize("slot", ALL_SLOTS)
def test_a_panel_reconnecting_is_not_told_it_was_displaced(reg, slot):
    panel, first, second = _Panel(), _live(slot), _live(slot)
    reg.adopt(slot, first, panel.owner, panel.on_displaced)
    assert reg.evict(slot, by=panel.owner) is True
    reg.adopt(slot, second, panel.owner, panel.on_displaced)
    reg.adopt(slot, _live(slot), panel.owner, panel.on_displaced)   # replaced without evicting first
    assert not _is_up(first)
    assert not _is_up(second)
    assert panel.displaced == []


def test_adopting_the_same_object_again_does_not_close_it(reg):
    panel, viewer = _Panel(), _live(SLOT_VIEWER)
    reg.adopt(SLOT_VIEWER, viewer, panel.owner, panel.on_displaced)
    reg.adopt(SLOT_VIEWER, viewer, panel.owner, panel.on_displaced)
    assert viewer.connected
    assert reg.owned(SLOT_VIEWER, panel.owner) is viewer


# --- panel against panel ------------------------------------------------------------------------------------

@pytest.mark.parametrize("slot", ALL_SLOTS)
def test_one_panel_cannot_see_or_close_another_panels_session(reg, slot):
    first, second, made = _Panel("quick-connect"), _Panel("viewer-tab"), _live(slot)
    reg.adopt(slot, made, first.owner, first.on_displaced)
    assert reg.owned(slot, second.owner) is None
    assert reg.release(slot, second.owner) is False
    getattr(reg, _SCRIPT_CLOSE[slot])(owner=second.owner)
    assert _is_up(made)
    assert reg.owned(slot, first.owner) is made
    assert first.displaced == []


@pytest.mark.parametrize("slot", ALL_SLOTS)
@pytest.mark.parametrize("evict_first", [True, False])
def test_a_panel_replaced_by_another_panel_is_told(reg, slot, evict_first):
    first, second, old, new = _Panel("quick-connect"), _Panel("viewer-tab"), _live(slot), _live(slot)
    reg.adopt(slot, old, first.owner, first.on_displaced)
    if evict_first:
        reg.evict(slot, by=second.owner)
    reg.adopt(slot, new, second.owner, second.on_displaced)
    assert not _is_up(old)
    assert _is_up(new)
    assert first.displaced == [(slot, second.owner)]
    assert second.displaced == []
    # The replaced panel's Disconnect no longer reaches the new session.
    assert reg.release(slot, first.owner) is False
    assert _is_up(new)
    assert reg.owned(slot, first.owner) is None


def test_the_two_viewer_transports_do_not_displace_each_other(reg):
    tcp, ws = _Panel(), _Panel()
    reg.adopt(SLOT_VIEWER, _live(SLOT_VIEWER), tcp.owner, tcp.on_displaced)
    reg.adopt(SLOT_WS_VIEWER, _live(SLOT_WS_VIEWER), ws.owner, ws.on_displaced)
    reg.evict(SLOT_WS_VIEWER, by=tcp.owner)
    assert tcp.displaced == []
    assert ws.displaced == [(SLOT_WS_VIEWER, tcp.owner)]
    assert reg.owned(SLOT_VIEWER, tcp.owner).connected


# --- script against panel -----------------------------------------------------------------------------------

@pytest.mark.parametrize("slot", ALL_SLOTS)
def test_a_script_connect_replaces_a_panels_session_and_tells_it(reg, slot):
    panel, old = _Panel(), _live(slot)
    reg.adopt(slot, old, panel.owner, panel.on_displaced)
    status = _SCRIPT_OPEN[slot](reg)
    assert status["owner"] == SCRIPT_OWNER
    assert not _is_up(old)
    assert panel.displaced == [(slot, SCRIPT_OWNER)]
    assert reg.release(slot, panel.owner) is False
    assert _is_up(_occupant(reg, slot))


@pytest.mark.parametrize("slot", ALL_SLOTS)
def test_a_script_close_ends_a_panels_session_and_tells_it(reg, slot):
    panel, made = _Panel(), _live(slot)
    reg.adopt(slot, made, panel.owner, panel.on_displaced)
    status = getattr(reg, _SCRIPT_CLOSE[slot])()
    assert status["owner"] is None
    assert not _is_up(made)
    assert panel.displaced == [(slot, SCRIPT_OWNER)]


@pytest.mark.parametrize("slot", ALL_SLOTS)
def test_a_panel_replaces_a_scripts_session(reg, slot):
    _SCRIPT_OPEN[slot](reg)
    scripted, panel = _occupant(reg, slot), _Panel()
    assert reg.owned(slot, panel.owner) is None
    assert reg.release(slot, panel.owner) is False
    assert _is_up(scripted)
    reg.evict(slot, by=panel.owner)
    reg.adopt(slot, _live(slot), panel.owner, panel.on_displaced)
    assert not _is_up(scripted)
    assert reg.owner_of(slot) == panel.owner


@pytest.mark.parametrize(("slot", "send"), [(SLOT_VIEWER, "send_input"), (SLOT_WS_VIEWER, "ws_send_input")])
def test_script_input_goes_to_the_active_viewer_whoever_opened_it(reg, slot, send):
    panel, viewer = _Panel(), _live(slot)
    reg.adopt(slot, viewer, panel.owner, panel.on_displaced)
    assert getattr(reg, send)({"action": "type", "text": "a"}) == {"sent": True}
    assert viewer.sent == [{"action": "type", "text": "a"}]
    reg.release(slot, panel.owner)
    send_input = getattr(reg, send)
    with pytest.raises(ConnectionError):
        send_input({"action": "type", "text": "b"})


# --- script alone: unchanged ---------------------------------------------------------------------------------

@pytest.mark.parametrize("slot", ALL_SLOTS)
def test_a_script_only_session_behaves_as_before(reg, slot):
    first_status = _SCRIPT_OPEN[slot](reg)
    first = _occupant(reg, slot)
    assert first_status["owner"] == SCRIPT_OWNER
    assert _is_up(first)
    _SCRIPT_OPEN[slot](reg)                               # a second connect replaces the first
    second = _occupant(reg, slot)
    assert second is not first
    assert not _is_up(first)
    assert _is_up(second)
    closed = getattr(reg, _SCRIPT_CLOSE[slot])()
    assert not _is_up(second)
    assert _occupant(reg, slot) is None
    assert closed["owner"] is None
    assert not closed.get("connected")
    assert not closed.get("running")
    getattr(reg, _SCRIPT_CLOSE[slot])()                   # closing nothing is still fine


def test_status_keeps_its_old_keys(reg):
    assert reg.viewer_status() == {"connected": False, "host_id": None, "owner": None}
    assert reg.host_status() == {"running": False, "port": 0, "connected_clients": 0,
                                 "host_id": None, "owner": None}
    reg.start_host("t")
    reg.connect_viewer("h", 1, "t")
    assert reg.host_status() == {"running": True, "port": 4321, "connected_clients": 0,
                                 "host_id": "987654321", "owner": SCRIPT_OWNER}
    assert reg.viewer_status() == {"connected": True, "host_id": "123456789", "owner": SCRIPT_OWNER}


def test_an_occupant_set_on_the_attribute_counts_as_the_scripts(reg):
    panel, stale, injected = _Panel(), _live(SLOT_VIEWER), _live(SLOT_VIEWER)
    reg.adopt(SLOT_VIEWER, stale, panel.owner, panel.on_displaced)
    reg._viewer = injected                                # what older tests and callers do
    assert reg.owner_of(SLOT_VIEWER) == SCRIPT_OWNER
    assert reg.owned(SLOT_VIEWER, panel.owner) is None
    reg.disconnect_viewer()
    assert not injected.connected
    assert panel.displaced == []


# --- notification delivery --------------------------------------------------------------------------------

def test_a_failing_displaced_callback_does_not_undo_the_new_connect(reg):
    def explode(slot, by):
        raise RuntimeError("the panel is gone")
    reg.adopt(SLOT_VIEWER, _live(SLOT_VIEWER), new_owner("panel"), explode)
    assert reg.connect_viewer("h", 1, "t")["connected"] is True


def test_the_owner_is_told_even_when_closing_its_session_raises(reg):
    class Stuck(_Viewer):
        def disconnect(self, timeout=2.0):
            raise OSError("socket already gone")
    panel = _Panel()
    reg.adopt(SLOT_VIEWER, Stuck(), panel.owner, panel.on_displaced)
    with pytest.raises(OSError):
        reg.disconnect_viewer()
    assert panel.displaced == [(SLOT_VIEWER, SCRIPT_OWNER)]
    assert reg.viewer is None


def test_a_callback_may_call_back_into_the_registry(reg):
    seen = []
    owner = new_owner("panel")
    reg.adopt(SLOT_VIEWER, _live(SLOT_VIEWER), owner,
              lambda slot, by: seen.append((reg.owner_of(slot), reg.owned(slot, owner))))
    done = threading.Thread(target=reg.connect_viewer, args=("h", 1, "t"), daemon=True)
    done.start()
    done.join(5.0)
    assert not done.is_alive(), "the callback ran under the registry lock"
    # Told while the slot is empty: the old viewer is closed before the new one dials.
    assert seen == [(None, None)]
    assert reg.owner_of(SLOT_VIEWER) == SCRIPT_OWNER


# --- through the executor and the MCP handlers ----------------------------------------------------------------

@pytest.fixture
def shared(monkeypatch):
    """The process-wide registry, emptied, building fakes."""
    shared_registry = registry_module.registry
    for name in ("RemoteDesktopViewer", "WebSocketDesktopViewer"):
        monkeypatch.setattr(registry_module, name, _Viewer)
    for name in ("RemoteDesktopHost", "WebSocketDesktopHost"):
        monkeypatch.setattr(registry_module, name, _Host)
    for attr in ("_host", "_viewer", "_ws_host", "_ws_viewer"):
        monkeypatch.setattr(shared_registry, attr, None)
    monkeypatch.setattr(shared_registry, "_claims", {})
    return shared_registry


def _run(command, params=None):
    action = [command] if params is None else [command, params]
    return next(iter(executor.execute_action([action]).values()))


def test_ac_remote_commands_alone_work_as_before(shared):
    connect = {"host": "h", "port": 1, "token": "t"}
    assert _run("AC_start_remote_host", {"token": "t"})["running"] is True
    assert _run("AC_remote_connect", connect)["connected"] is True
    first = shared.viewer
    assert _run("AC_remote_connect", connect)["connected"] is True
    assert shared.viewer is not first
    assert not first.connected
    assert _run("AC_remote_send_input", {"action": {"action": "type", "text": "x"}}) == {"sent": True}
    assert _run("AC_remote_viewer_status")["owner"] == SCRIPT_OWNER
    assert _run("AC_remote_disconnect")["connected"] is False
    assert _run("AC_stop_remote_host")["running"] is False
    assert shared.viewer is None
    assert shared.host is None


def test_ac_remote_commands_see_and_end_a_panels_session(shared):
    panel, viewer, host = _Panel(), _live(SLOT_VIEWER), _live(SLOT_HOST)
    shared.adopt(SLOT_VIEWER, viewer, panel.owner, panel.on_displaced)
    shared.adopt(SLOT_HOST, host, panel.owner, panel.on_displaced)
    assert _run("AC_remote_viewer_status") == {
        "connected": True, "host_id": "123456789", "owner": panel.owner}
    assert _run("AC_remote_host_status")["owner"] == panel.owner
    _run("AC_remote_send_input", {"action": {"action": "type", "text": "x"}})
    assert viewer.sent == [{"action": "type", "text": "x"}]
    _run("AC_remote_disconnect")
    _run("AC_stop_remote_host")
    assert not viewer.connected
    assert not host.is_running
    assert panel.displaced == [(SLOT_VIEWER, SCRIPT_OWNER), (SLOT_HOST, SCRIPT_OWNER)]


def test_ac_ws_commands_tell_a_replaced_panel(shared):
    panel, viewer = _Panel(), _live(SLOT_WS_VIEWER)
    shared.adopt(SLOT_WS_VIEWER, viewer, panel.owner, panel.on_displaced)
    assert _run("AC_ws_connect", {"host": "h", "port": 1, "token": "t"})["owner"] == SCRIPT_OWNER
    assert not viewer.connected
    assert panel.displaced == [(SLOT_WS_VIEWER, SCRIPT_OWNER)]
    assert _run("AC_ws_disconnect")["connected"] is False


def test_the_mcp_tools_share_the_script_owner(shared):
    from je_auto_control.utils.mcp_server.tools import _handlers_remote as handlers
    panel, viewer = _Panel(), _live(SLOT_VIEWER)
    shared.adopt(SLOT_VIEWER, viewer, panel.owner, panel.on_displaced)
    assert handlers.remote_viewer_status()["owner"] == panel.owner
    assert handlers.remote_viewer_connect("h", 1, "t")["owner"] == SCRIPT_OWNER
    assert panel.displaced == [(SLOT_VIEWER, SCRIPT_OWNER)]
    assert handlers.remote_viewer_disconnect()["connected"] is False
    assert handlers.remote_host_start("t")["owner"] == SCRIPT_OWNER
    assert handlers.remote_host_stop()["running"] is False
