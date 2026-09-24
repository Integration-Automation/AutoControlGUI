"""Window management through EWMH, from any square rather than only Linux.

`x11_backend.py` was at 0% everywhere. `Progress.md` had it down as "only the
two Linux squares can run it" -- but every `Xlib` import in the module is
*inside* a method, so the module loads on Windows and macOS too and only the
calls need a display. A stub in `sys.modules` (`_xlib_stub.py`) reaches all of
it from every square, which is what makes it worth writing: the coverage floor
is the lowest square, so a test that runs on two of nine moves it least.

What is actually being checked is protocol arithmetic, and it is the kind
that fails silently:

* **EWMH requests go to the *root*, not to the window.** They are addressed
  there with `SubstructureRedirect`, which is what routes them to the window
  manager -- the only party allowed to act on them. Sending to the window
  instead is a message nobody answers.
* **Stacking order is bottom-to-top.** `list_windows` reverses it so the
  front-most window is first, which is what makes "the first title that
  matches" the one the user meant. `_NET_CLIENT_LIST` carries no order at
  all, so it is only a fallback and must *not* be reversed.
* **`move()` sizes the client while `window_rect()` reads the frame.** EWMH
  and Win32 disagree about which rectangle they mean, so the decorations
  come off the requested size; getting that wrong is a window that shrinks a
  title bar's worth every time a script round-trips it.
* **Source indication 2 means "pager".** A window manager honours it without
  the focus-stealing prevention it applies to source 1, so a raise sent as an
  application is a raise that quietly does not happen.

The stub's constants carry their real `X.h` values, and
`test_xlib_stub_values.py` holds them to the installed library wherever there
is one -- so the masks asserted below are the numbers that go on the wire.
"""
from __future__ import annotations

import pytest

from headless import _xlib_stub
from je_auto_control.utils.exception.exceptions import (
    AutoControlUnsupportedOperationException,
)
from je_auto_control.wrapper.window_backends import x11_backend as x11
from je_auto_control.wrapper.window_backends.x11_backend import (
    X11WindowBackend, _as_text,
)

_X = _xlib_stub.X_CONSTANTS
_REDIRECT = (_X["SubstructureRedirectMask"] | _X["SubstructureNotifyMask"])


@pytest.fixture
def on_linux(monkeypatch):
    """Answer `_is_linux()` the way an X session would."""
    monkeypatch.setattr(x11.sys, "platform", "linux")


@pytest.fixture
def display(monkeypatch, on_linux):
    return _xlib_stub.install(monkeypatch)


@pytest.fixture
def backend(display):
    instance = X11WindowBackend()
    assert instance.available, "the stub display opens"
    return instance


def _client_messages(display):
    """Every EWMH request the backend addressed to the root window."""
    return [(event.fields["client_type"], event.fields["data"], mask)
            for event, mask, _propagate in display.root.sent]


def _named_messages(display):
    """The same, with atoms resolved back to the names they were interned as."""
    return [(display.atom_name(atom), data[1], mask)
            for atom, data, mask in _client_messages(display)]


# --- availability -------------------------------------------------------------

def test_the_backend_is_unavailable_off_linux(monkeypatch):
    monkeypatch.setattr(x11.sys, "platform", "win32")
    _xlib_stub.install(monkeypatch)
    backend = X11WindowBackend()
    assert backend.available is False
    assert backend._connection is None, "it did not even try to connect"


@pytest.mark.parametrize("platform", ["linux", "linux2"])
def test_both_spellings_of_linux_are_linux(monkeypatch, platform):
    monkeypatch.setattr(x11.sys, "platform", platform)
    _xlib_stub.install(monkeypatch)
    assert X11WindowBackend().available is True


def test_a_session_with_no_display_is_unavailable_rather_than_fatal(
        monkeypatch, on_linux):
    # No `DISPLAY` is the ordinary state of a Wayland session or an ssh
    # login; the selector turns this into a null backend with a reason.
    _xlib_stub.install_failing(monkeypatch, RuntimeError("no DISPLAY"))
    assert X11WindowBackend().available is False


def test_the_backend_names_the_protocol_it_speaks(backend):
    assert backend.name == "x11-ewmh"


# --- the connection and its atoms ---------------------------------------------

def test_the_display_is_opened_once_and_kept(backend, display):
    assert backend._display() is display
    assert backend._display() is display


