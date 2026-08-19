"""Tests for the libei backend selector, the portal hop, and the handshake.

libei will not emit anything until a sender has bound a seat's capabilities,
taken a device *out of an event*, and started emulating on it — and every
emission has to be followed by a frame. These tests drive that state machine
against a fake libei whose entry points record what they were called with, so
the protocol order is pinned on any host.

The one thing they cannot check is the ABI: the enum values and function
signatures come from ``libei.h`` and only a real Wayland session can confirm
them. What the tests *can* guarantee is the fail-closed property — every path
that does not reach a live device raises ``LibeiUnavailable``, which the
keyboard and mouse modules turn into "use the ydotool CLI".
"""
from unittest.mock import MagicMock, patch

import pytest

from je_auto_control.linux_wayland import (
    LibeiBackend, LibeiUnavailable, select_input_backend,
)
from je_auto_control.linux_wayland import libei as libei_mod
from je_auto_control.linux_wayland import oeffis as oeffis_mod
from je_auto_control.linux_wayland import (
    _select_input as select_mod,
)
from je_auto_control.linux_wayland import _ydotool_cli


SEAT = 0x5EA7
KEYBOARD_DEVICE = 0xD0001
POINTER_DEVICE = 0xD0002
SENDER = 0xEEEE


@pytest.fixture(autouse=True)
def _select_always_ready():
    """Report libei's fd readable without touching the real ``select``.

    On Linux ``ei_get_fd`` hands back a genuine epoll descriptor; the fake
    returns a plain integer, and Windows' ``select`` accepts only sockets.
    Stubbing the readiness check keeps these tests about the handshake
    rather than about the host's poll implementation.
    """
    with patch.object(libei_mod.select, "select",
                      side_effect=lambda r, _w, _x, _t: (list(r), [], [])):
        yield


@pytest.fixture(autouse=True)
def _ydotool_generation_already_known():
    """Keep the ydotool 0.1.x probe out of the captured argv of these tests.

    The CLI fallback paths here assert on the exact argv the backend builds.
    Before building any, both backends probe the installed ydotool once —
    0.1.x answers this argv with exit code 0 and no events — and that probe is
    a ``subprocess.run`` call, so it would be captured alongside the argv
    under test. ``test_wayland_ydotool_cli.py`` covers the probe itself.
    """
    _ydotool_cli.reset_cache()
    _ydotool_cli._cache["/usr/bin/ydotool"] = _ydotool_cli.MODERN
    try:
        yield
    finally:
        _ydotool_cli.reset_cache()


class FakeLibei:
    """A libei that plays back a scripted event stream and records calls.

    Devices carry capabilities the way real ones do, so the backend has to
    ask ``ei_device_has_capability`` rather than assume.
    """

    def __init__(self, events=None, capabilities=None, regions=None):
        self.calls = []
        self.pending = list(events if events is not None else _full_handshake())
        self.capabilities = capabilities if capabilities is not None else {
            KEYBOARD_DEVICE: {libei_mod.EI_DEVICE_CAP_KEYBOARD},
            POINTER_DEVICE: {libei_mod.EI_DEVICE_CAP_POINTER_ABSOLUTE,
                             libei_mod.EI_DEVICE_CAP_BUTTON,
                             libei_mod.EI_DEVICE_CAP_SCROLL},
        }
        #: ``device -> [(x, y, width, height)]``. Empty by default, which is
        #: the real "device declared no region" case: it accepts anything.
        self.regions = dict(regions or {})
        self._queue = []
        self.lib = MagicMock()

    # -- context ---------------------------------------------------------
    def ei_new_sender(self, _user_data):
        self.calls.append(("new_sender",))
        return SENDER

    def ei_setup_backend_fd(self, _ei, fd):
        self.calls.append(("setup_backend_fd", fd))
        return 0

    def ei_setup_backend_socket(self, _ei, path):
        self.calls.append(("setup_backend_socket", path))
        return 0

    def ei_get_fd(self, _ei):
        return 0          # a real fd number is never polled: timeout is 0

    def ei_dispatch(self, _ei):
        # One dispatch moves the whole scripted batch into the event queue.
        self._queue.extend(self.pending)
        self.pending = []

    def ei_get_event(self, _ei):
        return self._queue.pop(0) if self._queue else None

    def ei_event_unref(self, _event):
        return None

    def ei_now(self, _ei):
        return 123456789

    def ei_unref(self, _ei):
        self.calls.append(("unref",))
        return None

    # -- events ----------------------------------------------------------
    def ei_event_get_type(self, event):
        return event[0]

    def ei_event_get_seat(self, event):
        return event[1]

    def ei_event_get_device(self, event):
        return event[1]

    # -- seat / device ---------------------------------------------------
    def ei_seat_bind_capabilities(self, *args):
        self.calls.append(("bind", tuple(
            getattr(a, "value", a) for a in args)))

    def ei_device_has_capability(self, device, cap):
        return cap in self.capabilities.get(device, set())

    def ei_device_ref(self, device):
        self.calls.append(("device_ref", device))
        return device

    def ei_device_unref(self, device):
        self.calls.append(("device_unref", device))
        return None

    def ei_device_start_emulating(self, device, sequence):
        self.calls.append(("start_emulating", device, sequence))

    def ei_device_stop_emulating(self, device):
        self.calls.append(("stop_emulating", device))

    def ei_device_frame(self, device, when):
        self.calls.append(("frame", device, when))

    def ei_device_keyboard_key(self, device, keycode, is_press):
        self.calls.append(("key", device, keycode, is_press))

    def ei_device_pointer_motion_absolute(self, device, x, y):
        self.calls.append(("motion", device, x, y))

    # -- regions ---------------------------------------------------------
    # A region handle is ``(device, index)``: truthy, and enough to answer
    # the four getters. libei ends the list by returning NULL.
    def ei_device_get_region(self, device, index):
        shapes = self.regions.get(device, ())
        return (device, index) if index < len(shapes) else None

    def _region(self, handle):
        device, index = handle
        return self.regions[device][index]

    def ei_region_get_x(self, handle):
        return self._region(handle)[0]

    def ei_region_get_y(self, handle):
        return self._region(handle)[1]

    def ei_region_get_width(self, handle):
        return self._region(handle)[2]

    def ei_region_get_height(self, handle):
        return self._region(handle)[3]

    def ei_device_button_button(self, device, button, is_press):
        self.calls.append(("button", device, button, is_press))

    def ei_device_scroll_discrete(self, device, x, y):
        self.calls.append(("scroll", device, x, y))


