"""Headless tests for marks_layout (pure label placement + colour)."""
import je_auto_control as ac
from je_auto_control.utils.marks_layout import label_color, place_labels


def _rects_overlap(a, b):
    ax, ay, aw, ah = a
    bx, by, bw, bh = b
    return not (ax + aw <= bx or bx + bw <= ax
                or ay + ah <= by or by + bh <= ay)


# --- place_labels ---------------------------------------------------------

def test_place_labels_returns_one_per_mark():
    marks = [{"id": 1, "bbox": [100, 100, 40, 20]},
             {"id": 2, "bbox": [300, 300, 40, 20]}]
    labels = place_labels(marks)
    assert [item["id"] for item in labels] == [1, 2]
    assert all(len(item["label"]) == 4 for item in labels)


def test_place_labels_no_overlap_on_stacked_marks():
    # three marks at the exact same spot would collide if placed naively;
    # the candidate ring de-collides them
    marks = [{"id": i, "bbox": [200, 200, 30, 18]} for i in range(1, 4)]
    labels = place_labels(marks, bounds=[1920, 1080])
    boxes = [tuple(item["label"]) for item in labels]
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            assert not _rects_overlap(boxes[i], boxes[j])


def test_place_labels_stays_in_bounds():
    # a mark at the top-left corner can't put its label above the screen
    marks = [{"id": 1, "bbox": [0, 0, 40, 20]}]
    labels = place_labels(marks, label_width=22, label_height=16,
                          bounds=[800, 600])
    x, y, w, h = labels[0]["label"]
    assert x >= 0 and y >= 0
    assert x + w <= 800 and y + h <= 600


def test_place_labels_default_above_when_room():
    marks = [{"id": 1, "bbox": [100, 100, 40, 20]}]
    labels = place_labels(marks, label_height=16, bounds=[800, 600])
    # default candidate is directly above the box (y = 100 - 16 = 84)
    assert labels[0]["label"][1] == 84


def test_place_labels_empty():
    assert place_labels([]) == []


# --- label_color ----------------------------------------------------------

def test_label_color_white_on_dark():
    result = label_color((20, 20, 20))
    assert result["rgb"] == [255, 255, 255]
    assert result["contrast"] > 1.0


def test_label_color_black_on_light():
    result = label_color((240, 240, 240))
    assert result["rgb"] == [0, 0, 0]


# --- wiring ---------------------------------------------------------------

def test_executor_paths():
    from je_auto_control.utils.executor.action_executor import (
        _label_color, _place_labels,
    )
    out = _place_labels('[{"id": 1, "bbox": [10, 10, 30, 20]}]', 22, 16,
                        "[800, 600]")
    assert out["labels"][0]["id"] == 1
    assert _label_color([10, 10, 10])["rgb"] == [255, 255, 255]


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_place_labels", "AC_label_color"} <= known
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_place_labels", "ac_label_color"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_place_labels", "AC_label_color"} <= specs


def test_facade_exports():
    for name in ("place_labels", "label_color"):
        assert hasattr(ac, name) and name in ac.__all__
