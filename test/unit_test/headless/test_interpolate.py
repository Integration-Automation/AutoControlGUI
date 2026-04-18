"""Tests for ${var} interpolation in action lists."""
import pytest

from je_auto_control.utils.script_vars.interpolate import (
    interpolate_actions, interpolate_value,
)


def test_exact_placeholder_preserves_type():
    assert interpolate_value("${x}", {"x": 42}) == 42
    assert interpolate_value("${x}", {"x": [1, 2]}) == [1, 2]


def test_embedded_placeholder_coerces_to_string():
    assert interpolate_value("x=${x}!", {"x": 42}) == "x=42!"


def test_unknown_variable_raises():
    with pytest.raises(ValueError):
        interpolate_value("${missing}", {})


def test_nested_actions_interpolated():
    actions = [["AC_click_mouse", {"x": "${px}", "y": "${py}"}]]
    resolved = interpolate_actions(actions, {"px": 10, "py": 20})
    assert resolved == [["AC_click_mouse", {"x": 10, "y": 20}]]


def test_non_placeholder_passes_through():
    assert interpolate_value(123, {}) == 123
    assert interpolate_value("plain text", {}) == "plain text"