def _full_handshake():
    """The event stream a cooperating compositor produces."""
    return [
        (libei_mod.EI_EVENT_CONNECT, None),
        (libei_mod.EI_EVENT_SEAT_ADDED, SEAT),
        (libei_mod.EI_EVENT_DEVICE_ADDED, KEYBOARD_DEVICE),
        (libei_mod.EI_EVENT_DEVICE_ADDED, POINTER_DEVICE),
        (libei_mod.EI_EVENT_DEVICE_RESUMED, KEYBOARD_DEVICE),
        (libei_mod.EI_EVENT_DEVICE_RESUMED, POINTER_DEVICE),
    ]


def _portal_present():
    """Pretend liboeffis is installed, so the portal route is taken.

    Which route ``_open_backend`` picks is decided by that probe, not by the
    injected connector — a host without liboeffis would otherwise fall
    through to the well-known socket and these tests would silently stop
    exercising the portal.
    """
    return patch.object(libei_mod.oeffis, "is_available", return_value=True)


def _connected(fake=None, session=None):
    """Return a backend that has completed the handshake over a fake fd."""
    fake = fake or FakeLibei()
    backend = LibeiBackend(symbols=fake,
                           portal_connect=lambda: (7, session or MagicMock()))
    with _portal_present():
        backend.connect(timeout=1.0)
    return backend, fake


def _kinds(fake):
    return [call[0] for call in fake.calls]


# === Selector =============================================================

def test_select_input_backend_defaults_to_cli_when_libei_absent(monkeypatch):
    monkeypatch.setattr(select_mod, "_libei_loadable", lambda: False)
    assert select_input_backend({}) == "cli"


def test_select_input_backend_picks_libei_when_loadable(monkeypatch):
    monkeypatch.setattr(select_mod, "_libei_loadable", lambda: True)
    assert select_input_backend({}) == "libei"


def test_select_input_backend_honours_cli_override(monkeypatch):
    monkeypatch.setattr(select_mod, "_libei_loadable", lambda: True)
    assert select_input_backend({
        "JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND": "cli",
    }) == "cli"


def test_select_input_backend_force_libei_raises_without_libei(monkeypatch):
    monkeypatch.setattr(select_mod, "_libei_loadable", lambda: False)
    with pytest.raises(RuntimeError, match="libei"):
        select_input_backend({
            "JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND": "libei",
        })


def test_select_input_backend_invalid_override_treated_as_auto(monkeypatch):
    monkeypatch.setattr(select_mod, "_libei_loadable", lambda: False)
    assert select_input_backend({
        "JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND": "garbage",
    }) == "cli"


# === ABI constants ========================================================

