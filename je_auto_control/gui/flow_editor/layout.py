"""Pure-Python layout algorithm for the visual flow editor.

Lives outside ``flow_editor/scene.py`` so it can be unit-tested
without Qt — the GUI scene just paints the rectangles this module
emits. Designed around the existing :class:`Step` model used by the
list-based script builder, so a JSON action file loads identically in
both views.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

from je_auto_control.gui.script_builder.step_model import Step


NODE_WIDTH = 220.0
NODE_HEIGHT = 70.0
H_GAP = 80.0
V_GAP = 30.0

# Path = tuple of (step_index | (body_key, child_index), ...)
NodePath = Tuple


@dataclass(frozen=True)
class FlowNodePosition:
    """One painted rectangle in the flow editor scene."""

    path: NodePath
    label: str
    command: str
    x: float
    y: float
    width: float = NODE_WIDTH
    height: float = NODE_HEIGHT

    def center(self) -> Tuple[float, float]:
        return self.x + self.width / 2.0, self.y + self.height / 2.0


@dataclass(frozen=True)
class FlowEdge:
    """One arrow between two nodes (parent → child of a body key)."""

    source: NodePath
    target: NodePath
    body_key: str = ""


@dataclass
class FlowLayout:
    """Aggregate output: positions, edges, and bounding box."""

    nodes: List[FlowNodePosition] = field(default_factory=list)
    edges: List[FlowEdge] = field(default_factory=list)
    width: float = 0.0
    height: float = 0.0

    def by_path(self) -> Dict[NodePath, FlowNodePosition]:
        return {node.path: node for node in self.nodes}


def layout_steps(steps: List[Step]) -> FlowLayout:
    """Return the rectangles + edges that paint ``steps`` as a tree.

    Top-level steps stack vertically on the left; children of a body
    key sit to the right of their parent, stacked vertically within
    that branch. The layout is deterministic so tests can assert exact
    positions.
    """
    layout = FlowLayout()
    next_y = 0.0
    for index, step in enumerate(steps):
        next_y = _layout_subtree(
            step=step, path=(index,), x=0.0, top=next_y, layout=layout,
        )
        next_y += V_GAP
    if layout.nodes:
        layout.width = max(node.x + node.width for node in layout.nodes)
        layout.height = max(node.y + node.height for node in layout.nodes)
    return layout


def _layout_subtree(*, step: Step, path: NodePath, x: float,
                    top: float, layout: FlowLayout) -> float:
    """Place ``step`` then its body children. Returns the next free y."""
    node = FlowNodePosition(
        path=path, label=step.label, command=step.command,
        x=x, y=top, width=NODE_WIDTH, height=NODE_HEIGHT,
    )
    layout.nodes.append(node)
    bottom = top + NODE_HEIGHT
    child_x = x + NODE_WIDTH + H_GAP
    for body_key, children in step.bodies.items():
        if not children:
            continue
        bottom = _layout_body(
            parent_path=path, body_key=body_key, children=children,
            x=child_x, top=top, layout=layout,
        )
        top = bottom + V_GAP
    return max(bottom, top)


def _layout_body(*, parent_path: NodePath, body_key: str,
                 children: List[Step], x: float, top: float,
                 layout: FlowLayout) -> float:
    """Place every child of a body branch; emit one edge per child."""
    next_y = top
    for child_index, child in enumerate(children):
        child_path = parent_path + ((body_key, child_index),)
        next_y = _layout_subtree(
            step=child, path=child_path, x=x, top=next_y, layout=layout,
        )
        layout.edges.append(FlowEdge(
            source=parent_path, target=child_path, body_key=body_key,
        ))
        next_y += V_GAP
    return next_y - V_GAP


__all__ = [
    "FlowEdge", "FlowLayout", "FlowNodePosition", "H_GAP",
    "NODE_HEIGHT", "NODE_WIDTH", "V_GAP", "layout_steps",
]
