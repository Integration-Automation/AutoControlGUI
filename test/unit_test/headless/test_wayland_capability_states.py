"""Wayland capability and authorisation states, against fakes.

Nothing under ``linux_wayland`` can run on the machine these tests were
written on, so every one drives the real code against a fake libei, a fake
liboeffis and a described environment. What they pin is behaviour that is
independent of the host:

* a consent the portal *denied* is never worked around through ydotool;
* a session the compositor ended is never written to again;
* the X11 backend serving a Wayland session says how little it reaches;
* probing asks nobody for anything.

Whether real ``liboeffis`` words a refusal the way the fake does is the one
thing only Linux can settle; ``docker/portal_verify.py`` measures it.
"""
from unittest.mock import patch

import pytest

from je_auto_control.linux_wayland import _select_input as select_mod
from je_auto_control.linux_wayland import authorisation as auth
from je_auto_control.linux_wayland import keyboard as wl_keyboard
from je_auto_control.linux_wayland import libei as libei_mod
from je_auto_control.linux_wayland import oeffis as oeffis_mod
from je_auto_control.linux_wayland import portal as portal_mod
from je_auto_control.utils.exception.exceptions import (
    AutoControlException, AutoControlScreenException,
)
from je_auto_control.wrapper.capabilities import (
    BackendContext, CapabilityStatus, probe_capabilities,
)

SEAT = 0x5EA7
KEYBOARD = 0xD0001
POINTER = 0xD0002
KEY_A = 30


class FakeLibei:
    """A libei that plays back scripted events and counts what it is sent."""

    def __init__(self):
        self.pending = []
        self._queue = []
        self.writes = []
        self.rearm()
        self._caps = {
            KEYBOARD: {libei_mod.EI_DEVICE_CAP_KEYBOARD},
            POINTER: {libei_mod.EI_DEVICE_CAP_POINTER_ABSOLUTE,
                      libei_mod.EI_DEVICE_CAP_BUTTON,
                      libei_mod.EI_DEVICE_CAP_SCROLL},
        }

    def rearm(self):
        """Queue the event stream a cooperating compositor produces."""
        self._queue = []
        self.pending = [
            (libei_mod.EI_EVENT_CONNECT, None),
            (libei_mod.EI_EVENT_SEAT_ADDED, SEAT),
            (libei_mod.EI_EVENT_DEVICE_ADDED, KEYBOARD),
            (libei_mod.EI_EVENT_DEVICE_ADDED, POINTER),
            (libei_mod.EI_EVENT_DEVICE_RESUMED, KEYBOARD),
            (libei_mod.EI_EVENT_DEVICE_RESUMED, POINTER),
        ]

    def __getattr__(self, name):
        # Everything not spelled out below is a call this test does not
        # care about: accept it and return nothing.
        if name.startswith("ei_"):
            return lambda *_args: None
        raise AttributeError(name)

    def ei_new_sender(self, _user_data):
        return 0xEEEE

    def ei_setup_backend_fd(self, _ei, _fd):
        return 0

    def ei_get_fd(self, _ei):
        return 0

    def ei_dispatch(self, _ei):
        self._queue.extend(self.pending)
        self.pending = []

    def ei_get_event(self, _ei):
        return self._queue.pop(0) if self._queue else None

    def ei_event_get_type(self, event):
        return event[0]

    def ei_event_get_seat(self, event):
        return event[1]

    def ei_event_get_device(self, event):
        return event[1]

    def ei_device_has_capability(self, device, cap):
        return cap in self._caps.get(device, set())

    def ei_device_get_region(self, _device, _index):
        return None

    def ei_device_keyboard_key(self, device, keycode, is_press):
        self.writes.append(("key", device, keycode, is_press))

    def ei_device_frame(self, device, _when):
        self.writes.append(("frame", device))


class FakeOeffis:
    """A liboeffis whose portal answers the way ``outcome`` says."""

    def __init__(self, event, message=b""):
        self._event = event
        self._message = message
        self.sessions = 0

    def oeffis_new(self, _user_data):
        return 0x0EFF

    def oeffis_unref(self, _handle):
        return None

    def oeffis_create_session(self, _handle, _devices):
        self.sessions += 1

    def oeffis_get_fd(self, _handle):
        return 0

    def oeffis_dispatch(self, _handle):
        return None

    def oeffis_get_event(self, _handle):
        return self._event

    def oeffis_get_eis_fd(self, _handle):
        return 7

    def oeffis_get_error_message(self, _handle):
        return self._message