def test_capability_constants_match_libei_h():
    """``enum ei_device_capability`` is a bitmask, not a sequence.

    Checked against libei.h (Debian 1.5.0-3 and upstream main, which agree on
    these six). This was wrong here — KEYBOARD had been guessed as 3 rather
    than ``1 << 2`` — and the consequence was invisible: no device would ever
    have reported the capability, so the handshake would have timed out and
    every session silently fallen back to the ydotool CLI.
    """
    assert libei_mod.EI_DEVICE_CAP_POINTER == 1
    assert libei_mod.EI_DEVICE_CAP_POINTER_ABSOLUTE == 2
    assert libei_mod.EI_DEVICE_CAP_KEYBOARD == 4
    assert libei_mod.EI_DEVICE_CAP_TOUCH == 8
    assert libei_mod.EI_DEVICE_CAP_SCROLL == 16
    assert libei_mod.EI_DEVICE_CAP_BUTTON == 32


def test_event_type_constants_match_libei_h():
    """``enum ei_event_type`` starts at 1 and increments implicitly through
    DEVICE_RESUMED before jumping to 90."""
    assert libei_mod.EI_EVENT_CONNECT == 1
    assert libei_mod.EI_EVENT_DISCONNECT == 2
    assert libei_mod.EI_EVENT_SEAT_ADDED == 3
    assert libei_mod.EI_EVENT_SEAT_REMOVED == 4
    assert libei_mod.EI_EVENT_DEVICE_ADDED == 5
    assert libei_mod.EI_EVENT_DEVICE_REMOVED == 6
    assert libei_mod.EI_EVENT_DEVICE_PAUSED == 7
    assert libei_mod.EI_EVENT_DEVICE_RESUMED == 8


# === Handshake ============================================================

def test_connect_attaches_the_portal_fd_not_a_socket_path():
    """GNOME / KDE hand the EIS socket over as a file descriptor; a path
    only exists on compositors that publish one."""
    _, fake = _connected()
    assert ("setup_backend_fd", 7) in fake.calls
    assert not any(call[0] == "setup_backend_socket" for call in fake.calls)


def test_connect_falls_back_to_the_well_known_socket_without_liboeffis():
    """Some compositors publish EIS at ``$XDG_RUNTIME_DIR/eis-0``; without
    liboeffis that is the only route left, and it beats giving up."""
    fake = FakeLibei()
    backend = LibeiBackend(symbols=fake)
    with patch.object(libei_mod.oeffis, "is_available", return_value=False):
        backend.connect(timeout=1.0)
    setup = next(c for c in fake.calls if c[0] == "setup_backend_socket")
    assert setup[1].endswith(b"eis-0")


def test_connect_binds_the_seat_capabilities_it_will_emit():
    _, fake = _connected()
    bind = next(call for call in fake.calls if call[0] == "bind")
    # seat first, then each capability, then the NULL terminator.
    assert bind[1][0] == SEAT
    assert set(bind[1][1:-1]) == set(libei_mod._WANTED_CAPS)
    assert bind[1][-1] is None


def test_connect_starts_emulating_on_every_resumed_device():
    _, fake = _connected()
    started = [call for call in fake.calls if call[0] == "start_emulating"]
    assert {call[1] for call in started} == {KEYBOARD_DEVICE, POINTER_DEVICE}
    # The sequence number increases per device, as libei requires.
    assert [call[2] for call in started] == [1, 2]


def test_devices_are_taken_from_events_never_from_the_context():
    """The defect this rewrite exists for: the old binding passed the ``ei``
    context to entry points that take an ``ei_device``."""
    backend, fake = _connected()
    backend.press_key(30)
    for call in fake.calls:
        if call[0] in ("key", "motion", "button", "scroll", "frame",
                       "start_emulating"):
            assert call[1] in (KEYBOARD_DEVICE, POINTER_DEVICE)
            assert call[1] != SENDER


def test_handshake_times_out_when_no_device_ever_resumes():
    """A seat that never resumes a device must not hang the caller."""
    fake = FakeLibei(events=[(libei_mod.EI_EVENT_SEAT_ADDED, SEAT)])
    backend = LibeiBackend(symbols=fake,
                           portal_connect=lambda: (7, MagicMock()))
    with _portal_present(), pytest.raises(LibeiUnavailable,
                                          match="handshake timeout"):
        backend.connect(timeout=0.05)


def test_handshake_rejects_a_partial_grant():
    """Only a pointer and no keyboard would leave every key press silently
    doing nothing, so a partial grant counts as no grant."""
    fake = FakeLibei(
        events=[(libei_mod.EI_EVENT_SEAT_ADDED, SEAT),
                (libei_mod.EI_EVENT_DEVICE_ADDED, POINTER_DEVICE),
                (libei_mod.EI_EVENT_DEVICE_RESUMED, POINTER_DEVICE)],
    )
    backend = LibeiBackend(symbols=fake,
                           portal_connect=lambda: (7, MagicMock()))
    with _portal_present(), pytest.raises(LibeiUnavailable):
        backend.connect(timeout=0.05)


