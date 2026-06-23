"""Headless tests for form label/value association + checkbox state."""
import pytest

import je_auto_control as ac
from je_auto_control.utils.form_fields import (
    associate_fields, checkbox_state, match_labels_to_widgets,
)


def _box(x, y, text, w=60, h=20):
    return {"x": x, "y": y, "width": w, "height": h, "text": text}


def test_label_to_value_on_the_right():
    boxes = [_box(0, 0, "Name:"), _box(80, 0, "Ann")]
    fields = associate_fields(boxes)
    assert len(fields) == 1
    assert fields[0]["label"] == "Name"
    assert fields[0]["value"] == "Ann" and fields[0]["direction"] == "right"


def test_label_above_value_below():
    # value directly below the label, nothing to the right
    boxes = [_box(0, 0, "Email:"), _box(0, 40, "a@b.com")]
    fields = associate_fields(boxes, directions=("right", "below"))
    assert fields[0]["value"] == "a@b.com" and fields[0]["direction"] == "below"


def test_nearest_value_wins_and_gap_within_max():
    boxes = [_box(0, 0, "City:"), _box(70, 0, "Taipei"), _box(400, 0, "Far")]
    fields = associate_fields(boxes, max_gap=150)
    assert fields[0]["value"] == "Taipei"


def test_value_beyond_max_gap_unmatched():
    boxes = [_box(0, 0, "Lonely:"), _box(900, 0, "TooFar")]
    assert associate_fields(boxes, max_gap=150) == []


def test_match_labels_to_widgets_nearest():
    labels = [_box(0, 0, "Accept"), _box(0, 100, "Decline")]
    widgets = [_box(120, 0, "", w=16, h=16)]
    pairs = match_labels_to_widgets(labels, widgets)
    assert pairs[0]["label"] == "Accept"


def test_checkbox_state_from_fill():
    np = pytest.importorskip("numpy")
    image = np.full((40, 40), 255, dtype=np.uint8)   # white
    image[5:35, 5:35] = 0                            # dark fill inside the box
    box = {"x": 0, "y": 0, "width": 40, "height": 40}
    assert checkbox_state(image, box) == "checked"
    assert checkbox_state(np.full((40, 40), 255, np.uint8), box) == "unchecked"


# --- wiring ---------------------------------------------------------------

def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_associate_fields", "AC_match_labels_to_widgets"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_associate_fields", "ac_match_labels_to_widgets"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_associate_fields", "AC_match_labels_to_widgets"} <= specs


def test_facade_exports():
    for name in ("associate_fields", "match_labels_to_widgets", "checkbox_state"):
        assert hasattr(ac, name) and name in ac.__all__