def _ready(readers, _writers, _errors, _timeout):
    """A ``select`` that reports every descriptor readable at once."""
    return list(readers), [], []


def _quiet(_readers, _writers, _errors, _timeout):
    """A ``select`` on which nothing ever arrives."""
    return [], [], []


@pytest.fixture(autouse=True)
def _clean_state(monkeypatch):
    """Every test starts unasked and leaves nothing behind for the next."""
    monkeypatch.delenv("JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND", raising=False)
    monkeypatch.delenv("JE_AUTOCONTROL_WAYLAND_EI_WORKER", raising=False)
    auth.ledger.reset()
    libei_mod.reset_default_backend()
    with patch.object(libei_mod.select, "select", side_effect=_ready), \
            patch.object(oeffis_mod.select, "select", side_effect=_ready):
        yield
    libei_mod.reset_default_backend()
    auth.ledger.reset()


def _wayland(**overrides):
    """A GNOME-shaped Wayland session with libei and ydotool installed."""
    settings = {
        "platform": "linux",
        "environ": {"XDG_SESSION_TYPE": "wayland",
                    "WAYLAND_DISPLAY": "wayland-0",
                    "XDG_RUNTIME_DIR": "/run/user/1000"},
        "which": lambda name: "/usr/bin/" + name,
        "library_present": lambda _name: True,
        "session_bus_present": lambda: True,
        "readable": lambda _path: True,
        "compositor": lambda _env: "8:1:100",
        "authorisations": auth.ledger,
    }
    settings.update(overrides)
    return BackendContext(**settings)


def _portal_session(monkeypatch, fake_oeffis, fake_libei=None):
    """Route the one libei probe through a fake portal and a fake libei."""
    fake_libei = fake_libei or FakeLibei()
    real_backend = libei_mod.LibeiBackend

    def build():
        fake_libei.rearm()
        return real_backend(
            symbols=fake_libei,
            portal_connect=lambda: oeffis_mod.connect_eis_fd(
                symbols=fake_oeffis, timeout=0.5))

    monkeypatch.setattr(libei_mod, "LibeiBackend", build)
    monkeypatch.setattr(libei_mod.oeffis, "is_available", lambda: True)
    monkeypatch.setattr(select_mod, "_libei_loadable", lambda: True)
    return fake_libei


def _cli_calls(monkeypatch):
    """Capture what would have been handed to ydotool."""
    calls = []
    monkeypatch.setattr(wl_keyboard, "_require_ydotool",
                        lambda: "/usr/bin/ydotool")
    monkeypatch.setattr(wl_keyboard, "_run",
                        lambda argv, **_kw: calls.append(argv))
    return calls


# === the three behaviours the plan names ====================================

def test_cancel_does_not_fallback_silently(monkeypatch):
    """A denied consent stops the action; ydotool is not used behind it."""
    portal = FakeOeffis(oeffis_mod.OEFFIS_EVENT_DISCONNECTED,
                        b"Portal denied Start")
    _portal_session(monkeypatch, portal)
    cli = _cli_calls(monkeypatch)

    with pytest.raises(auth.WaylandAuthorisationError) as refused:
        wl_keyboard.press_key(KEY_A)

    canceled = probe_capabilities(_wayland()).input
    assert canceled.state == 'needs_permission'
    assert canceled.backend == "libei"
    assert canceled.recovery
    assert cli == []
    assert refused.value.has_recovery_instruction
    assert refused.value.capability == "input"
    assert isinstance(refused.value, AutoControlException)
    # The fallback the keyboard module's own probe would take is a
    # RuntimeError; this must not be one, or it would be swallowed there.
    assert not isinstance(refused.value, RuntimeError)

    # It stays refused, and the portal is not asked again behind the user.
    with pytest.raises(auth.WaylandAuthorisationError):
        wl_keyboard.press_key(KEY_A)
    assert portal.sessions == 1
    assert cli == []