def test_a_denied_portal_request_reads_as_libei_unavailable():
    """A dismissed consent dialog is an ordinary fall-back-to-CLI, not a
    crash and not a hang."""
    def refuse():
        raise oeffis_mod.OeffisUnavailable("the user dismissed the dialog")

    fake = FakeLibei()
    backend = LibeiBackend(symbols=fake, portal_connect=refuse)
    with _portal_present(), pytest.raises(LibeiUnavailable, match="dismissed"):
        backend.connect(timeout=1.0)
    # The sender is released rather than leaked on the way out.
    assert ("unref",) in fake.calls


def test_connect_abandons_an_opened_context_rather_than_unref_it():
    """``ei_unref`` segfaults on libei 1.3.901 once the backend is open.

    Measured against the real library in ``docker/libei_verify.py``: safe
    before setup and after a *failed* setup, SIGSEGV after a successful one.
    A crash in a library driving someone's desktop is worse than leaking one
    context per process, so an opened backend is dropped without unref.
    """
    fake = FakeLibei(events=[])
    session = MagicMock()
    backend = LibeiBackend(symbols=fake, portal_connect=lambda: (7, session))
    with _portal_present(), pytest.raises(LibeiUnavailable):
        backend.connect(timeout=0.05)
    assert ("unref",) not in fake.calls
    # The portal session is liboeffis, a different library, and closing it is
    # what actually revokes the grant — so that still has to happen.
    session.close.assert_called_once()


def test_a_context_that_never_opened_a_backend_is_unreffed():
    """The other half of the rule: before any backend is set up, ``unref`` is
    the documented release and is safe, so it must still run."""
    fake = FakeLibei()

    def refuse():
        raise oeffis_mod.OeffisUnavailable("no portal")

    backend = LibeiBackend(symbols=fake, portal_connect=refuse)
    with _portal_present(), pytest.raises(LibeiUnavailable):
        backend.connect(timeout=0.05)
    assert ("unref",) in fake.calls


def test_a_failed_backend_setup_is_unreffed():
    """``ei_setup_backend_socket`` returning non-zero leaves the context in
    the state the header documents as releasable, and the probe confirms is
    safe."""
    class _SetupFails(FakeLibei):
        def ei_setup_backend_socket(self, _ei, path):
            self.calls.append(("setup_backend_socket", path))
            return -2

    fake = _SetupFails()
    backend = LibeiBackend(symbols=fake)
    with pytest.raises(LibeiUnavailable, match="returned -2"):
        backend.connect(timeout=0.05, socket_path=b"/nope")
    assert ("unref",) in fake.calls


# === Emission =============================================================

def test_every_emission_is_followed_by_a_frame():
    """libei buffers until ``ei_device_frame``; without it the compositor
    sees nothing, which is how the old binding could look correct and emit
    nothing at all."""
    backend, fake = _connected()
    backend.press_key(30)
    backend.set_position(4, 9)
    backend.press_button(272)
    backend.scroll(0, 3)
    kinds = _kinds(fake)
    for emission in ("key", "motion", "button", "scroll"):
        index = kinds.index(emission)
        assert kinds[index + 1] == "frame", f"{emission} was not framed"


def test_scroll_sends_whole_wheel_clicks_not_raw_detents():
    """libei measures discrete scroll in 120ths of a click, like WHEEL_DELTA.

    Passing a raw detent count is a 120th of the scroll asked for, and libei
    says so at runtime — "suspicious discrete event value 1, did you mean
    120?" — which is how ``docker/eis_verify.py`` found it against a real EIS
    peer. It reads the value back off the wire there; this pins the unit
    without needing one."""
    backend, fake = _connected()

    def _last_scroll():
        return [call for call in fake.calls if call[0] == "scroll"][-1][2:]

    backend.scroll(0, 3)
    assert _last_scroll() == (0, 3 * libei_mod.SCROLL_UNIT)
    backend.scroll(-2, 0)
    assert _last_scroll() == (-2 * libei_mod.SCROLL_UNIT, 0), \
        "the sign has to survive the conversion too"


def test_key_press_and_release_use_the_keyboard_device():
    backend, fake = _connected()
    backend.press_key(30)
    backend.release_key(30)
    keys = [call for call in fake.calls if call[0] == "key"]
    assert keys == [("key", KEYBOARD_DEVICE, 30, True),
                    ("key", KEYBOARD_DEVICE, 30, False)]


def test_pointer_motion_uses_the_absolute_pointer_device():
    backend, fake = _connected()
    backend.set_position(120, 340)
    assert ("motion", POINTER_DEVICE, 120.0, 340.0) in fake.calls


# === Absolute pointer regions =============================================
#
# libei drops an absolute motion that lands in no region and reports nothing
# about it: no return code, no event, no error the caller can see. Measured
# against a real EIS peer, which is also where the rest of this section's
# expectations come from — see ``docker/eis_verify.py``.

