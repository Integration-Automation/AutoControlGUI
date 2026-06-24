"""Headless tests for the readable/addressable a11y-tree post-processing."""
import je_auto_control as ac
from je_auto_control.utils.accessibility.backends import base as backend_base
from je_auto_control.utils.accessibility.element import AccessibilityElement
from je_auto_control.utils.accessibility.tree import AXTreeNode
from je_auto_control.utils.ax_tree_walk import (
    assign_node_paths, control_type_name, find_by_path, humanize_role,
    humanize_tree,
)


def _tree() -> AXTreeNode:
    return AXTreeNode(
        name="root", role="AXRoot", bounds=(0, 0, 0, 0),
        children=[
            AXTreeNode(name="app", role="ControlType_50032", bounds=(0, 0, 4, 4),
                       children=[
                           AXTreeNode(name="OK", role="ControlType_50000",
                                      bounds=(1, 1, 2, 2)),
                           AXTreeNode(name="Name", role="ControlType_50004",
                                      bounds=(2, 2, 2, 2)),
                       ]),
        ],
    )


def test_control_type_name_known_and_unknown():
    assert control_type_name(50000) == "Button"
    assert control_type_name(50004) == "Edit"
    assert control_type_name(99999) == "ControlType_99999"


def test_humanize_role_forms():
    assert humanize_role(50000) == "Button"
    assert humanize_role("ControlType_50000") == "Button"
    assert humanize_role("50000") == "Button"
    assert humanize_role("Button") == "Button"          # already friendly
    assert humanize_role("AXApplication") == "AXApplication"  # non-UIA


def test_humanize_tree_is_a_deep_copy():
    root = _tree()
    out = humanize_tree(root)
    assert out.children[0].role == "Window"
    assert out.children[0].children[0].role == "Button"
    assert out.children[0].children[1].role == "Edit"
    assert root.children[0].role == "ControlType_50032"  # original untouched


def test_assign_node_paths_and_find_by_path():
    root = assign_node_paths(_tree())
    assert root.attributes["path"] == "0"
    assert root.children[0].attributes["path"] == "0.0"
    assert root.children[0].children[1].attributes["path"] == "0.0.1"
    node = find_by_path(root, "0.0.1")
    assert node is not None and node.name == "Name"
    assert find_by_path(root, "0.0.9") is None   # out of range
    assert find_by_path(root, "1.0") is None      # bad root


# --- wiring (executor path is CI-exercised via a fake backend) -------------

class _FakeBackend(backend_base.AccessibilityBackend):
    name = "fake"
    available = True

    def list_elements(self, app_name=None, max_results=200):
        return [AccessibilityElement(name="OK", role="ControlType_50000",
                                     bounds=(1, 1, 2, 2), app_name="demo.exe")]


def _inject(monkeypatch, backend):
    import je_auto_control.utils.accessibility.backends as backends
    monkeypatch.setattr(backends, "_cached_backend", backend, raising=False)


def test_walk_tree_executor_humanizes_and_paths(monkeypatch):
    _inject(monkeypatch, _FakeBackend())
    from je_auto_control.utils.executor.action_executor import _walk_tree
    out = _walk_tree(app_name="demo.exe")
    assert out["attributes"]["path"] == "0"
    button = out["children"][0]["children"][0]
    assert button["role"] == "Button"
    assert button["attributes"]["path"] == "0.0.0"


def test_humanize_role_executor():
    from je_auto_control.utils.executor.action_executor import _humanize_role
    assert _humanize_role("ControlType_50000") == {"role": "Button"}


def test_wiring():
    known = set(ac.executor.known_commands())
    assert {"AC_walk_tree", "AC_humanize_role"} <= known
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    names = {t.name for t in build_default_tool_registry()}
    assert {"ac_walk_tree", "ac_humanize_role"} <= names
    from je_auto_control.gui.script_builder.command_schema import _build_specs
    specs = {s.command for s in _build_specs()}
    assert {"AC_walk_tree", "AC_humanize_role"} <= specs


def test_facade_exports():
    for name in ("control_type_name", "humanize_role", "humanize_tree",
                 "assign_node_paths", "find_by_path"):
        assert hasattr(ac, name) and name in ac.__all__
