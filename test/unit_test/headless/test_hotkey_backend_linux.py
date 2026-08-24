"""Grabbing a hotkey on X11, from any square rather than only Linux.

`utils/hotkey/backends/` is the last of the project's backend seams with a
real hole in it -- accessibility and window management are covered now, and
the OCR / vision / LLM / agent seams were already close to full. This is the
X11 half: 138 statements at 24%.

The same fact makes it reachable: every `Xlib` import is inside a function,
so a stub in `sys.modules` (`_xlib_stub.py`) drives the whole thing from all
nine CI squares.

What the grab has to get right, and what breaks silently if it does not:

* **A hotkey is grabbed four times, not once.** X reports NumLock and
  CapsLock as modifier bits in the event state, and a grab registered
  without them simply does not match while either is on. So every combo is
  registered under all four lock combinations, and the match ignores those
  same bits again on the way back.
* **A failed grab has to roll back the ones that already took.** X refuses a
  grab another client already holds, and it refuses it per lock-variant --
  so a combo can be half-grabbed. Leaving those held, with `_registered`
  never updated, leaks the grab and spams `BadAccess` on every following
  poll.
* **The match is exact on the modifiers, not a superset.** `ctrl+k` must not
  fire on `ctrl+shift+k`: the state has to equal the mask once the lock bits
  are masked out, or every binding shadows the ones above it.

The stub's constants and keysyms carry their real values, and
`test_xlib_stub_values.py` compares every one of them against the installed
library on the Linux squares.
"""
from __future__ import annotations

import threading

import pytest

from headless import _xlib_stub
from je_auto_control.utils.hotkey.backends.linux_backend import (
    LinuxHotkeyBackend, _combo_to_x11, _lock_all_mask, _lock_mask_variants,
)
from je_auto_control.utils.hotkey.hotkey_daemon import (
    BackendContext, HotkeyBinding,
)

_X = _xlib_stub.X_CONSTANTS
CTRL = _X["ControlMask"]
SHIFT = _X["ShiftMask"]
ALT = _X["Mod1Mask"]
SUPER = _X["Mod4Mask"]
NUM_LOCK = _X["Mod2Mask"]
CAPS_LOCK = _X["LockMask"]

#: What `_combo_to_x11` resolves "k" to, given the keycodes installed below.
K_KEYCODE = 45


@pytest.fixture
def display(monkeypatch):
    """An X display that resolves the keysyms these combos use."""
    fake = _xlib_stub.install(monkeypatch)
    fake.keycodes = {
        _xlib_stub.KEYSYMS["k"]: K_KEYCODE,
        _xlib_stub.KEYSYMS["q"]: 24,
        _xlib_stub.KEYSYMS["Return"]: 36,
        _xlib_stub.KEYSYMS["F5"]: 71,
        _xlib_stub.KEYSYMS["Page_Up"]: 112,
    }
    return fake


@pytest.fixture
def backend():
    return LinuxHotkeyBackend()


def _binding(binding_id="b1", combo="ctrl+alt+k"):
    return HotkeyBinding(binding_id=binding_id, combo=combo,
                         script_path="script.json")


def _context(bindings, fired=None, stop_after=1):
    """A context whose stop event trips after `stop_after` polls."""
    stop = threading.Event()
    state = {"polls": 0}

    def _get_bindings():
        state["polls"] += 1
        if state["polls"] >= stop_after:
            stop.set()
        return list(bindings)

    return BackendContext(stop_event=stop, get_bindings=_get_bindings,
                          fire=(fired if fired is not None else []).append)


# --- turning a combo into a grab ----------------------------------------------

@pytest.mark.parametrize("combo,mask", [
    ("k", 0),
    ("ctrl+k", CTRL),
    ("shift+k", SHIFT),
    ("alt+k", ALT),
    ("win+k", SUPER),
    ("ctrl+alt+k", CTRL | ALT),
    ("ctrl+shift+alt+win+k", CTRL | SHIFT | ALT | SUPER),
])
def test_a_combo_becomes_an_x11_modifier_mask(display, combo, mask):
    assert _combo_to_x11(combo) == (mask, K_KEYCODE)


@pytest.mark.parametrize("combo,keycode", [
    ("ctrl+enter", 36), ("ctrl+return", 36), ("ctrl+f5", 71),
    ("ctrl+pageup", 112),
])
def test_a_named_key_resolves_through_its_keysym(display, combo, keycode):
    # "pageup" is not what X calls it -- `Page_Up` is -- so the table in the
    # module is the only thing between the user's spelling and a grab.
    assert _combo_to_x11(combo)[1] == keycode


def test_a_single_character_key_needs_no_table_entry(display):
    assert _combo_to_x11("ctrl+Q")[1] == 24, "upper case is lowered first"