def _with_regions(regions):
    """A connected backend whose absolute pointer advertises ``regions``."""
    return _connected(FakeLibei(regions={POINTER_DEVICE: regions}))


def test_a_device_with_no_region_takes_the_coordinate_unchanged():
    """The common case, and the one every other test here relies on: a
    device that declared no region accepts anything, so nothing is mapped."""
    backend, fake = _connected()
    backend.set_position(4000, 3000)
    assert ("motion", POINTER_DEVICE, 4000.0, 3000.0) in fake.calls


def test_a_point_inside_a_region_is_sent_as_it_stands():
    backend, fake = _with_regions([(0, 0, 1920, 1080)])
    backend.set_position(640, 400)
    assert ("motion", POINTER_DEVICE, 640.0, 400.0) in fake.calls


def test_region_offsets_are_part_of_the_coordinate_not_stripped():
    """A region at ``x=1280`` takes 1380 for a point 100 pixels into it."""
    backend, fake = _with_regions([(1280, 0, 1920, 1080)])
    backend.set_position(1380, 100)
    assert ("motion", POINTER_DEVICE, 1380.0, 100.0) in fake.calls


def test_the_far_edges_of_a_region_are_outside_it(monkeypatch):
    monkeypatch.setattr(libei_mod, "layout_origin", lambda: (0, 0))
    backend, fake = _with_regions([(0, 0, 1920, 1080)])
    backend.set_position(1919, 1079)
    assert ("motion", POINTER_DEVICE, 1919.0, 1079.0) in fake.calls
    with pytest.raises(LibeiUnavailable, match="outside every region"):
        backend.set_position(1920, 1080)


def test_a_point_no_region_covers_is_refused_not_silently_dropped(monkeypatch):
    """The bug this section exists for. Without the check libei swallows the
    motion and ``set_position`` returns as though the pointer had moved."""
    monkeypatch.setattr(libei_mod, "layout_origin", lambda: (0, 0))
    backend, fake = _with_regions([(0, 0, 1920, 1080)])
    with pytest.raises(LibeiUnavailable, match=r"\(4000, 30\) lies outside"):
        backend.set_position(4000, 30)
    assert not [call for call in fake.calls if call[0] == "motion"]


def test_a_refused_motion_is_not_committed_with_a_frame(monkeypatch):
    """Nothing was buffered, so nothing may be flushed — a frame here would
    commit whatever the previous emission left on the device."""
    monkeypatch.setattr(libei_mod, "layout_origin", lambda: (0, 0))
    backend, fake = _with_regions([(0, 0, 1920, 1080)])
    with pytest.raises(LibeiUnavailable):
        backend.set_position(4000, 30)
    assert not [call for call in fake.calls if call[0] == "frame"]


def test_a_negative_layout_origin_is_normalised_into_region_space(monkeypatch):
    """Region offsets are ``uint32``, so a compositor cannot advertise one
    left of the origin — but a monitor placed left of the primary gives this
    project's layout a negative origin. Input has to make the same shift
    capture already makes, or ``get_pixel`` and ``set_position`` name
    different pixels."""
    monkeypatch.setattr(libei_mod, "layout_origin", lambda: (-1280, 0))
    backend, fake = _with_regions([(0, 0, 1280, 1024), (1280, 0, 1920, 1080)])
    backend.set_position(-1280, 10)
    assert ("motion", POINTER_DEVICE, 0.0, 10.0) in fake.calls


def test_normalising_is_not_attempted_on_a_layout_that_starts_at_zero(
        monkeypatch):
    """A zero origin makes the shift a no-op, so an out-of-region point must
    still be refused rather than sent twice."""
    monkeypatch.setattr(libei_mod, "layout_origin", lambda: (0, 0))
    backend, fake = _with_regions([(0, 0, 1920, 1080)])
    with pytest.raises(LibeiUnavailable):
        backend.set_position(-5, -5)
    assert not [call for call in fake.calls if call[0] == "motion"]


def test_a_point_outside_even_after_normalising_is_still_refused(monkeypatch):
    monkeypatch.setattr(libei_mod, "layout_origin", lambda: (-1280, 0))
    backend, fake = _with_regions([(0, 0, 1280, 1024)])
    with pytest.raises(LibeiUnavailable, match="outside every region"):
        backend.set_position(9000, 9000)
    assert not [call for call in fake.calls if call[0] == "motion"]


def test_the_layout_origin_is_only_consulted_when_a_point_misses():
    """It costs a ``wlr-randr`` subprocess, so it must stay off the path
    every ordinary mouse move takes."""
    asked = []
    with patch.object(libei_mod, "layout_origin",
                      side_effect=lambda: asked.append(1) or (0, 0)):
        backend, _fake = _with_regions([(0, 0, 1920, 1080)])
        backend.set_position(640, 400)
    assert asked == []