def test_an_atom_is_interned_once_per_connection(backend, display):
    first = backend._atom("_NET_WM_STATE")
    assert backend._atom("_NET_WM_STATE") == first
    assert list(display.atoms) == ["_NET_WM_STATE"]


def test_a_missing_property_reads_as_none(backend, display):
    assert backend._property(display.root, "_NET_CLIENT_LIST") is None


# --- listing ------------------------------------------------------------------

def test_listing_puts_the_front_most_window_first(backend, display):
    # `_NET_CLIENT_LIST_STACKING` is bottom-to-top, so 30 is in front.
    display.set_root_property("_NET_CLIENT_LIST_STACKING", [10, 20, 30])
    for window_id, title in ((10, "back"), (20, "middle"), (30, "front")):
        _titled(display, window_id, title)
    assert backend.list_windows() == [(30, "front"), (20, "middle"),
                                      (10, "back")]


def test_listing_falls_back_to_the_unordered_list(backend, display):
    # `_NET_CLIENT_LIST` has no stacking meaning, so reversing it would
    # invent an order the window manager never stated.
    display.set_root_property("_NET_CLIENT_LIST", [10, 20])
    _titled(display, 10, "first")
    _titled(display, 20, "second")
    assert backend.list_windows() == [(10, "first"), (20, "second")]


def test_a_desktop_with_no_windows_lists_nothing(backend, display):
    assert backend.list_windows() == []


def test_a_title_prefers_the_utf8_property(backend, display):
    display.set_root_property("_NET_CLIENT_LIST_STACKING", [10])
    display.intern_atom("_NET_WM_NAME")
    display.window(10, properties={"_NET_WM_NAME": b"Editor \xe2\x80\x94 file"},
                   wm_name="legacy")
    assert backend.list_windows() == [(10, "Editor — file")]


def test_a_title_falls_back_to_the_legacy_property(backend, display):
    display.set_root_property("_NET_CLIENT_LIST_STACKING", [10])
    display.intern_atom("_NET_WM_NAME")
    display.window(10, wm_name="Old Toolkit")
    assert backend.list_windows() == [(10, "Old Toolkit")]


def test_a_window_that_vanishes_mid_walk_lists_with_an_empty_title(
        backend, display):
    # The list is a snapshot; by the time a title is read the window may be
    # gone, and one closing window must not fail the whole enumeration.
    display.set_root_property("_NET_CLIENT_LIST_STACKING", [10, 20])
    _titled(display, 10, "still here")
    display.window(20).property_error = RuntimeError("BadWindow")
    assert backend.list_windows() == [(20, ""), (10, "still here")]


def _titled(display, window_id: int, title: str):
    display.intern_atom("_NET_WM_NAME")
    return display.window(window_id,
                          properties={"_NET_WM_NAME": title.encode("utf-8")})


# --- the focused window -------------------------------------------------------

def test_the_foreground_window_is_the_first_id_the_property_names(backend,
                                                                 display):
    display.set_root_property("_NET_ACTIVE_WINDOW", [42])
    assert backend.foreground_window() == 42


@pytest.mark.parametrize("value", [None, []])
def test_no_focused_window_reads_as_zero(backend, display, value):
    if value is not None:
        display.set_root_property("_NET_ACTIVE_WINDOW", value)
    assert backend.foreground_window() == 0


# --- rectangles ---------------------------------------------------------------

def test_the_rectangle_is_the_frame_not_the_client(backend, display):
    # A reparenting window manager makes the client a grandchild of the root
    # inside a frame that carries the border and title bar; the frame is what
    # the user sees and drags, and what Win32's GetWindowRect would report.
    display.window(50, parent_id=99, geometry=(0, 0, 10, 10))
    display.window(99, parent_id=1, geometry=(100, 200, 640, 480))
    assert backend.window_rect(50) == (100, 200, 740, 680)


def test_an_undecorated_window_is_its_own_frame(backend, display):
    display.window(50, parent_id=1, geometry=(5, 6, 70, 80))
    assert backend.window_rect(50) == (5, 6, 75, 86)


def test_a_window_whose_parent_is_gone_is_its_own_frame(backend, display):
    display.window(50, parent_id=None, geometry=(1, 2, 3, 4))
    assert backend.window_rect(50) == (1, 2, 4, 6)


def test_a_frame_walk_cannot_loop_forever(backend, display):
    # A cycle in the tree would hang the caller; the walk is bounded instead.
    display.window(50, parent_id=51, geometry=(0, 0, 1, 1))
    display.window(51, parent_id=50, geometry=(7, 7, 2, 2))
    assert backend.window_rect(50) is not None