def test_a_multi_character_key_x_does_not_know_is_refused(display):
    with pytest.raises(ValueError, match="unsupported hotkey key"):
        _combo_to_x11("ctrl+mediaplay")


def test_a_key_with_no_keysym_is_refused(display):
    # `string_to_keysym` answers 0 for a name X has never heard of; grabbing
    # keycode 0 would register a hotkey on nothing.
    with pytest.raises(ValueError, match="unknown X keysym"):
        _combo_to_x11("ctrl+¥")


def test_resolving_a_combo_closes_the_display_it_opened(display):
    _combo_to_x11("ctrl+k")
    assert display.closed is True


# --- the lock-mask variants ---------------------------------------------------

def test_a_hotkey_is_grabbed_under_every_lock_combination(display):
    # X reports NumLock and CapsLock as modifier bits, and a grab registered
    # without them does not match while either is on.
    assert _lock_mask_variants() == [0, NUM_LOCK, CAPS_LOCK,
                                     NUM_LOCK | CAPS_LOCK]


def test_the_lock_bits_are_masked_out_of_the_event_state(display):
    assert _lock_all_mask() == NUM_LOCK | CAPS_LOCK


def test_without_xlib_the_variants_degrade_to_the_plain_grab(monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "Xlib", None)
    assert _lock_mask_variants() == [0]
    assert _lock_all_mask() == 0


# --- registering and unregistering --------------------------------------------

def test_a_new_binding_is_grabbed_four_times(backend, display):
    backend._sync(display, display.root, [_binding()])
    assert display.root.grabbed == [
        (K_KEYCODE, CTRL | ALT | extra) for extra in _lock_mask_variants()
    ]


def test_a_grab_owns_the_key_rather_than_observing_it(backend, display):
    # `owner_events=True` with async modes is what consumes the key, matching
    # Windows `RegisterHotKey` semantics.
    backend._sync(display, display.root, [_binding()])
    _keycode, _mask, owner_events, pointer, keyboard = display.root.grabs[0]
    assert owner_events is True
    assert pointer == keyboard == _X["GrabModeAsync"]


def test_a_binding_that_has_not_changed_is_not_re_grabbed(backend, display):
    bindings = [_binding()]
    backend._sync(display, display.root, bindings)
    before = len(display.root.grabs)
    backend._sync(display, display.root, bindings)
    assert len(display.root.grabs) == before


def test_a_binding_whose_combo_changed_releases_the_old_key(backend,
                                                            display):
    # Until 2026-08-24 the old grab was only forgotten, never released:
    # the previous combo stayed consumed from every application, fired
    # nothing, and `_ungrab_all` could not free what it no longer knew
    # about. The Windows backend has always unregistered here.
    backend._sync(display, display.root, [_binding(combo="ctrl+k")])
    backend._sync(display, display.root, [_binding(combo="ctrl+q")])
    assert (24, CTRL) in display.root.grabbed
    assert (K_KEYCODE, CTRL) not in display.root.grabbed
    assert backend._registered["b1"][0] == "ctrl+q"


def test_a_binding_that_disappeared_is_ungrabbed(backend, display):
    backend._sync(display, display.root, [_binding()])
    backend._sync(display, display.root, [])
    assert display.root.grabbed == []
    assert backend._registered == {}


def test_an_unparseable_combo_is_logged_and_skipped(backend, display):
    backend._sync(display, display.root,
                  [_binding(combo="ctrl+mediaplay"), _binding("b2", "ctrl+k")])
    assert list(backend._registered) == ["b2"], "the good one still took"


def test_a_refused_grab_rolls_back_the_variants_that_took(backend, display):
    # X refuses per lock-variant, so a combo can be half-grabbed. Leaving
    # those held with `_registered` never updated leaks the grab and spams
    # BadAccess on every following poll.
    display.root.grab_errors[(K_KEYCODE, CTRL | ALT | CAPS_LOCK)] = (
        RuntimeError("BadAccess"))
    backend._sync(display, display.root, [_binding()])
    assert display.root.grabbed == []
    assert backend._registered == {}


def test_a_rollback_that_itself_fails_does_not_escape(backend, display):
    display.root.grab_errors[(K_KEYCODE, CTRL | ALT | NUM_LOCK)] = (
        RuntimeError("BadAccess"))
    display.root.ungrab_errors[(K_KEYCODE, CTRL | ALT)] = (
        RuntimeError("BadWindow"))
    backend._sync(display, display.root, [_binding()])
    assert backend._registered == {}