def test_layout_origin_is_zero_when_the_layout_cannot_be_read():
    """GNOME and KDE have no ``wlr-randr``; they also normalise the layout
    themselves, so zero is the right answer rather than a fallback."""
    with patch("je_auto_control.linux_wayland.screen.layout_origin",
               side_effect=OSError("no wlr-randr")):
        assert libei_mod.layout_origin() == (0, 0)


def test_region_enumeration_stops_at_the_ceiling():
    """A libei whose contract differs must not hang the caller's mouse."""
    fake = FakeLibei()
    fake.ei_device_get_region = lambda _device, index: ("endless", index)
    fake.ei_region_get_x = lambda _handle: 0
    fake.ei_region_get_y = lambda _handle: 0
    fake.ei_region_get_width = lambda _handle: 1
    fake.ei_region_get_height = lambda _handle: 1
    backend, _fake = _connected(fake)
    assert len(backend._device_regions(POINTER_DEVICE)) == libei_mod._MAX_REGIONS


def test_a_motion_refused_for_its_region_reaches_the_cli(monkeypatch):
    """End to end: the refusal is the *point*, because ``emitted`` turns it
    into the ydotool move that libei would have swallowed."""
    from je_auto_control.linux_wayland import mouse as wayland_mouse
    monkeypatch.setattr(libei_mod, "layout_origin", lambda: (0, 0))
    backend, fake = _with_regions([(0, 0, 1920, 1080)])
    captured = []

    binary, run = _cli_capture(wayland_mouse, captured)
    with patch.object(wayland_mouse, "_try_libei", return_value=backend), \
         binary, run:
        wayland_mouse.set_position(4000, 30)
    assert not [call for call in fake.calls if call[0] == "motion"]
    assert captured[0][1:] == ["mousemove", "--absolute",
                               "-x", "4000", "-y", "30"]


def test_click_button_presses_then_releases():
    backend, fake = _connected()
    backend.click_button(272)
    buttons = [call for call in fake.calls if call[0] == "button"]
    assert buttons == [("button", POINTER_DEVICE, 272, True),
                       ("button", POINTER_DEVICE, 272, False)]


def test_a_paused_device_stops_accepting_emissions():
    """Pause arrives asynchronously; emitting into a paused device would be
    silently dropped, so it has to raise and let the CLI take over."""
    backend, fake = _connected()
    fake.pending = [(libei_mod.EI_EVENT_DEVICE_PAUSED, KEYBOARD_DEVICE)]
    with pytest.raises(LibeiUnavailable, match="no libei device"):
        backend.press_key(30)


def test_emitting_before_connect_raises():
    backend = LibeiBackend(symbols=FakeLibei())
    with pytest.raises(LibeiUnavailable, match="not connected"):
        backend.press_key(30)


def test_backend_reports_unavailable_when_symbols_missing():
    backend = LibeiBackend(symbols=None)
    assert backend.is_available is False
    with pytest.raises(LibeiUnavailable):
        backend.connect()


def test_disconnect_ends_the_portal_session_and_releases_a_live_context():
    """A completed handshake is released properly — devices, then the context.

    ``ei_unref`` is only unsafe on a context whose backend opened but whose
    handshake never progressed; on a live one it is safe, measured against a
    real EIS peer in ``docker/eis_verify.py``. The portal session is a
    different library and always closes, or the compositor keeps the
    remote-desktop grant open."""
    session = MagicMock()
    backend, fake = _connected(session=session)
    backend.disconnect()
    session.close.assert_called_once()
    assert backend.is_connected is False
    assert ("unref",) in fake.calls
    devices = [call for call in fake.calls if call[0] == "device_unref"]
    assert devices, "the devices were dropped without being unreffed"
    assert _kinds(fake).index("unref") > _kinds(fake).index("device_unref"), \
        "the context was unreffed before its devices, so those are use-after-free"


def test_a_handshake_that_never_completed_abandons_the_context():
    """The one state where ``ei_unref`` segfaults must still be abandoned.

    ``docker/libei_verify.py`` measures it: a backend that opened but never
    handshook takes the process down on unref, and on ``ei_disconnect`` too,
    so it is not a refcount mistake here."""
    fake = FakeLibei(events=[])   # nothing arrives, so no device goes live
    backend = LibeiBackend(symbols=fake,
                           portal_connect=lambda: (7, MagicMock()))
    with _portal_present():
        with pytest.raises(LibeiUnavailable):
            backend.connect(timeout=0.05)
    assert ("unref",) not in fake.calls


# === Probe caching ========================================================

