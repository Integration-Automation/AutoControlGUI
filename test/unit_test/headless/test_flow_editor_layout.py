"""Headless tests for the visual flow editor layout algorithm."""
import pytest

from je_auto_control.gui.flow_editor.layout import (
    H_GAP, NODE_HEIGHT, NODE_WIDTH, V_GAP, layout_steps,
)
from je_auto_control.gui.script_builder.step_model import (
    Step, action_to_step,
)


def _flat(commands):
    return [Step(command=c) for c in commands]


# === flat lists ============================================================

def test_layout_empty_list_produces_empty_output():
    layout = layout_steps([])
    assert layout.nodes == []
    assert layout.edges == []
    assert layout.width == pytest.approx(0.0)
    assert layout.height == pytest.approx(0.0)


def test_layout_single_step_places_at_origin():
    layout = layout_steps([Step(command="AC_screenshot")])
    assert len(layout.nodes) == 1
    node = layout.nodes[0]
    assert (node.x, node.y) == (0.0, 0.0)
    assert node.width == NODE_WIDTH
    assert node.height == NODE_HEIGHT
    assert layout.width == NODE_WIDTH
    assert layout.height == NODE_HEIGHT


def test_layout_two_top_level_steps_stacked_vertically():
    layout = layout_steps(_flat(["AC_screenshot", "AC_click_mouse"]))
    assert len(layout.nodes) == 2
    first, second = layout.nodes
    assert first.y == pytest.approx(0.0)
    assert second.y == pytest.approx(first.y + NODE_HEIGHT + V_GAP)
    assert first.x == pytest.approx(0.0)
    assert second.x == pytest.approx(0.0)
    # No control-flow edges between sibling top-level nodes.
    assert layout.edges == []


def test_layout_paths_match_step_index_for_flat_list():
    layout = layout_steps(_flat(["AC_a", "AC_b", "AC_c"]))
    assert [n.path for n in layout.nodes] == [(0,), (1,), (2,)]


# === nested control flow ====================================================

def _build_loop_with_two_body_steps() -> Step:
    return Step(
        command="AC_loop",
        params={"count": 3},
        bodies={"body": _flat(["AC_screenshot", "AC_click_mouse"])},
    )


def test_loop_with_body_emits_edges_per_child():
    layout = layout_steps([_build_loop_with_two_body_steps()])
    body_edges = [e for e in layout.edges if e.body_key == "body"]
    assert len(body_edges) == 2
    sources = {e.source for e in body_edges}
    assert sources == {(0,)}
    targets = sorted(e.target for e in body_edges)
    assert targets == [(0, ("body", 0)), (0, ("body", 1))]


def test_loop_children_sit_right_of_parent():
    layout = layout_steps([_build_loop_with_two_body_steps()])
    by_path = layout.by_path()
    parent = by_path[(0,)]
    child0 = by_path[(0, ("body", 0))]
    assert child0.x == parent.x + NODE_WIDTH + H_GAP
    assert child0.y == parent.y


def test_loop_children_stacked_vertically():
    layout = layout_steps([_build_loop_with_two_body_steps()])
    by_path = layout.by_path()
    child0 = by_path[(0, ("body", 0))]
    child1 = by_path[(0, ("body", 1))]
    assert child1.y == child0.y + NODE_HEIGHT + V_GAP


def test_if_then_else_emits_two_branch_keys():
    if_step = Step(
        command="AC_if_image_found",
        params={"image": "x.png"},
        bodies={
            "then": [Step(command="AC_click_mouse")],
            "else": [Step(command="AC_press_keyboard_key")],
        },
    )
    layout = layout_steps([if_step])
    keys = {e.body_key for e in layout.edges}
    assert keys == {"then", "else"}


def test_layout_bounding_box_covers_nested_children():
    layout = layout_steps([_build_loop_with_two_body_steps()])
    assert layout.width == NODE_WIDTH * 2 + H_GAP
    assert layout.height >= NODE_HEIGHT * 2 + V_GAP


def test_layout_round_trips_action_json():
    actions = [
        ["AC_loop", {
            "count": 2,
            "body": [
                ["AC_screenshot", {"file_path": "x.png"}],
                ["AC_click_mouse", {"mouse_keycode": "mouse_left"}],
            ],
        }],
        ["AC_screenshot", {"file_path": "y.png"}],
    ]
    steps = [action_to_step(entry) for entry in actions]
    layout = layout_steps(steps)
    paths = [n.path for n in layout.nodes]
    assert (0,) in paths
    assert (0, ("body", 0)) in paths
    assert (0, ("body", 1)) in paths
    assert (1,) in paths


def test_layout_deterministic_for_same_input():
    steps = _flat(["AC_a", "AC_b"])
    a = layout_steps(steps)
    b = layout_steps(steps)
    assert [n.path for n in a.nodes] == [n.path for n in b.nodes]
    assert [(n.x, n.y) for n in a.nodes] == [(n.x, n.y) for n in b.nodes]


@pytest.mark.parametrize("body_key", ["body", "then", "else"])
def test_empty_body_branch_produces_no_edges(body_key):
    step = Step(
        command="AC_loop", params={"count": 1},
        bodies={body_key: []},
    )
    layout = layout_steps([step])
    assert layout.edges == []
    assert len(layout.nodes) == 1