def test_revoked_session_cannot_send(monkeypatch):
    """After the compositor disconnects, nothing more is written anywhere."""
    granted = FakeOeffis(oeffis_mod.OEFFIS_EVENT_CONNECTED_TO_EIS)
    fake = _portal_session(monkeypatch, granted)
    cli = _cli_calls(monkeypatch)

    wl_keyboard.press_key(KEY_A)
    assert ("key", KEYBOARD, KEY_A, True) in fake.writes
    assert probe_capabilities(_wayland()).input.state == "available"

    fake.writes.clear()
    fake.pending = [(libei_mod.EI_EVENT_DISCONNECT, None)]
    with pytest.raises(auth.WaylandAuthorisationError):
        wl_keyboard.release_key(KEY_A)
    with pytest.raises(auth.WaylandAuthorisationError):
        wl_keyboard.press_key(KEY_A)
    # And the backend itself refuses, whoever holds a reference to it.
    backend = libei_mod.connected_backend()
    with pytest.raises(libei_mod.LibeiSessionRevoked):
        backend.press_key(KEY_A)

    writes_after_revoke = len(fake.writes)
    assert writes_after_revoke == 0
    assert cli == []
    assert probe_capabilities(_wayland()).input.state == "revoked"


def test_xwayland_scope_is_explicit():
    """X11 serving a Wayland session reaches X11 clients only, and says so."""
    context = _wayland(
        environ={"XDG_SESSION_TYPE": "wayland", "WAYLAND_DISPLAY": "wayland-0",
                 "DISPLAY": ":0",
                 "JE_AUTOCONTROL_LINUX_DISPLAY_SERVER": "x11"})
    snapshot = probe_capabilities(context)
    xwayland = snapshot.input

    assert snapshot.xwayland is True
    assert xwayland.desktop_wide is False
    assert snapshot.capture.desktop_wide is False
    assert xwayland.backend == "xwayland"
    assert "native Wayland windows" in xwayland.detail
    assert xwayland.recovery_key == "cap_fix_xwayland"


# === the rest of the state machine ==========================================

def test_wrapper_fallback_to_x11_is_reported_as_xwayland():
    """The wrapper can fall back without the override; the probe follows it."""
    snapshot = probe_capabilities(_wayland(loaded_backend="x11"))
    assert snapshot.xwayland is True
    assert snapshot.display_server == "x11"
    assert snapshot.input.desktop_wide is False


def test_a_real_x11_session_is_desktop_wide():
    context = _wayland(environ={"XDG_SESSION_TYPE": "x11", "DISPLAY": ":0"})
    snapshot = probe_capabilities(context)
    assert snapshot.xwayland is False
    assert snapshot.input.desktop_wide is True
    assert snapshot.input.state == "available"


def test_no_portal_still_falls_back_to_the_cli(monkeypatch):
    """Not a refusal: a host with no RemoteDesktop portal keeps working."""
    portal = FakeOeffis(oeffis_mod.OEFFIS_EVENT_DISCONNECTED,
                        b"The name org.freedesktop.portal.Desktop was not "
                        b"provided by any .service files")
    _portal_session(monkeypatch, portal)
    cli = _cli_calls(monkeypatch)

    wl_keyboard.press_key(KEY_A)

    assert cli == [["/usr/bin/ydotool", "key", "30:1"]]
    assert auth.ledger.get(auth.INPUT).state is auth.AuthorisationState.FAILED
    serving = probe_capabilities(_wayland()).input
    assert serving.backend == "ydotool"
    assert serving.state == "available"
    assert "libei could not start" in serving.detail


def test_an_unanswered_dialog_is_needs_permission(monkeypatch):
    portal = FakeOeffis(oeffis_mod.OEFFIS_EVENT_NONE)
    _portal_session(monkeypatch, portal)
    _cli_calls(monkeypatch)
    with patch.object(oeffis_mod.select, "select", side_effect=_quiet):
        wl_keyboard.press_key(KEY_A)
    state = auth.ledger.get(auth.INPUT).state
    assert state is auth.AuthorisationState.TIMED_OUT
    assert probe_capabilities(_wayland()).input.state == "needs_permission"


