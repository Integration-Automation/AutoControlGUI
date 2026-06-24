"""Make an accessibility-tree dump readable and addressable.

``dump_accessibility_tree`` emits nodes with the platform's *raw* role —
on Windows that is the bare UI Automation ControlType id, e.g.
``"ControlType_50000"`` for a button. That is unreadable, and the dump
carries no stable per-node identity (UIA RuntimeId needs the live element,
which a serialised dump has thrown away). ``ax_tree_walk`` adds the pure,
platform-agnostic post-processing the dump lacks:

* :func:`control_type_name` / :func:`humanize_role` — translate a UIA
  ControlType id (or ``"ControlType_NNNNN"`` string) to a friendly name,
* :func:`humanize_tree` — a deep copy of the tree with every role humanised,
* :func:`assign_node_paths` — a deep copy stamping each node with a stable
  positional ``path`` (``"0.2.1"``) — a pure stand-in for RuntimeId identity,
* :func:`find_by_path` — resolve a node back from its path.

Pure-stdlib over :class:`AXTreeNode` values; no device or backend access, no
``PySide6``. Compose it on top of any ``dump_accessibility_tree`` output.
"""
from typing import Optional, Union

from je_auto_control.utils.accessibility.tree import AXTreeNode

# UIA ControlType ids → friendly names (UIAutomationClient ControlTypeId range).
_CONTROL_TYPE_NAMES = {
    50000: "Button", 50001: "Calendar", 50002: "CheckBox", 50003: "ComboBox",
    50004: "Edit", 50005: "Hyperlink", 50006: "Image", 50007: "ListItem",
    50008: "List", 50009: "Menu", 50010: "MenuBar", 50011: "MenuItem",
    50012: "ProgressBar", 50013: "RadioButton", 50014: "ScrollBar",
    50015: "Slider", 50016: "Spinner", 50017: "StatusBar", 50018: "Tab",
    50019: "TabItem", 50020: "Text", 50021: "ToolBar", 50022: "ToolTip",
    50023: "Tree", 50024: "TreeItem", 50025: "Custom", 50026: "Group",
    50027: "Thumb", 50028: "DataGrid", 50029: "DataItem", 50030: "Document",
    50031: "SplitButton", 50032: "Window", 50033: "Pane", 50034: "Header",
    50035: "HeaderItem", 50036: "Table", 50037: "TitleBar", 50038: "Separator",
    50039: "SemanticZoom", 50040: "AppBar",
}
_ROLE_PREFIX = "ControlType_"


def control_type_name(control_type: int) -> str:
    """Return the friendly name for a UIA ControlType id (e.g. ``50000`` → ``Button``).

    Unknown ids fall back to ``"ControlType_<id>"`` so nothing is lost.
    """
    cid = int(control_type)
    return _CONTROL_TYPE_NAMES.get(cid, f"{_ROLE_PREFIX}{cid}")


def humanize_role(role: Union[str, int]) -> str:
    """Map a raw UIA role to a friendly name.

    Accepts an int id (``50000``), a ``"ControlType_50000"`` string, or a bare
    ``"50000"`` string. Any role that is not a recognised ControlType — already
    friendly (``"Button"``) or a non-UIA role (``"AXApplication"``) — is returned
    unchanged.
    """
    if isinstance(role, int):
        return control_type_name(role)
    text = str(role)
    digits = text[len(_ROLE_PREFIX):] if text.startswith(_ROLE_PREFIX) else text
    if digits.isdigit():
        return control_type_name(int(digits))
    return text


def humanize_tree(node: AXTreeNode) -> AXTreeNode:
    """Return a deep copy of ``node`` with every role run through :func:`humanize_role`."""
    return AXTreeNode(
        name=node.name, role=humanize_role(node.role), bounds=node.bounds,
        app_name=node.app_name, process_id=node.process_id,
        attributes=dict(node.attributes),
        children=[humanize_tree(child) for child in node.children],
    )


def assign_node_paths(node: AXTreeNode, prefix: str = "0") -> AXTreeNode:
    """Return a deep copy stamping each node with a stable positional ``path``.

    The root is ``"0"``; its third child is ``"0.2"``, and so on. The path is a
    pure stand-in for a RuntimeId: stable for a given tree shape and re-resolvable
    with :func:`find_by_path`. Stored under ``attributes["path"]``.
    """
    attributes = dict(node.attributes)
    attributes["path"] = prefix
    children = [assign_node_paths(child, f"{prefix}.{index}")
                for index, child in enumerate(node.children)]
    return AXTreeNode(
        name=node.name, role=node.role, bounds=node.bounds,
        app_name=node.app_name, process_id=node.process_id,
        attributes=attributes, children=children,
    )


def find_by_path(root: AXTreeNode, path: str) -> Optional[AXTreeNode]:
    """Resolve the node addressed by ``path`` (e.g. ``"0.2.1"``); ``None`` if absent."""
    parts = str(path).split(".")
    if not parts or parts[0] != "0":
        return None
    node = root
    for part in parts[1:]:
        if not part.isdigit():
            return None
        index = int(part)
        if index >= len(node.children):
            return None
        node = node.children[index]
    return node