def test_a_failed_probe_is_not_retried_on_every_keystroke():
    """The probe costs a portal round trip and possibly a consent dialog.
    Paying that per key press would be worse than not having libei at all."""
    libei_mod.reset_default_backend()
    attempts = []

    class _Failing(LibeiBackend):
        def __init__(self, **_kwargs):
            super().__init__(symbols=FakeLibei())

        def connect(self, **_kwargs):
            attempts.append(1)
            raise LibeiUnavailable("no portal here")

    try:
        with patch.object(libei_mod, "LibeiBackend", _Failing):
            assert libei_mod.connected_backend() is None
            assert libei_mod.connected_backend() is None
            assert libei_mod.connected_backend() is None
    finally:
        libei_mod.reset_default_backend()
    assert len(attempts) == 1


def test_active_backend_is_none_when_the_selector_says_cli(monkeypatch):
    monkeypatch.setenv("JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND", "cli")
    assert select_mod.active_backend() is None


# === Keyboard / mouse fall back rather than fail ==========================

def test_keyboard_falls_back_to_ydotool_when_libei_is_unavailable():
    import subprocess

    from je_auto_control.linux_wayland import keyboard as wayland_keyboard
    captured = []

    with patch.object(wayland_keyboard, "_try_libei", return_value=None), \
         patch.object(wayland_keyboard, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_keyboard.subprocess, "run",
                      side_effect=lambda argv, **kw: (
                          captured.append(list(argv))
                          or subprocess.CompletedProcess(argv, 0, b"", b""))):  # nosemgrep
        wayland_keyboard.press_key(28)
    assert captured == [["/usr/bin/ydotool", "key", "28:1"]]


def test_keyboard_uses_libei_when_it_is_connected():
    from je_auto_control.linux_wayland import keyboard as wayland_keyboard
    backend = MagicMock()
    with patch.object(wayland_keyboard, "_try_libei", return_value=backend):
        wayland_keyboard.press_key(28)
    backend.press_key.assert_called_once_with(28)


def test_mouse_button_maps_onto_an_evdev_code_for_libei():
    from je_auto_control.linux_wayland import mouse as wayland_mouse
    backend = MagicMock()
    with patch.object(wayland_mouse, "_try_libei", return_value=backend):
        wayland_mouse.press_mouse(wayland_mouse.wayland_mouse_left)
    # BTN_LEFT, not ydotool's 0xC0 bitmask.
    backend.press_button.assert_called_once_with(272)


def _scroll_calls(backend):
    return [tuple(call.args) for call in backend.scroll.call_args_list]


def test_mouse_scroll_flips_the_vertical_axis_for_libei():
    """The two paths count wheel detents in opposite directions.

    This module's ``wayland_scroll_direction_*`` constants are in the
    kernel's ``REL_WHEEL`` frame — what ydotool writes into ``/dev/uinput``,
    where positive is up. libei is in the ``wl_pointer`` / libinput frame,
    where positive is down: libinput's own evdev reader negates ``REL_WHEEL``
    to get there. Handing the constant over unchanged would scroll the wrong
    way on every libei host, and scrolling the wrong way fails silently.
    """
    from je_auto_control.linux_wayland import mouse as wayland_mouse
    backend = MagicMock()

    with patch.object(wayland_mouse, "_try_libei", return_value=backend), \
         patch.object(wayland_mouse, "binary_path", return_value=None):
        wayland_mouse.scroll(5, wayland_mouse.wayland_scroll_direction_up)
        wayland_mouse.scroll(5, wayland_mouse.wayland_scroll_direction_down)
    # binary_path is None, so any fall-through to the CLI would have raised.
    assert _scroll_calls(backend) == [(0, -5), (0, 5)]


def test_mouse_scroll_does_not_flip_the_horizontal_axis_for_libei():
    """``REL_HWHEEL`` and libinput agree that right is positive, and
    libinput passes that axis through unnegated — so flipping both axes
    would be as wrong as flipping neither."""
    from je_auto_control.linux_wayland import mouse as wayland_mouse
    backend = MagicMock()

    with patch.object(wayland_mouse, "_try_libei", return_value=backend), \
         patch.object(wayland_mouse, "binary_path", return_value=None):
        wayland_mouse.scroll(3, wayland_mouse.wayland_scroll_direction_right)
        wayland_mouse.scroll(3, wayland_mouse.wayland_scroll_direction_left)
    assert _scroll_calls(backend) == [(3, 0), (-3, 0)]


def _cli_capture(module, captured):
    """Patch ``module``'s ydotool lookup and subprocess.run, recording argv."""
    import subprocess

    return (
        patch.object(module, "binary_path", return_value="/usr/bin/ydotool"),
        patch.object(module.subprocess, "run",
                     side_effect=lambda argv, **kw: (
                         captured.append(list(argv))
                         or subprocess.CompletedProcess(argv, 0, b"", b""))),  # nosemgrep
    )


