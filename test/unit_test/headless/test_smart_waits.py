"""Tests for the smart-wait helpers."""
import pytest

from je_auto_control.utils.smart_waits import (
    WaitOutcome, wait_until_pixel_changes, wait_until_region_idle,
    wait_until_screen_stable,
)
from je_auto_control.utils.smart_waits.waits import Frame


# === Frame fixtures =======================================================

def _frame_solid(width: int = 4, height: int = 4,
                  rgb: tuple = (0, 0, 0)) -> Frame:
    pixel = bytes(rgb)
    return Frame(width=width, height=height,
                  pixels=pixel * (width * height))


def _frame_with_single_diff(width: int = 4, height: int = 4) -> Frame:
    base = bytearray(b"\x00\x00\x00" * (width * height))
    base[0:3] = b"\xff\xff\xff"
    return Frame(width=width, height=height, pixels=bytes(base))


def _frames_in_order(*frames):
    """Return a sampler that yields each frame in turn, repeating the last."""
    buffer = list(frames)

    def sampler(_region):
        return buffer.pop(0) if len(buffer) > 1 else buffer[0]

    return sampler


# === wait_until_screen_stable ============================================

def test_screen_stable_returns_when_no_changes(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _s: None)
    sampler = _frames_in_order(_frame_solid(), _frame_solid(), _frame_solid())
    outcome = wait_until_screen_stable(
        timeout_s=2.0, poll_interval_s=0.01, stable_for_s=0.0,
        sampler=sampler,
    )
    assert isinstance(outcome, WaitOutcome)
    assert outcome.succeeded is True
    assert outcome.reason == "screen stable"


def test_screen_stable_returns_false_on_timeout(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _s: None)
    different = _frame_with_single_diff()
    sampler = _frames_in_order(_frame_solid(), different, _frame_solid())
    outcome = wait_until_screen_stable(
        timeout_s=0.05, poll_interval_s=0.01,
        stable_for_s=0.5, sampler=sampler,
    )
    assert outcome.succeeded is False
    assert "timeout" in outcome.reason


def test_screen_stable_validates_arguments():
    with pytest.raises(ValueError):
        wait_until_screen_stable(timeout_s=0.0, sampler=_frames_in_order(
            _frame_solid(),
        ))
    with pytest.raises(ValueError):
        wait_until_screen_stable(poll_interval_s=0.0, sampler=_frames_in_order(
            _frame_solid(),
        ))


def test_screen_stable_respects_max_pixel_diff(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _s: None)
    sampler = _frames_in_order(
        _frame_solid(), _frame_with_single_diff(), _frame_with_single_diff(),
    )
    outcome = wait_until_screen_stable(
        timeout_s=2.0, poll_interval_s=0.01, stable_for_s=0.0,
        max_pixel_diff=5, sampler=sampler,
    )
    assert outcome.succeeded is True


# === wait_until_pixel_changes ============================================

def test_pixel_changes_returns_when_pixel_differs(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _s: None)
    sampler = _frames_in_order(
        _frame_solid(), _frame_solid(), _frame_with_single_diff(),
    )
    outcome = wait_until_pixel_changes(
        x=0, y=0, timeout_s=2.0, poll_interval_s=0.01,
        rgb_tolerance=2, sampler=sampler,
    )
    assert outcome.succeeded is True


def test_pixel_changes_times_out_when_unchanged(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _s: None)
    sampler = _frames_in_order(_frame_solid())
    outcome = wait_until_pixel_changes(
        x=0, y=0, timeout_s=0.05, poll_interval_s=0.01,
        sampler=sampler,
    )
    assert outcome.succeeded is False


def test_pixel_changes_rejects_out_of_bounds():
    sampler = _frames_in_order(_frame_solid(width=4, height=4))
    with pytest.raises(ValueError):
        wait_until_pixel_changes(
            x=10, y=10, timeout_s=1.0, sampler=sampler,
        )


def test_pixel_changes_rejects_zero_timeout():
    with pytest.raises(ValueError):
        wait_until_pixel_changes(x=0, y=0, timeout_s=0,
                                   sampler=_frames_in_order(_frame_solid()))


# === wait_until_region_idle ==============================================

def test_region_idle_delegates_to_screen_stable(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda _s: None)
    sampler = _frames_in_order(_frame_solid(), _frame_solid())
    outcome = wait_until_region_idle(
        region=[0, 0, 10, 10], timeout_s=2.0, poll_interval_s=0.01,
        stable_for_s=0.0, sampler=sampler,
    )
    assert outcome.succeeded is True


def test_region_idle_rejects_invalid_region():
    sampler = _frames_in_order(_frame_solid())
    with pytest.raises(ValueError):
        wait_until_region_idle(
            region=[0, 0, 10], timeout_s=1.0, sampler=sampler,
        )


# === Outcome serialisation ==============================================

def test_outcome_to_dict_round_trips():
    outcome = WaitOutcome(succeeded=True, reason="x",
                           elapsed_s=0.05, samples_taken=3)
    data = outcome.to_dict()
    assert data == {
        "succeeded": True, "reason": "x",
        "elapsed_s": 0.05, "samples_taken": 3,
    }


# === Executor / MCP / facade ===========================================

def test_executor_registers_smart_wait_commands():
    from je_auto_control.utils.executor.action_executor import executor
    assert {
        "AC_wait_screen_stable", "AC_wait_pixel_changes",
        "AC_wait_region_idle",
    } <= executor.known_commands()


def test_mcp_factory_registers_smart_wait_tools():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {tool.name for tool in build_default_tool_registry()}
    assert {
        "ac_wait_screen_stable", "ac_wait_pixel_changes",
        "ac_wait_region_idle",
    } <= names


def test_facade_exports_smart_wait_api():
    import je_auto_control as ac
    for name in ("WaitOutcome", "wait_until_pixel_changes",
                  "wait_until_region_idle", "wait_until_screen_stable"):
        assert hasattr(ac, name)
