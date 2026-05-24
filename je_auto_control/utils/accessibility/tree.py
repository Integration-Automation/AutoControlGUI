"""Recursive accessibility-tree dump types and helpers.

The existing :func:`list_accessibility_elements` returns a flat list of
elements; a tree dump preserves parent / child relationships so a
script can reason about hierarchy (e.g. "find the submit button
inside the login form"). Pure Python, JSON-serialisable, platform
agnostic — backends fill in the children list when they walk the OS
accessibility tree.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple


@dataclass
class AXTreeNode:
    """One node in a recursive accessibility tree dump."""

    name: str
    role: str
    bounds: Tuple[int, int, int, int]
    app_name: str = ""
    process_id: int = 0
    children: List["AXTreeNode"] = field(default_factory=list)
    attributes: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "name": self.name, "role": self.role,
            "bounds": list(self.bounds),
            "app_name": self.app_name,
            "process_id": int(self.process_id),
            "attributes": dict(self.attributes),
            "children": [child.to_dict() for child in self.children],
        }

    def walk(self) -> "AXTreeWalker":
        """Iterate every node in the tree depth-first."""
        return AXTreeWalker(self)

    def find_first(self, *, name: Optional[str] = None,
                    role: Optional[str] = None) -> Optional["AXTreeNode"]:
        """First node matching ``name`` and/or ``role``."""
        for node in self.walk():
            if name is not None and node.name != name:
                continue
            if role is not None and node.role != role:
                continue
            return node
        return None


class AXTreeWalker:
    """Lazy depth-first iterator over an :class:`AXTreeNode`."""

    def __init__(self, root: AXTreeNode) -> None:
        self._stack: List[AXTreeNode] = [root]

    def __iter__(self) -> "AXTreeWalker":
        return self

    def __next__(self) -> AXTreeNode:
        if not self._stack:
            raise StopIteration
        node = self._stack.pop()
        # Push children in reverse so they pop in original order.
        for child in reversed(node.children):
            self._stack.append(child)
        return node


def count_nodes(root: AXTreeNode) -> int:
    """Total number of nodes in a tree."""
    return sum(1 for _ in root.walk())


def max_depth(root: AXTreeNode) -> int:
    """Length of the longest root-to-leaf path."""
    if not root.children:
        return 1
    return 1 + max(max_depth(child) for child in root.children)


__all__ = [
    "AXTreeNode", "AXTreeWalker", "count_nodes", "max_depth",
]