def test_a_rectangle_for_a_window_that_is_gone_is_none(backend, display):
    display.window(50, parent_id=1)
    display.window(50).geometry_error = RuntimeError("BadWindow")
    assert backend.window_rect(50) is None


# --- ownership and state ------------------------------------------------------

def test_the_owning_pid_comes_from_the_ewmh_property(backend, display):
    display.intern_atom("_NET_WM_PID")
    display.window(50, properties={"_NET_WM_PID": [4321]})
    assert backend.window_process_id(50) == 4321


def test_a_window_with_no_pid_property_reports_zero(backend, display):
    assert backend.window_process_id(50) == 0


def test_a_pid_read_that_fails_reports_zero(backend, display):
    display.window(50).property_error = RuntimeError("BadWindow")
    assert backend.window_process_id(50) == 0


def test_a_hidden_window_is_minimised(backend, display):
    hidden = backend._atom("_NET_WM_STATE_HIDDEN")
    display.intern_atom("_NET_WM_STATE")
    display.window(50, properties={"_NET_WM_STATE": [hidden]})
    assert backend.is_minimized(50) is True


def test_a_window_in_another_state_is_not_minimised(backend, display):
    display.intern_atom("_NET_WM_STATE")
    other = display.intern_atom("_NET_WM_STATE_MAXIMIZED_VERT")
    display.window(50, properties={"_NET_WM_STATE": [other]})
    assert backend.is_minimized(50) is False


def test_a_window_with_no_state_property_is_not_minimised(backend, display):
    assert backend.is_minimized(50) is False


def test_a_state_read_that_fails_is_not_minimised(backend, display):
    display.window(50).property_error = RuntimeError("BadWindow")
    assert backend.is_minimized(50) is False


# --- raising and restoring ----------------------------------------------------

def test_raising_a_window_addresses_the_root_as_a_pager(backend, display):
    backend.set_foreground(50)
    [(name, source, mask)] = _named_messages(display)
    assert name == "_NET_ACTIVE_WINDOW"
    assert source[0] == 2, "source 2 is 'pager'; source 1 gets refused"
    assert mask == _REDIRECT
    assert display.root.sent[0][0].fields["window"].id == 50


def test_the_request_carries_the_window_it_is_about(backend, display):
    backend.set_foreground(50)
    event = display.root.sent[0][0]
    assert event.fields["window"].id == 50, "addressed to root, about 50"


def test_a_client_message_is_padded_to_five_values(backend, display):
    backend.set_foreground(50)
    _format, data = display.root.sent[0][0].fields["data"]
    assert _format == 32
    assert len(data) == 5


def test_restoring_maps_the_window_before_raising_it(backend, display):
    backend.restore(50)
    assert display.window(50).mapped is True
    assert [name for name, _, _ in _named_messages(display)] == [
        "_NET_ACTIVE_WINDOW",
    ]


# --- show-state codes ---------------------------------------------------------

def test_hiding_unmaps_the_window(backend, display):
    backend.show(50, x11.SW_HIDE)
    assert display.window(50).mapped is False


@pytest.mark.parametrize("code", [x11.SW_SHOWNORMAL, x11.SW_RESTORE])
def test_the_normal_and_restore_codes_both_restore(backend, display, code):
    backend.show(50, code)
    assert display.window(50).mapped is True


@pytest.mark.parametrize("code", [x11.SW_MINIMIZE, x11.SW_SHOWMINIMIZED])
def test_both_minimise_codes_send_the_icccm_request(backend, display, code):
    backend.show(50, code)
    assert [name for name, _, _ in _named_messages(display)] == [
        "WM_CHANGE_STATE",
    ]


def test_maximising_names_both_axes(backend, display):
    # `_NET_WM_STATE_ADD` is 1, and a request that names one axis grows the
    # window one way only.
    backend.show(50, x11.SW_MAXIMIZE)
    [(name, data, _mask)] = _named_messages(display)
    assert name == "_NET_WM_STATE"
    assert data[0] == 1, "_NET_WM_STATE_ADD"
    assert {data[1], data[2]} == {
        backend._atom("_NET_WM_STATE_MAXIMIZED_HORZ"),
        backend._atom("_NET_WM_STATE_MAXIMIZED_VERT"),
    }


