"""The Windows hook has to record fractional wheel movement as whole notches.

``WM_MOUSEWHEEL`` carries the wheel delta in 1/120ths of a notch. A classic
wheel sends exactly 120 per detent, but a precision touchpad (and a
free-spinning wheel) sends fractions -- ``±30`` is typical. Replay scrolls whole
notches only, and the hook used to floor every event on its own:
``30 // 120 == 0`` and ``-30 // 120 == -1``. A touchpad recording therefore lost
every upward scroll and quadrupled every downward one.

No real input and no hook installation: ``_mouse_event`` is called directly with
a pointer to a struct we fill in ourselves.
"""
import ctypes
import sys

import pytest

if not sys.platform.startswith("win"):        # pragma: no cover
    pytest.skip("Windows recorder", allow_module_level=True)

from je_auto_control.windows.record import win32_input_hook as hook  # noqa: E402

_WM_MOUSEWHEEL = 0x020A


def _recorder():
    """A hook whose recorded events land in the returned list."""
    recorder = hook.Win32InputHook()
    captured = []
    recorder._put = captured.append
    return recorder, captured


def _wheel(recorder, raw, *, x=3, y=4):
    """Deliver one WM_MOUSEWHEEL with a wheel delta of ``raw``."""
    payload = hook._MSLLHOOKSTRUCT()
    payload.pt.x = x
    payload.pt.y = y
    payload.mouseData = (raw & 0xFFFF) << 16
    recorder._mouse_event(ctypes.addressof(payload), _WM_MOUSEWHEEL)


def _deltas(events):
    return [event["delta"] for event in events]


@pytest.mark.parametrize("raw, notches", [(120, 1), (-120, -1), (360, 3),
                                          (-240, -2)])
def test_a_whole_notch_is_recorded_at_once(raw, notches):
    recorder, events = _recorder()
    _wheel(recorder, raw)
    assert _deltas(events) == [notches]


@pytest.mark.parametrize("step, notch", [(30, 1), (-30, -1)])
def test_four_touchpad_quarters_make_exactly_one_notch(step, notch):
    """Both directions, because the old floor failed them in opposite ways."""
    recorder, events = _recorder()
    for _ in range(4):
        _wheel(recorder, step)
    assert _deltas(events) == [notch]


def test_a_single_fraction_records_nothing_yet():
    # Flooring made this -1: a quarter-notch down replayed as a full notch.
    recorder, events = _recorder()
    _wheel(recorder, -30)
    _wheel(recorder, 30 + 30)            # reversal: the -30 is dropped
    assert events == []


def test_the_notch_is_recorded_where_it_completed():
    recorder, events = _recorder()
    _wheel(recorder, 90, x=1, y=1)
    _wheel(recorder, 30, x=8, y=9)
    assert events == [{"op": "scroll", "delta": 1, "x": 8, "y": 9}]


def test_a_leftover_fraction_carries_into_the_next_notch():
    recorder, events = _recorder()
    for raw in (100, 100, 100):          # 300 = two notches + 60 left over
        _wheel(recorder, raw)
    _wheel(recorder, 60)                 # completes the third
    assert _deltas(events) == [1, 1, 1]


def test_reversing_direction_drops_the_pending_fraction():
    """A leftover upward fraction must not swallow a full notch down."""
    recorder, events = _recorder()
    _wheel(recorder, 90)
    _wheel(recorder, -120)
    assert _deltas(events) == [-1]


def test_every_hook_starts_with_no_remainder():
    first, _ = _recorder()
    _wheel(first, 90)
    second, events = _recorder()
    _wheel(second, 30)
    assert events == []
