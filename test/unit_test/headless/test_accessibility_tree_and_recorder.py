"""Tests for the AXTreeNode dump + polling accessibility recorder."""
from unittest.mock import patch

import pytest

from je_auto_control.utils.accessibility import (
    AXRecorderEvent, AXTreeNode, AccessibilityRecorder,
    count_nodes, max_depth,
)
from je_auto_control.utils.accessibility.element import AccessibilityElement


# === AXTreeNode ===========================================================

def _node(name, role="x", children=None) -> AXTreeNode:
    return AXTreeNode(
        name=name, role=role, bounds=(0, 0, 10, 10),
        children=list(children or []),
    )


def test_walk_visits_every_node_depth_first():
    root = _node("a", children=[
        _node("b", children=[_node("d"), _node("e")]),
        _node("c"),
    ])
    names = [n.name for n in root.walk()]
    assert names == ["a", "b", "d", "e", "c"]


def test_count_nodes_includes_root():
    root = _node("a", children=[_node("b"), _node("c")])
    assert count_nodes(root) == 3


def test_max_depth_leaf_only_is_one():
    assert max_depth(_node("a")) == 1


def test_max_depth_nested_returns_path_length():
    root = _node("a", children=[
        _node("b", children=[_node("c", children=[_node("d")])]),
    ])
    assert max_depth(root) == 4


def test_find_first_returns_match_or_none():
    root = _node("a", children=[
        _node("b", role="button"), _node("c", role="text"),
    ])
    assert root.find_first(name="b").role == "button"
    assert root.find_first(name="missing") is None


def test_to_dict_serialises_children_recursively():
    root = _node("a", children=[_node("b")])
    data = root.to_dict()
    assert data["name"] == "a"
    assert data["children"][0]["name"] == "b"
    assert data["bounds"] == [0, 0, 10, 10]


# === dump_accessibility_tree ==============================================

def test_dump_groups_elements_by_app():
    from je_auto_control.utils.accessibility import (
        dump_accessibility_tree,
    )
    fakes = [
        AccessibilityElement(name="OK", role="AXButton",
                              bounds=(0, 0, 10, 10),
                              app_name="Finder", process_id=1),
        AccessibilityElement(name="Cancel", role="AXButton",
                              bounds=(0, 0, 10, 10),
                              app_name="Finder", process_id=1),
        AccessibilityElement(name="Send", role="AXButton",
                              bounds=(0, 0, 10, 10),
                              app_name="Mail", process_id=2),
    ]
    with patch(
        "je_auto_control.utils.accessibility.accessibility_api"
        ".list_accessibility_elements",
        return_value=fakes,
    ):
        tree = dump_accessibility_tree()
    assert tree.role == "AXRoot"
    app_names = sorted(child.name for child in tree.children)
    assert app_names == ["Finder", "Mail"]
    finder = next(c for c in tree.children if c.name == "Finder")
    assert {n.name for n in finder.children} == {"OK", "Cancel"}


def test_dump_handles_empty_element_list():
    from je_auto_control.utils.accessibility import (
        dump_accessibility_tree,
    )
    with patch(
        "je_auto_control.utils.accessibility.accessibility_api"
        ".list_accessibility_elements",
        return_value=[],
    ):
        tree = dump_accessibility_tree()
    assert tree.children == []


# === Recorder =============================================================

def _snapshot(name="OK", role="AXButton", bounds=(0, 0, 10, 10),
               app="Finder"):
    return {"name": name, "role": role, "bounds": bounds, "app_name": app}


def test_recorder_rejects_zero_poll():
    with pytest.raises(ValueError):
        AccessibilityRecorder(poll_interval_s=0.0)


def test_recorder_emits_focus_event_on_first_snapshot():
    sequence = iter([_snapshot()])
    recorder = AccessibilityRecorder(
        fetcher=lambda _app: next(sequence, None),
    )
    event = recorder.sample_once()
    assert event is not None
    assert event.kind == "focus"
    assert event.name == "OK"


def test_recorder_skips_event_when_snapshot_unchanged():
    recorder = AccessibilityRecorder(
        fetcher=lambda _app: _snapshot(),
    )
    first = recorder.sample_once()
    second = recorder.sample_once()
    assert first is not None
    assert second is None


def test_recorder_emits_focus_event_on_element_change():
    sequence = [_snapshot(name="OK"), _snapshot(name="Cancel")]
    iterator = iter(sequence)
    recorder = AccessibilityRecorder(
        fetcher=lambda _app: next(iterator, None),
    )
    recorder.sample_once()
    second = recorder.sample_once()
    assert second.kind == "focus"
    assert second.name == "Cancel"


def test_recorder_emits_bounds_event_when_moved_far():
    sequence = [
        _snapshot(bounds=(0, 0, 10, 10)),
        _snapshot(bounds=(100, 0, 10, 10)),
    ]
    iterator = iter(sequence)
    recorder = AccessibilityRecorder(
        fetcher=lambda _app: next(iterator, None),
        min_movement_px=20,
    )
    recorder.sample_once()
    second = recorder.sample_once()
    assert second.kind == "bounds"


def test_recorder_ignores_tiny_bounds_drift():
    sequence = [
        _snapshot(bounds=(0, 0, 10, 10)),
        _snapshot(bounds=(2, 2, 10, 10)),
    ]
    iterator = iter(sequence)
    recorder = AccessibilityRecorder(
        fetcher=lambda _app: next(iterator, None),
        min_movement_px=20,
    )
    recorder.sample_once()
    assert recorder.sample_once() is None


def test_recorder_emits_tree_changed_when_snapshot_disappears():
    sequence = [_snapshot(), None]
    iterator = iter(sequence)
    recorder = AccessibilityRecorder(
        fetcher=lambda _app: next(iterator, None),
    )
    recorder.sample_once()
    second = recorder.sample_once()
    assert second.kind == "tree_changed"


def test_recorder_event_to_dict_renders_bounds_as_list():
    event = AXRecorderEvent(
        timestamp_iso="t", kind="focus", role="AXButton",
        name="OK", bounds=(0, 0, 10, 10), app_name="Finder",
    )
    data = event.to_dict()
    assert data["bounds"] == [0, 0, 10, 10]


def test_recorder_clear_resets_events_and_previous():
    sequence = iter([_snapshot()])
    recorder = AccessibilityRecorder(
        fetcher=lambda _app: next(sequence, None),
    )
    recorder.sample_once()
    assert recorder.events()
    recorder.clear()
    assert recorder.events() == []


# === Executor / MCP / facade =============================================

def test_executor_registers_a11y_dump_and_recorder():
    from je_auto_control.utils.executor.action_executor import executor
    assert {
        "AC_a11y_dump", "AC_a11y_record_start",
        "AC_a11y_record_stop", "AC_a11y_record_events",
    } <= executor.known_commands()


def test_mcp_factory_registers_a11y_tools():
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry,
    )
    names = {tool.name for tool in build_default_tool_registry()}
    assert {"ac_a11y_dump", "ac_a11y_record_start",
             "ac_a11y_record_stop"} <= names


def test_facade_exports_a11y_tree_api():
    import je_auto_control as ac
    for name in ("AXTreeNode", "AXRecorderEvent",
                  "AccessibilityRecorder",
                  "dump_accessibility_tree"):
        assert hasattr(ac, name)
