"""Tests for the trace-replay navigation controller."""
import json
from pathlib import Path

import pytest

from je_auto_control.utils.time_travel import (
    ReplayState, TimelinePlayer, TraceReplayController,
)


def _build_recording(tmp_path: Path) -> Path:
    """Create a tiny recording with 3 frames + 2 actions."""
    directory = tmp_path / "recording"
    directory.mkdir()
    manifest = {
        "entries": [
            {"timestamp": 100.0, "filename": "f0.jpg", "size": 1},
            {"timestamp": 101.0, "filename": "f1.jpg", "size": 1},
            {"timestamp": 102.0, "filename": "f2.jpg", "size": 1},
        ],
    }
    (directory / "manifest.json").write_text(
        json.dumps(manifest), encoding="utf-8",
    )
    # Two actions; one inside frame[0] window, one inside frame[1].
    actions = [
        {"timestamp": 100.5, "action_name": "AC_click_mouse", "args": {}},
        {"timestamp": 101.5, "action_name": "AC_screenshot", "args": {}},
    ]
    (directory / "actions.jsonl").write_text(
        "\n".join(json.dumps(a) for a in actions) + "\n",
        encoding="utf-8",
    )
    for name in ("f0.jpg", "f1.jpg", "f2.jpg"):
        (directory / name).write_bytes(b"x")
    return directory


# === navigation ==========================================================

def test_initial_step_is_zero(tmp_path):
    controller = TraceReplayController(
        TimelinePlayer(_build_recording(tmp_path)),
    )
    assert controller.step == 0
    state = controller.state()
    assert state.step == 0
    assert state.total_steps == 3


def test_step_forward_advances(tmp_path):
    controller = TraceReplayController(
        TimelinePlayer(_build_recording(tmp_path)),
    )
    controller.step_forward()
    assert controller.step == 1


def test_step_forward_clamps_at_end(tmp_path):
    controller = TraceReplayController(
        TimelinePlayer(_build_recording(tmp_path)),
    )
    for _ in range(10):
        controller.step_forward()
    assert controller.step == 2  # 3 frames → max index 2


def test_step_backward_clamps_at_zero(tmp_path):
    controller = TraceReplayController(
        TimelinePlayer(_build_recording(tmp_path)),
    )
    for _ in range(5):
        controller.step_backward()
    assert controller.step == 0


def test_jump_to_start_and_end(tmp_path):
    controller = TraceReplayController(
        TimelinePlayer(_build_recording(tmp_path)),
    )
    controller.seek(1)
    controller.jump_to_start()
    assert controller.step == 0
    controller.jump_to_end()
    assert controller.step == 2


def test_seek_clamps_negative_and_overflow(tmp_path):
    controller = TraceReplayController(
        TimelinePlayer(_build_recording(tmp_path)),
    )
    assert controller.seek(-5).step == 0
    assert controller.seek(99).step == 2


def test_seek_to_time_resolves_correct_frame(tmp_path):
    controller = TraceReplayController(
        TimelinePlayer(_build_recording(tmp_path)),
    )
    state = controller.seek_to_time(1.2)
    assert state.step == 1


def test_jump_to_action_seeks_to_owning_frame(tmp_path):
    controller = TraceReplayController(
        TimelinePlayer(_build_recording(tmp_path)),
    )
    state = controller.jump_to_action(1)
    assert state is not None
    assert state.step == 1


def test_jump_to_action_out_of_range_returns_none(tmp_path):
    controller = TraceReplayController(
        TimelinePlayer(_build_recording(tmp_path)),
    )
    assert controller.jump_to_action(99) is None


# === Rendered state ======================================================

def test_state_contains_frame_filename(tmp_path):
    controller = TraceReplayController(
        TimelinePlayer(_build_recording(tmp_path)),
    )
    state = controller.state()
    assert state.frame_filename == "f0.jpg"


def test_state_lists_actions_in_step_window(tmp_path):
    controller = TraceReplayController(
        TimelinePlayer(_build_recording(tmp_path)),
    )
    state = controller.state()
    names = [action["action_name"] for action in state.actions]
    assert "AC_click_mouse" in names


def test_state_step_two_has_no_actions(tmp_path):
    controller = TraceReplayController(
        TimelinePlayer(_build_recording(tmp_path)),
    )
    state = controller.seek(2)
    assert state.actions == []


def test_state_relative_time_is_zero_at_first_frame(tmp_path):
    controller = TraceReplayController(
        TimelinePlayer(_build_recording(tmp_path)),
    )
    assert controller.state().relative_time_s == pytest.approx(0.0)


def test_state_to_dict_round_trip(tmp_path):
    state = ReplayState(
        step=1, total_steps=3, relative_time_s=1.0,
        frame_filename="f1.jpg",
        actions=[{"action_name": "x"}],
    )
    data = state.to_dict()
    assert data["step"] == 1
    assert data["total_steps"] == 3
    assert data["frame_filename"] == "f1.jpg"


def test_action_index_returns_all_recorded_actions(tmp_path):
    controller = TraceReplayController(
        TimelinePlayer(_build_recording(tmp_path)),
    )
    actions = controller.action_index()
    assert len(actions) == 2


# === Empty recording ====================================================

def test_empty_recording_returns_zero_total(tmp_path):
    directory = tmp_path / "empty"
    directory.mkdir()
    controller = TraceReplayController(TimelinePlayer(directory))
    state = controller.state()
    assert state.total_steps == 0
    assert state.frame_filename is None


def test_empty_recording_step_forward_stays_at_zero(tmp_path):
    directory = tmp_path / "empty"
    directory.mkdir()
    controller = TraceReplayController(TimelinePlayer(directory))
    controller.step_forward()
    assert controller.step == 0


# === Facade =============================================================

def test_facade_exports_controller_and_state():
    from je_auto_control.utils import time_travel
    assert hasattr(time_travel, "TraceReplayController")
    assert hasattr(time_travel, "ReplayState")