def test_only_a_stated_denial_counts_as_declined():
    """``declined`` is recognised narrowly, from the library's own text."""
    denied = oeffis_mod.PortalConsentNotGranted(
        "x", "disconnected", "Portal denied CreateSession")
    absent = oeffis_mod.PortalConsentNotGranted(
        "x", "disconnected", "no such interface")
    silent = oeffis_mod.PortalConsentNotGranted("x", "timeout")
    # What a real liboeffis said when the portal withheld the EIS descriptor
    # (portal-verification, 2026-10-09): a failed route, not the user's "no".
    withheld = oeffis_mod.PortalConsentNotGranted(
        "x", "disconnected", "Error calling ConnectToEIS: Permission denied")
    assert denied.declined is True
    assert absent.declined is False
    assert silent.declined is False
    assert withheld.declined is False
    assert isinstance(denied, oeffis_mod.OeffisUnavailable)


def test_reset_lets_the_desktop_be_asked_again(monkeypatch):
    portal = FakeOeffis(oeffis_mod.OEFFIS_EVENT_DISCONNECTED,
                        b"Portal denied Start")
    _portal_session(monkeypatch, portal)
    _cli_calls(monkeypatch)
    with pytest.raises(auth.WaylandAuthorisationError):
        wl_keyboard.press_key(KEY_A)

    select_mod.reset_input_authorisation()

    assert probe_capabilities(_wayland()).input.state == "not_requested"
    with pytest.raises(auth.WaylandAuthorisationError):
        wl_keyboard.press_key(KEY_A)
    assert portal.sessions == 2


def test_closing_the_session_is_its_own_state(monkeypatch):
    granted = FakeOeffis(oeffis_mod.OEFFIS_EVENT_CONNECTED_TO_EIS)
    _portal_session(monkeypatch, granted)
    _cli_calls(monkeypatch)
    wl_keyboard.press_key(KEY_A)

    select_mod.close_input_session()

    closed = probe_capabilities(_wayland()).input
    assert closed.state == "session_closed"
    assert closed.usable is True
    wl_keyboard.press_key(KEY_A)          # asks again, and is granted again
    assert granted.sessions == 2
    assert probe_capabilities(_wayland()).input.state == "available"


def test_forcing_the_cli_never_asks_the_portal(monkeypatch):
    """``cli`` is the explicit choice of ydotool; a past refusal is moot."""
    portal = FakeOeffis(oeffis_mod.OEFFIS_EVENT_DISCONNECTED,
                        b"Portal denied Start")
    _portal_session(monkeypatch, portal)
    cli = _cli_calls(monkeypatch)
    auth.ledger.transition(auth.INPUT, auth.AuthorisationState.DECLINED, "no")
    monkeypatch.setenv("JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND", "cli")

    wl_keyboard.press_key(KEY_A)

    assert cli == [["/usr/bin/ydotool", "key", "30:1"]]
    assert portal.sessions == 0


def test_a_compositor_restart_is_its_own_state():
    with patch.object(auth, "compositor_identity", return_value="8:1:100"):
        auth.ledger.transition(auth.INPUT, auth.AuthorisationState.GRANTED)
    same = probe_capabilities(_wayland(compositor=lambda _env: "8:1:100"))
    restarted = probe_capabilities(_wayland(compositor=lambda _env: "8:9:999"))
    assert same.input.state == "available"
    assert restarted.input.state == "compositor_restarted"
    assert restarted.input.recovery


def test_the_restore_token_is_stated_rather_than_implied():
    libei_input = probe_capabilities(_wayland()).input
    assert libei_input.restore_token == "unsupported"
    cli = probe_capabilities(_wayland(library_present=lambda _n: False)).input
    assert cli.restore_token == "not_applicable"


def test_input_and_capture_are_diagnosed_independently():
    """Capture working says nothing about input, and the reverse."""
    only_grim = _wayland(which=lambda name: "/usr/bin/grim"
                         if name == "grim" else None,
                         library_present=lambda _name: False)
    snapshot = probe_capabilities(only_grim)
    assert snapshot.capture.state == "available"
    assert snapshot.capture.backend == "grim"
    assert snapshot.input.state == "needs_setup"
    assert snapshot.input.recovery_key == "cap_fix_ydotool"

    only_input = _wayland(which=lambda name: "/usr/bin/ydotool"
                          if name == "ydotool" else None,
                          library_present=lambda _name: False,
                          session_bus_present=lambda: False)
    snapshot = probe_capabilities(only_input)
    assert snapshot.input.state == "available"
    assert snapshot.capture.state == "needs_setup"