def test_a_show_code_with_no_x11_meaning_is_refused(backend, display):
    # SW_SHOWNA, SW_FORCEMINIMIZE and friends have no X11 equivalent, and
    # guessing at one would move a window the caller did not ask to move.
    with pytest.raises(AutoControlUnsupportedOperationException,
                       match="show"):
        backend.show(50, 8)
    assert display.root.sent == []


# --- closing and minimising ---------------------------------------------------

def test_closing_sends_the_ewmh_close_request(backend, display):
    assert backend.close(50) is True
    [(name, data, _mask)] = _named_messages(display)
    assert name == "_NET_CLOSE_WINDOW"
    assert data[1] == 2, "source 2, as with every other request here"


def test_a_close_that_the_connection_refuses_reports_failure(backend, display):
    display.root.send_error = RuntimeError("connection lost")
    assert backend.close(50) is False


def test_minimising_uses_the_icccm_request(backend, display):
    # There is no `_NET_` message for iconify; `WM_CHANGE_STATE` with the
    # ICCCM iconic state is what every window manager implements.
    assert backend.minimize(50) is True
    [(name, data, _mask)] = _named_messages(display)
    assert name == "WM_CHANGE_STATE"
    assert data[0] == 3, "IconicState"


def test_a_minimise_that_the_connection_refuses_reports_failure(backend,
                                                                display):
    display.root.send_error = RuntimeError("connection lost")
    assert backend.minimize(50) is False


# --- moving -------------------------------------------------------------------

def test_moving_takes_the_decorations_off_the_requested_size(backend, display):
    # EWMH sizes the client; Win32's MoveWindow sizes the frame. Subtracting
    # the extents is what makes move() round-trip with window_rect().
    display.intern_atom("_NET_FRAME_EXTENTS")
    display.window(50, properties={"_NET_FRAME_EXTENTS": [4, 4, 30, 2]})
    assert backend.move(50, 100, 200, 640, 480) is True
    [(name, data, _mask)] = _named_messages(display)
    assert name == "_NET_MOVERESIZE_WINDOW"
    assert data[1:] == [100, 200, 640 - 8, 480 - 32]


def test_moving_a_window_with_no_extents_uses_the_size_as_given(backend,
                                                                display):
    backend.move(50, 10, 20, 300, 400)
    [(_name, data, _mask)] = _named_messages(display)
    assert data[1:] == [10, 20, 300, 400]


def test_an_unreadable_extents_property_is_treated_as_no_decorations(backend,
                                                                     display):
    # Not knowing the border thickness is not a reason to refuse the move:
    # the window ends up a border's worth larger, which is recoverable, while
    # refusing leaves the caller with a window that never moved at all.
    display.window(50).property_error = RuntimeError("BadWindow")
    assert backend.move(50, 0, 0, 100, 100) is True
    [(_name, data, _mask)] = _named_messages(display)
    assert data[3:] == [100, 100]


def test_a_short_extents_property_is_treated_as_no_decorations(backend,
                                                               display):
    display.intern_atom("_NET_FRAME_EXTENTS")
    display.window(50, properties={"_NET_FRAME_EXTENTS": [4, 4]})
    backend.move(50, 0, 0, 100, 100)
    [(_name, data, _mask)] = _named_messages(display)
    assert data[3:] == [100, 100]


def test_a_window_smaller_than_its_own_decorations_still_gets_a_size(backend,
                                                                     display):
    # A client size of zero or less is not a request any window manager can
    # honour, so it floors at one pixel rather than going negative.
    display.intern_atom("_NET_FRAME_EXTENTS")
    display.window(50, properties={"_NET_FRAME_EXTENTS": [40, 40, 40, 40]})
    backend.move(50, 0, 0, 10, 10)
    [(_name, data, _mask)] = _named_messages(display)
    assert data[3:] == [1, 1]


def test_the_move_flags_name_all_four_fields_and_the_pager_source(backend,
                                                                  display):
    backend.move(50, 0, 0, 100, 100)
    [(_name, data, _mask)] = _named_messages(display)
    flags = data[0]
    for bit in (8, 9, 10, 11):
        assert flags & (1 << bit), f"bit {bit} says one of x/y/w/h is supplied"
    assert (flags >> 12) & 0b11 == 2, "source indication 2 is 'pager'"


def test_a_move_the_connection_refuses_reports_failure(backend, display):
    display.root.send_error = RuntimeError("connection lost")
    assert backend.move(50, 0, 0, 100, 100) is False


