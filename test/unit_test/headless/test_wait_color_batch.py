"""Headless tests for region-colour waits. No Qt."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.smart_waits import (
    Frame, WaitOutcome, wait_until_color,
)


def _frame(color, count, *, other=(0, 0, 0), other_count=0):
    """Build a 1-row Frame: ``count`` px of ``color`` then ``other_count`` of other."""
    pixels = bytes(list(color) * count + list(other) * other_count)
    return Frame(width=count + other_count, height=1, pixels=pixels)


def test_succeeds_when_colour_reaches_fraction():
    green = _frame((0, 200, 0), 8, other=(0, 0, 0), other_count=2)   # 80% green
    outcome = wait_until_color(
        target_rgb=(0, 200, 0), tolerance=10, min_fraction=0.5, present=True,
        timeout_s=1.0, poll_interval_s=0.001, sampler=lambda region: green)
    assert isinstance(outcome, WaitOutcome) and outcome.succeeded is True


def test_times_out_when_colour_absent():
    blank = _frame((0, 0, 0), 10)
    outcome = wait_until_color(
        target_rgb=(255, 0, 0), min_fraction=0.5, present=True,
        timeout_s=0.03, poll_interval_s=0.001, sampler=lambda region: blank)
    assert outcome.succeeded is False and "timeout" in outcome.reason


def test_vanish_succeeds_when_below_fraction():
    blank = _frame((0, 0, 0), 10)
    outcome = wait_until_color(
        target_rgb=(255, 0, 0), min_fraction=0.5, present=False,
        timeout_s=1.0, poll_interval_s=0.001, sampler=lambda region: blank)
    assert outcome.succeeded is True             # colour absent -> "gone" met


def test_tolerance_band():
    near = _frame((5, 198, 3), 10)               # all near (0,200,0)
    outcome = wait_until_color(
        target_rgb=(0, 200, 0), tolerance=10, min_fraction=1.0, present=True,
        timeout_s=1.0, poll_interval_s=0.001, sampler=lambda region: near)
    assert outcome.succeeded is True


def test_validation():
    for bad in ({"timeout_s": 0}, {"poll_interval_s": 0}):
        try:
            wait_until_color(target_rgb=(0, 0, 0), **bad)
        except ValueError:
            pass
        else:                                    # pragma: no cover
            raise AssertionError("expected ValueError")


# --- wiring ---------------------------------------------------------------

def test_executor_color_fraction_helper():
    # the adapter's screen dispatch is device-bound; exercise the pure pixel-
    # counting helper the wait relies on instead.
    from je_auto_control.utils.smart_waits.waits import _color_fraction
    half = _frame((0, 200, 0), 5, other=(0, 0, 0), other_count=5)
    assert _color_fraction(half, (0, 200, 0), 10) == pytest.approx(0.5)
    assert _color_fraction(half, (255, 255, 255), 10) == pytest.approx(0.0)


def test_wiring():
    known = ac.executor.known_commands()
    assert "AC_wait_color" in set(known)
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert "ac_wait_color" in names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert "AC_wait_color" in specs


def test_facade_exports():
    assert hasattr(ac, "wait_until_color") and "wait_until_color" in ac.__all__
