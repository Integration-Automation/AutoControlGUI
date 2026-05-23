"""Phase 9.4: time-travel debugger tests."""
import json
from pathlib import Path

import pytest

from je_auto_control.utils.time_travel import (
    ActionEvent, FrameRef, TimelinePlayer, load_action_log, save_action_log,
)


def _write_manifest(directory: Path, frames: list) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    body = {"frame_count": len(frames), "entries": frames}
    (directory / "manifest.json").write_text(
        json.dumps(body, indent=2), encoding="utf-8",
    )
    for entry in frames:
        (directory / entry["filename"]).write_bytes(b"\xff\xd8\xff")  # fake JPEG


# --- ActionEvent / save_action_log ---------------------------------

def test_action_event_round_trip(tmp_path):
    events = [
        ActionEvent(timestamp=100.0, action_name="AC_click_mouse",
                    args={"button": "left"}, result="ok"),
        ActionEvent(timestamp=101.5, action_name="AC_type_keyboard",
                    args={"text": "hi"}, error=None),
    ]
    target = save_action_log(events, tmp_path / "actions.jsonl")
    assert target.exists()
    loaded = load_action_log(target)
    assert len(loaded) == 2
    assert loaded[0].action_name == "AC_click_mouse"
    assert loaded[1].args == {"text": "hi"}


def test_load_action_log_returns_empty_when_missing(tmp_path):
    assert load_action_log(tmp_path / "missing.jsonl") == []


def test_load_action_log_skips_invalid_lines(tmp_path):
    target = tmp_path / "actions.jsonl"
    target.write_text(
        '{"timestamp": 1.0, "action_name": "AC_x"}\n'
        'not-json-at-all\n'
        '{"timestamp": 2.0, "action_name": "AC_y"}\n',
        encoding="utf-8",
    )
    events = load_action_log(target)
    assert [e.action_name for e in events] == ["AC_x", "AC_y"]


# --- TimelinePlayer -----------------------------------------------

def test_player_empty_when_nothing_recorded(tmp_path):
    player = TimelinePlayer(tmp_path)
    assert player.frame_count == 0
    assert player.action_count == 0
    assert player.duration_s == pytest.approx(0.0)
    assert player.at_step(0).frame is None


def test_player_loads_frames_in_timestamp_order(tmp_path):
    _write_manifest(tmp_path, [
        {"filename": "b.jpg", "timestamp": 200.0, "size": 1},
        {"filename": "a.jpg", "timestamp": 100.0, "size": 1},
    ])
    player = TimelinePlayer(tmp_path)
    assert player.frame_count == 2
    # at_step 0 should be the earlier frame.
    snap = player.at_step(0)
    assert snap.frame.filename == "a.jpg"


def test_at_step_clamps_to_bounds(tmp_path):
    _write_manifest(tmp_path, [
        {"filename": "a.jpg", "timestamp": 100.0, "size": 1},
        {"filename": "b.jpg", "timestamp": 110.0, "size": 1},
    ])
    player = TimelinePlayer(tmp_path)
    # Negative index clamps to 0.
    assert player.at_step(-5).step == 0
    # Past-the-end clamps to last.
    assert player.at_step(999).frame.filename == "b.jpg"


def test_at_relative_time_picks_floor_frame(tmp_path):
    _write_manifest(tmp_path, [
        {"filename": "a.jpg", "timestamp": 100.0, "size": 1},
        {"filename": "b.jpg", "timestamp": 110.0, "size": 1},
        {"filename": "c.jpg", "timestamp": 120.0, "size": 1},
    ])
    player = TimelinePlayer(tmp_path)
    # Started_at = 100; relative=0 → a; relative=12 → b; relative=20 → c.
    assert player.at_relative_time(0).frame.filename == "a.jpg"
    assert player.at_relative_time(12).frame.filename == "b.jpg"
    assert player.at_relative_time(20).frame.filename == "c.jpg"
    # Negative time clamps to 0.
    assert player.at_relative_time(-100).frame.filename == "a.jpg"


def test_actions_window_joined_into_snapshot(tmp_path):
    _write_manifest(tmp_path, [
        {"filename": "a.jpg", "timestamp": 100.0, "size": 1},
        {"filename": "b.jpg", "timestamp": 110.0, "size": 1},
    ])
    save_action_log([
        ActionEvent(timestamp=105.0, action_name="AC_click_mouse"),
        ActionEvent(timestamp=108.0, action_name="AC_type_keyboard"),
        ActionEvent(timestamp=112.0, action_name="AC_screenshot"),
    ], tmp_path / "actions.jsonl")
    player = TimelinePlayer(tmp_path)
    snap = player.at_step(0)
    # The first frame's window covers [100, 110) — should pick the
    # two clicks but NOT the post-110 screenshot.
    names = [a.action_name for a in snap.actions]
    assert names == ["AC_click_mouse", "AC_type_keyboard"]
    # Relative time on the first frame is 0.
    assert snap.relative_time_s == pytest.approx(0.0)


def test_actions_in_window_explicit_range(tmp_path):
    save_action_log([
        ActionEvent(timestamp=10.0, action_name="A"),
        ActionEvent(timestamp=20.0, action_name="B"),
        ActionEvent(timestamp=30.0, action_name="C"),
    ], tmp_path / "actions.jsonl")
    _write_manifest(tmp_path, [
        {"filename": "x.jpg", "timestamp": 10.0, "size": 1},
    ])
    player = TimelinePlayer(tmp_path)
    in_window = player.actions_in_window(15.0, 25.0)
    assert [a.action_name for a in in_window] == ["B"]


def test_load_frame_bytes_returns_disk_content(tmp_path):
    _write_manifest(tmp_path, [
        {"filename": "a.jpg", "timestamp": 100.0, "size": 1},
    ])
    player = TimelinePlayer(tmp_path)
    snap = player.at_step(0)
    raw = player.load_frame_bytes(snap.frame)
    assert raw == b"\xff\xd8\xff"


def test_duration_spans_first_to_last_event(tmp_path):
    _write_manifest(tmp_path, [
        {"filename": "a.jpg", "timestamp": 100.0, "size": 1},
        {"filename": "b.jpg", "timestamp": 110.0, "size": 1},
    ])
    save_action_log([
        ActionEvent(timestamp=99.0, action_name="A"),
        ActionEvent(timestamp=120.0, action_name="B"),
    ], tmp_path / "actions.jsonl")
    player = TimelinePlayer(tmp_path)
    # started_at = min(frame 100, action 99) = 99
    # stopped_at = max(frame 110, action 120) = 120
    assert player.started_at == pytest.approx(99.0)
    assert player.stopped_at == pytest.approx(120.0)
    assert player.duration_s == pytest.approx(21.0)


def test_frame_ref_from_manifest_entry_handles_missing_fields():
    ref = FrameRef.from_manifest_entry({"filename": "x.jpg"})
    assert ref.filename == "x.jpg"
    assert ref.timestamp == pytest.approx(0.0)
    assert ref.size == 0


def test_save_action_log_empty_writes_empty_file(tmp_path):
    target = save_action_log([], tmp_path / "actions.jsonl")
    assert target.exists()
    assert target.read_text(encoding="utf-8") == ""