def test_an_ungrab_that_fails_is_not_fatal(backend, display):
    backend._sync(display, display.root, [_binding()])
    display.root.ungrab_errors[(K_KEYCODE, CTRL | ALT)] = (
        RuntimeError("BadWindow"))
    backend._sync(display, display.root, [])
    assert backend._registered == {}


def test_a_sync_flushes_the_grabs_to_the_server(backend, display):
    # X buffers requests; grabs that are never synced are grabs the server
    # has not made yet.
    before = display.syncs
    backend._sync(display, display.root, [_binding()])
    assert display.syncs > before


# --- matching an event back to a binding --------------------------------------

def _key_press(keycode=K_KEYCODE, state=CTRL | ALT):
    import types as _types
    return _types.SimpleNamespace(type=_X["KeyPress"], detail=keycode,
                                  state=state)


def test_a_matching_key_press_fires_its_binding(backend, display):
    backend._sync(display, display.root, [_binding()])
    display.events = [_key_press()]
    fired = []
    backend._drain(display, fired.append)
    assert fired == ["b1"]


@pytest.mark.parametrize("extra", [NUM_LOCK, CAPS_LOCK, NUM_LOCK | CAPS_LOCK])
def test_a_hotkey_fires_with_the_locks_on(backend, display, extra):
    backend._sync(display, display.root, [_binding()])
    display.events = [_key_press(state=CTRL | ALT | extra)]
    fired = []
    backend._drain(display, fired.append)
    assert fired == ["b1"]


def test_a_press_with_an_extra_modifier_does_not_fire(backend, display):
    # `ctrl+k` must not fire on `ctrl+shift+k`, or every binding shadows the
    # ones with more modifiers.
    backend._sync(display, display.root, [_binding(combo="ctrl+k")])
    display.events = [_key_press(state=CTRL | SHIFT)]
    fired = []
    backend._drain(display, fired.append)
    assert fired == []


def test_a_press_with_a_missing_modifier_does_not_fire(backend, display):
    backend._sync(display, display.root, [_binding()])
    display.events = [_key_press(state=CTRL)]
    fired = []
    backend._drain(display, fired.append)
    assert fired == []


def test_a_press_of_another_key_does_not_fire(backend, display):
    backend._sync(display, display.root, [_binding()])
    display.events = [_key_press(keycode=99)]
    fired = []
    backend._drain(display, fired.append)
    assert fired == []


def test_an_event_that_is_not_a_key_press_is_ignored(backend, display):
    import types as _types
    backend._sync(display, display.root, [_binding()])
    display.events = [_types.SimpleNamespace(type=99, detail=K_KEYCODE,
                                             state=CTRL | ALT)]
    fired = []
    backend._drain(display, fired.append)
    assert fired == []


def test_every_queued_event_is_drained_in_one_poll(backend, display):
    backend._sync(display, display.root, [_binding()])
    display.events = [_key_press(), _key_press(), _key_press()]
    fired = []
    backend._drain(display, fired.append)
    assert fired == ["b1", "b1", "b1"]
    assert display.pending_events() == 0


# --- the run loop -------------------------------------------------------------

def test_the_loop_asks_the_root_for_key_presses(backend, display):
    backend.run_forever(_context([_binding()]))
    assert display.root.attributes == {"event_mask": _X["KeyPressMask"]}


def test_the_loop_registers_polls_and_tears_down(backend, display):
    fired = []
    backend.run_forever(_context([_binding()], fired))
    assert display.root.grabs, "it grabbed while running"
    assert display.root.grabbed == [], "and released everything on the way out"
    assert backend._registered == {}
    assert display.closed is True


def test_the_loop_fires_a_hotkey_pressed_while_it_runs(backend, display):
    display.events = [_key_press()]
    fired = []
    backend.run_forever(_context([_binding()], fired))
    assert fired == ["b1"]


def test_a_session_with_no_display_gives_up_quietly(monkeypatch, backend):
    # Wayland, or a daemon started outside a session. There is nothing to
    # grab, and taking the daemon's thread down with an exception would take
    # every other binding with it.
    _xlib_stub.install(monkeypatch,
                       display_error=RuntimeError("no DISPLAY"))
    backend.run_forever(_context([_binding()]))
    assert backend._registered == {}


def test_a_teardown_ungrab_that_fails_does_not_escape(backend, display):
    # X11 ungrab races are non-fatal: the window can already be gone. The
    # daemon's thread is on its way out and must not raise there.
    backend._sync(display, display.root, [_binding()])
    display.root.ungrab_errors = {
        (K_KEYCODE, CTRL | ALT | extra): RuntimeError("BadWindow")
        for extra in _lock_mask_variants()
    }
    backend._ungrab_all(display, display.root)
    assert backend._registered == {}


def test_the_backend_names_the_protocol_it_uses(backend):
    assert backend.name == "linux-x11"