# --- posting input to an unfocused window -------------------------------------

def test_posting_a_key_sends_a_press_and_a_release(backend, display):
    assert backend.post_key(50, keycode=38, character="a") is True
    sent = display.window(50).sent
    assert [event.kind for event, _mask, _p in sent] == ["KeyPress",
                                                         "KeyRelease"]
    assert [mask for _e, mask, _p in sent] == [_X["KeyPressMask"],
                                               _X["KeyReleaseMask"]]


def test_a_posted_key_is_addressed_by_keycode_not_by_character(backend,
                                                               display):
    # X11 has no "type this character" event; the character is Win32's idea
    # and is dropped rather than guessed at.
    backend.post_key(50, keycode=38, character="Z")
    press = display.window(50).sent[0][0]
    assert press.fields["detail"] == 38
    assert "character" not in press.fields


def test_a_posted_key_is_marked_as_propagating(backend, display):
    # Synthetic events are what XSendEvent delivers; propagate lets the
    # toolkit that does accept them see it on an ancestor.
    backend.post_key(50, keycode=38)
    assert display.window(50).sent[0][2] is True


def test_a_post_key_that_the_connection_refuses_reports_failure(backend,
                                                                display):
    display.window(50).send_error = RuntimeError("connection lost")
    assert backend.post_key(50, keycode=38) is False


@pytest.mark.parametrize("button,number", [
    ("left", 1), ("middle", 2), ("right", 3),
    ("LEFT", 1), ("mouse_right", 3),
])
def test_posting_a_click_maps_the_button_name_to_x11_numbering(
        backend, display, button, number):
    assert backend.post_click(50, button, x=7, y=9) is True
    press = display.window(50).sent[0][0]
    assert press.fields["detail"] == number


def test_a_posted_click_carries_window_relative_coordinates(backend, display):
    backend.post_click(50, "left", x=7, y=9)
    press = display.window(50).sent[0][0]
    assert (press.fields["event_x"], press.fields["event_y"]) == (7, 9)
    assert (press.fields["root_x"], press.fields["root_y"]) == (0, 0)


def test_posting_a_click_sends_a_press_and_a_release(backend, display):
    backend.post_click(50, "left", x=0, y=0)
    sent = display.window(50).sent
    assert [event.kind for event, _mask, _p in sent] == ["ButtonPress",
                                                         "ButtonRelease"]
    assert [mask for _e, mask, _p in sent] == [_X["ButtonPressMask"],
                                               _X["ButtonReleaseMask"]]


def test_an_unknown_button_is_refused_rather_than_guessed(backend, display):
    with pytest.raises(AutoControlUnsupportedOperationException,
                       match="post_click"):
        backend.post_click(50, "thumb", x=0, y=0)
    assert display.window(50).sent == []


def test_a_post_click_that_the_connection_refuses_reports_failure(backend,
                                                                  display):
    display.window(50).send_error = RuntimeError("connection lost")
    assert backend.post_click(50, "left", x=0, y=0) is False


# --- every request is flushed -------------------------------------------------

@pytest.mark.parametrize("action", [
    lambda b: b.set_foreground(50),
    lambda b: b.restore(50),
    lambda b: b.show(50, x11.SW_HIDE),
    lambda b: b.close(50),
    lambda b: b.minimize(50),
    lambda b: b.move(50, 0, 0, 10, 10),
    lambda b: b.post_key(50, 38),
    lambda b: b.post_click(50, "left", 0, 0),
])
def test_every_action_flushes_the_connection(backend, display, action):
    # X buffers requests; one that is never flushed is one the window manager
    # does not see until something else happens to flush it.
    before = display.flushes
    action(backend)
    assert display.flushes > before


# --- property decoding --------------------------------------------------------

@pytest.mark.parametrize("value,expected", [
    (None, ""),
    (b"plain", "plain"),
    ("already text", "already text"),
    (b"caf\xc3\xa9", "café"),
    ([104, 105], "hi"),
    ([104, 105, 0, 0], "hi"),
    (b"\xff\xfe", "��"),
])
def test_a_property_value_decodes_to_text(value, expected):
    # X properties arrive as bytes, as str, or as an array of byte-sized
    # ints depending on the property and the Xlib version, and a title that
    # is not valid UTF-8 is a title to show badly, not an exception.
    assert _as_text(value) == expected


def test_an_undecodable_property_falls_back_to_its_repr():
    assert _as_text(object) == str(object)