def test_libei_unavailable_is_catchable_as_an_autocontrol_error():
    """It used to inherit ``RuntimeError`` alone, so every ``except
    AutoControlException`` boundary — the executor, the poll loops, the
    request handlers, the GUI slots — let it straight through."""
    from je_auto_control.utils.exception.exceptions import AutoControlException

    assert issubclass(LibeiUnavailable, AutoControlException)
    # The probes in _select_input and the two input modules catch
    # RuntimeError; that has to keep working.
    assert issubclass(LibeiUnavailable, RuntimeError)


def test_a_refused_emission_falls_back_to_the_cli():
    """A backend that finished its handshake can still refuse one emission —
    a paused device, a session that ended between calls. libei is documented
    as the fast path and never the only one, but the refusal used to escape
    the module instead of reaching ydotool."""
    from je_auto_control.linux_wayland import mouse as wayland_mouse
    backend = MagicMock()
    backend.set_position.side_effect = LibeiUnavailable("device paused")
    captured = []

    binary, run = _cli_capture(wayland_mouse, captured)
    with patch.object(wayland_mouse, "_try_libei", return_value=backend), \
         binary, run:
        wayland_mouse.set_position(120, 240)
    assert captured[0][1:] == ["mousemove", "--absolute",
                               "-x", "120", "-y", "240"]


def test_a_refused_scroll_falls_back_to_the_cli_in_ydotools_own_frame():
    """And it falls back *unflipped*: the vertical flip belongs to libei."""
    from je_auto_control.linux_wayland import mouse as wayland_mouse
    backend = MagicMock()
    backend.scroll.side_effect = LibeiUnavailable("device paused")
    captured = []

    binary, run = _cli_capture(wayland_mouse, captured)
    with patch.object(wayland_mouse, "_try_libei", return_value=backend), \
         binary, run:
        wayland_mouse.scroll(5, wayland_mouse.wayland_scroll_direction_up)
    assert captured[0][1:] == ["mousemove", "--wheel", "-x", "0", "-y", "5"]


def test_a_refused_button_release_still_reaches_the_cli():
    """The worst refusal to drop: the press landed, so giving up on the
    release leaves the button held for the rest of the session."""
    from je_auto_control.linux_wayland import mouse as wayland_mouse
    backend = MagicMock()
    backend.release_button.side_effect = LibeiUnavailable("device paused")
    captured = []

    binary, run = _cli_capture(wayland_mouse, captured)
    with patch.object(wayland_mouse, "_try_libei", return_value=backend), \
         binary, run:
        wayland_mouse.click_mouse(wayland_mouse.wayland_mouse_left)
    backend.press_button.assert_called_once_with(272)
    # 0xC0 with the down-bit cleared: a release-only click.
    assert captured[0][1:] == ["click", "0x80"]


def test_a_refused_key_press_falls_back_to_the_cli():
    from je_auto_control.linux_wayland import keyboard as wayland_keyboard
    backend = MagicMock()
    backend.press_key.side_effect = LibeiUnavailable("device paused")
    captured = []

    binary, run = _cli_capture(wayland_keyboard, captured)
    with patch.object(wayland_keyboard, "_try_libei", return_value=backend), \
         binary, run:
        wayland_keyboard.press_key(28)
    assert captured[0][1:] == ["key", "28:1"]


def test_a_chord_refused_part_way_releases_what_it_already_pressed():
    """Otherwise the fallback presses Ctrl again on top of a Ctrl that libei
    never released, and the modifier is stuck once the CLI chord ends."""
    from je_auto_control.linux_wayland import keyboard as wayland_keyboard
    backend = MagicMock()
    backend.press_key.side_effect = [None, LibeiUnavailable("device paused")]
    captured = []

    binary, run = _cli_capture(wayland_keyboard, captured)
    with patch.object(wayland_keyboard, "_try_libei", return_value=backend), \
         binary, run:
        wayland_keyboard.hotkey([29, 42])
    backend.release_key.assert_called_once_with(29)
    assert captured[0][1:] == ["key", "29:1", "42:1", "42:0", "29:0"]


def test_mouse_scroll_falls_back_to_ydotool_without_libei():
    """No libei means the ydotool argv, in ydotool's own frame — unflipped."""
    import subprocess

    from je_auto_control.linux_wayland import mouse as wayland_mouse
    captured = []

    with patch.object(wayland_mouse, "_try_libei", return_value=None), \
         patch.object(wayland_mouse, "binary_path",
                      return_value="/usr/bin/ydotool"), \
         patch.object(wayland_mouse.subprocess, "run",
                      side_effect=lambda argv, **kw: (
                          captured.append(list(argv))
                          or subprocess.CompletedProcess(argv, 0, b"", b""))):  # nosemgrep
        wayland_mouse.scroll(5, wayland_mouse.wayland_scroll_direction_down)
    assert captured[0][1:] == ["mousemove", "--wheel", "-x", "0", "-y", "-5"]
