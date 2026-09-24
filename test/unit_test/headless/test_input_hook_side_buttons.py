"""The Windows hook has to record mouse side buttons (x1 / x2).

Playback has supported ``mouse_x1`` / ``mouse_x2`` all along, but the recorder's
``_MOUSE_BUTTONS`` table is keyed by message id and ``WM_XBUTTONDOWN`` /
``WM_XBUTTONUP`` are a *single* message id for *both* buttons -- the button is in
the high word of ``mouseData``, exactly like the wheel's notch count. So the
table could not express them and side clicks were dropped silently: the macro
replayed without them and nothing said why.

The second half of the fix matters more than the first. ``_RECORDED_BUTTON``
falls back to ``mouse_left`` for an unknown name, so teaching the hook to emit
``x1`` *without* teaching the replay map about it would turn a side click into a
real left click -- a worse bug than the one being fixed. Both directions are
pinned here.

No real input and no hook installation: ``_mouse_event`` is called directly with
a pointer to a struct we fill in ourselves.
"""
import ctypes
import sys

import pytest

if not sys.platform.startswith("win"):        # pragma: no cover
    pytest.skip("Windows recorder", allow_module_level=True)

from je_auto_control.utils.input_macro.input_macro import (  # noqa: E402
    _RECORDED_BUTTON,
)
from je_auto_control.windows.record import win32_input_hook as hook  # noqa: E402

_WM_XBUTTONDOWN = 0x020B
_WM_XBUTTONUP = 0x020C
_XBUTTON1_HI = 0x0001
_XBUTTON2_HI = 0x0002


def _fire(message, mouse_data, *, x=11, y=22):
    """Call `_mouse_event` with a struct we control; return what it queued."""
    recorder = hook.Win32InputHook()
    captured = []
    recorder._put = captured.append
    payload = hook._MSLLHOOKSTRUCT()
    payload.pt.x = x
    payload.pt.y = y
    payload.mouseData = mouse_data
    recorder._mouse_event(ctypes.addressof(payload), message)
    return captured


@pytest.mark.parametrize("hi, name", [(_XBUTTON1_HI, "x1"),
                                      (_XBUTTON2_HI, "x2")])
def test_a_side_button_press_is_recorded(hi, name):
    events = _fire(_WM_XBUTTONDOWN, hi << 16)
    assert events == [{"op": "mouse_down", "button": name, "x": 11, "y": 22}]


@pytest.mark.parametrize("hi, name", [(_XBUTTON1_HI, "x1"),
                                      (_XBUTTON2_HI, "x2")])
def test_a_side_button_release_is_recorded(hi, name):
    # Without the release a replay cannot tell a held side button from a click.
    events = _fire(_WM_XBUTTONUP, hi << 16)
    assert events == [{"op": "mouse_up", "button": name, "x": 11, "y": 22}]


def test_the_two_side_buttons_are_told_apart():
    """One message id covers both, so the high word is the only discriminator.

    A mutation that ignores ``mouseData`` still passes every single-button test
    above by always answering ``x1``; this one is what catches it.
    """
    down_1 = _fire(_WM_XBUTTONDOWN, _XBUTTON1_HI << 16)[0]["button"]
    down_2 = _fire(_WM_XBUTTONDOWN, _XBUTTON2_HI << 16)[0]["button"]
    assert down_1 != down_2, "both side buttons recorded as the same name"


def test_an_unknown_side_button_is_dropped_not_guessed():
    """Guessing is worse than dropping: the replay map falls back to LEFT.

    A value we do not recognise must produce no event at all, so an odd mouse
    driver cannot turn into a real left click somewhere else on the screen.
    """
    assert _fire(_WM_XBUTTONDOWN, 0x0009 << 16) == []


def test_the_low_word_of_mousedata_is_not_mistaken_for_the_button():
    """The button is in the HIGH word. Reading the low word finds keyboard
    modifier flags (``MK_XBUTTON1`` is 0x0020) and would answer for the wrong
    reason -- or answer at all when no side button is involved.
    """
    assert _fire(_WM_XBUTTONDOWN, _XBUTTON1_HI) == []


def test_the_ordinary_buttons_still_work():
    """Positive control: refusing everything would pass the "dropped" tests."""
    events = _fire(0x0201, 0)
    assert events == [{"op": "mouse_down", "button": "left",
                       "x": 11, "y": 22}]


def test_every_recorded_button_name_has_a_replay_mapping():
    """The reconciliation that makes the fix safe.

    ``_sink_mouse_down`` does ``_RECORDED_BUTTON.get(name, "mouse_left")``, so a
    name the hook can emit but the map does not know replays as a LEFT click --
    silently, at whatever coordinates the side click happened. Both tables have
    to move together.
    """
    emitted = {name for _, name in hook._MOUSE_BUTTONS.values()}
    emitted |= set(hook._XBUTTON_NAMES.values())
    # Positive control: an empty extraction would make the check below vacuous.
    assert len(emitted) >= 5, f"only extracted {sorted(emitted)}"
    missing = sorted(emitted - set(_RECORDED_BUTTON))
    assert not missing, (
        f"the hook can emit {missing} but _RECORDED_BUTTON has no entry, so "
        "replay would fall back to mouse_left and click the WRONG button")


def test_every_replay_mapping_names_a_real_mouse_button():
    """The other direction: a typo'd table value fails only at replay time."""
    from je_auto_control.wrapper.auto_control_mouse import get_mouse_table

    table = get_mouse_table()
    assert len(table) >= 5, f"mouse table looks wrong: {sorted(table)}"
    unknown = sorted(set(_RECORDED_BUTTON.values()) - set(table))
    assert not unknown, f"_RECORDED_BUTTON points at non-existent buttons: {unknown}"
