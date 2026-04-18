"""Tests for Script Builder step model (de)serialisation."""
from je_auto_control.gui.script_builder.step_model import (
    actions_to_steps, steps_to_actions,
)


def test_flat_action_roundtrip():
    actions = [
        ["AC_click_mouse", {"mouse_keycode": "mouse_left", "x": 10, "y": 20}],
        ["AC_sleep", {"seconds": 0.5}],
    ]
    assert steps_to_actions(actions_to_steps(actions)) == actions


def test_nested_flow_roundtrip():
    actions = [
        ["AC_loop", {"times": 3, "body": [
            ["AC_type_keyboard", {"keycode": "a"}],
        ]}],
        ["AC_if_image_found", {"image": "x.png", "then": [
            ["AC_sleep", {"seconds": 1}],
        ], "else": [
            ["AC_break"],
        ]}],
    ]
    assert steps_to_actions(actions_to_steps(actions)) == actions


def test_step_label_includes_params():
    [step] = actions_to_steps([
        ["AC_click_mouse", {"mouse_keycode": "mouse_left", "x": 100}]
    ])
    assert "Click Mouse" in step.label
    assert "mouse_keycode=" in step.label


def test_no_params_serialises_to_name_only():
    actions = [["AC_break"]]
    assert steps_to_actions(actions_to_steps(actions)) == actions