def test_a_dismissed_screenshot_dialog_is_needs_permission():
    with pytest.raises(AutoControlScreenException):
        portal_mod._uri_from_response([1, {}])
    portal_only = _wayland(which=lambda _name: None)
    capture = probe_capabilities(portal_only).capture
    assert capture.backend == "xdg-desktop-portal"
    assert capture.state == "needs_permission"
    assert capture.recovery

    assert portal_mod._uri_from_response([0, {"uri": "file:///tmp/a.png"}])
    assert probe_capabilities(portal_only).capture.state == "available"


def test_recording_is_opt_in_and_names_what_is_missing():
    unset = probe_capabilities(_wayland()).get("recording")
    assert unset.state == "needs_setup"
    assert "opt-in" in unset.detail

    env = {"XDG_SESSION_TYPE": "wayland",
           "JE_AUTOCONTROL_WAYLAND_RECORD_DEVICES": "/dev/input/event3"}
    denied = probe_capabilities(
        _wayland(environ=env, readable=lambda _p: False)).get("recording")
    assert denied.state == "needs_permission"
    assert "root" in denied.recovery
    allowed = probe_capabilities(_wayland(environ=env)).get("recording")
    assert allowed.state == "available"


def test_probing_has_no_side_effect(monkeypatch):
    """A probe asks nobody for anything and changes nothing."""
    def forbidden(*_args, **_kwargs):
        raise AssertionError("a probe must not do this")

    monkeypatch.setattr(libei_mod, "connected_backend", forbidden)
    monkeypatch.setattr(libei_mod, "LibeiBackend", forbidden)
    monkeypatch.setattr(oeffis_mod, "connect_eis_fd", forbidden)
    monkeypatch.setattr(portal_mod, "capture_png", forbidden)
    monkeypatch.setattr(portal_mod._dbus_client, "SessionBus", forbidden)
    before = {name: auth.ledger.get(name) for name in (auth.INPUT, auth.CAPTURE)}

    for context in (_wayland(), _wayland(which=lambda _n: None),
                    _wayland(loaded_backend="x11"), BackendContext.current()):
        probe_capabilities(context)

    after = {name: auth.ledger.get(name) for name in (auth.INPUT, auth.CAPTURE)}
    assert after == before


def test_other_platforms_are_described_without_guessing():
    from je_auto_control.wrapper.capability_probes import MacFacts, WindowsFacts
    # Facts are supplied: the defaults query the machine the test runs on.
    windows = probe_capabilities(BackendContext(
        platform="win32", windows_facts=lambda: WindowsFacts(
            integrity="high", session_id=1, input_desktop="Default",
            hook_access=True, capture_ok=True)))
    assert windows.input.state is CapabilityStatus.AVAILABLE
    assert windows.input.backend == "win32"
    unread = probe_capabilities(BackendContext(
        platform="win32", windows_facts=WindowsFacts))
    assert unread.input.state is CapabilityStatus.UNKNOWN
    mac = probe_capabilities(BackendContext(platform="darwin", mac_facts=MacFacts))
    assert mac.input.state is CapabilityStatus.UNKNOWN
    assert mac.xwayland is False


def test_every_surface_reads_the_same_data():
    """Headless, the executor and the snapshot's dict are one description."""
    import je_auto_control as ac
    from je_auto_control.utils.executor.action_executor import executor

    expected = probe_capabilities().to_dict()
    assert ac.probe_capabilities().to_dict() == expected
    assert executor.event_dict["AC_probe_capabilities"]() == expected
    names = [item["name"] for item in expected["capabilities"]]
    assert names == ["input", "capture", "recording", "stop_shortcut"]
    for item in expected["capabilities"]:
        assert isinstance(item["state"], str)


def test_the_mcp_tool_reads_the_same_data():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    tools = {tool.name: tool for tool in build_default_tool_registry()}
    tool = tools["ac_probe_capabilities"]
    assert tool.handler() == probe_capabilities().to_dict()
    assert tool.annotations.read_only is True
