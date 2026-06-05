"""Tests for the non-destructive recording editor helpers."""
import pytest

from je_auto_control.utils.recording_edit.editor import (
    adjust_delays, dedupe_moves, filter_actions, insert_action,
    merge_sleeps, remove_action, scale_coordinates, trim_actions,
)


def _sample():
    return [
        ["AC_click_mouse", {"x": 100, "y": 200}],
        ["AC_sleep", {"seconds": 1.0}],
        ["AC_type_keyboard", {"keycode": "a"}],
        ["AC_sleep", {"seconds": 0.2}],
    ]


def test_trim_slices_returns_copy():
    actions = _sample()
    result = trim_actions(actions, 1, 3)
    assert len(result) == 2
    assert result[0][0] == "AC_sleep"
    result.append(["AC_noop"])
    assert len(actions) == 4


def test_insert_rejects_out_of_range():
    with pytest.raises(IndexError):
        insert_action(_sample(), 99, ["AC_noop"])


def test_remove_drops_index():
    result = remove_action(_sample(), 0)
    assert result[0][0] == "AC_sleep"


def test_filter_keeps_predicate_matches():
    result = filter_actions(_sample(),
                            lambda action: action[0] != "AC_sleep")
    assert [action[0] for action in result] == ["AC_click_mouse", "AC_type_keyboard"]


def test_adjust_delays_scales_and_clamps():
    result = adjust_delays(_sample(), factor=0.5, clamp_ms=300)
    # 1.0 * 0.5 = 0.5 (above clamp of 0.3)
    # 0.2 * 0.5 = 0.1 (clamped up to 0.3)
    assert result[1][1]["seconds"] == pytest.approx(0.5)
    assert result[3][1]["seconds"] == pytest.approx(0.3)


def test_scale_coordinates_multiplies_xy():
    result = scale_coordinates(_sample(), 2.0, 3.0)
    assert result[0][1] == {"x": 200, "y": 600}
    # non-coordinate actions untouched
    assert result[2] == ["AC_type_keyboard", {"keycode": "a"}]


def test_dedupe_moves_keeps_last_of_each_run():
    actions = [
        ["AC_set_mouse_position", {"x": 1, "y": 1}],
        ["AC_set_mouse_position", {"x": 2, "y": 2}],
        ["AC_set_mouse_position", {"x": 3, "y": 3}],
        ["AC_click_mouse", {"x": 3, "y": 3}],
        ["AC_set_mouse_position", {"x": 9, "y": 9}],
    ]
    result = dedupe_moves(actions)
    assert result == [
        ["AC_set_mouse_position", {"x": 3, "y": 3}],
        ["AC_click_mouse", {"x": 3, "y": 3}],
        ["AC_set_mouse_position", {"x": 9, "y": 9}],
    ]


def test_dedupe_moves_is_non_destructive():
    actions = [
        ["AC_set_mouse_position", {"x": 1, "y": 1}],
        ["AC_set_mouse_position", {"x": 2, "y": 2}],
    ]
    dedupe_moves(actions)
    assert len(actions) == 2


def test_dedupe_moves_no_moves_unchanged():
    actions = [["AC_click_mouse", {"x": 1, "y": 1}], ["AC_sleep", {"seconds": 1}]]
    assert dedupe_moves(actions) == actions


def test_dedupe_moves_custom_command_names():
    actions = [
        ["AC_mouse_move", {"x": 1, "y": 1}],
        ["AC_mouse_move", {"x": 5, "y": 5}],
    ]
    result = dedupe_moves(actions, move_commands=["AC_mouse_move"])
    assert result == [["AC_mouse_move", {"x": 5, "y": 5}]]


def test_merge_sleeps_sums_consecutive_runs():
    actions = [
        ["AC_sleep", {"seconds": 1.0}],
        ["AC_sleep", {"seconds": 0.5}],
        ["AC_click_mouse", {"x": 1, "y": 1}],
        ["AC_sleep", {"seconds": 0.2}],
        ["AC_sleep", {"seconds": 0.3}],
    ]
    result = merge_sleeps(actions)
    assert result == [
        ["AC_sleep", {"seconds": 1.5}],
        ["AC_click_mouse", {"x": 1, "y": 1}],
        ["AC_sleep", {"seconds": pytest.approx(0.5)}],
    ]


def test_merge_sleeps_non_destructive():
    actions = [["AC_sleep", {"seconds": 1.0}], ["AC_sleep", {"seconds": 2.0}]]
    merge_sleeps(actions)
    assert len(actions) == 2


def test_merge_sleeps_no_sleeps_unchanged():
    actions = [["AC_click_mouse", {"x": 1, "y": 1}]]
    assert merge_sleeps(actions) == actions
