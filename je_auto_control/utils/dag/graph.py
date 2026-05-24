"""DAG types: nodes, definition, topological ordering, cycle detection."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Set, Tuple


class DagDefinitionError(ValueError):
    """Raised when a DAG definition is malformed (cycles, dangling deps, …)."""


@dataclass(frozen=True)
class DagNode:
    """One unit of work in the DAG.

    Exactly one of ``actions`` / ``action_file`` must be set. ``host``
    selects the executor:

    * ``"local"`` — run via :func:`execute_action` in this process;
    * any other value — must match a registered :class:`AdminHost`
      label and gets dispatched via the admin console REST client.
    """

    id: str
    host: str = "local"
    actions: Optional[List[Any]] = None
    action_file: Optional[str] = None
    depends_on: Tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.id, str) or not self.id.strip():
            raise DagDefinitionError("node id must be a non-empty string")
        if not isinstance(self.host, str) or not self.host.strip():
            raise DagDefinitionError(
                f"node {self.id!r} requires a host string",
            )
        if self.actions is None and not self.action_file:
            raise DagDefinitionError(
                f"node {self.id!r} needs actions or action_file",
            )
        if self.actions is not None and self.action_file:
            raise DagDefinitionError(
                f"node {self.id!r} cannot set both actions and action_file",
            )


@dataclass(frozen=True)
class DagDefinition:
    """Validated graph of :class:`DagNode` plus a topo order helper."""

    nodes: Tuple[DagNode, ...]

    def __post_init__(self) -> None:
        ids = [node.id for node in self.nodes]
        if len(set(ids)) != len(ids):
            duplicates = sorted({n for n in ids if ids.count(n) > 1})
            raise DagDefinitionError(
                f"duplicate node id(s): {duplicates}",
            )
        known = set(ids)
        for node in self.nodes:
            for dep in node.depends_on:
                if dep not in known:
                    raise DagDefinitionError(
                        f"node {node.id!r} depends on unknown node {dep!r}",
                    )

    def by_id(self) -> Dict[str, DagNode]:
        return {node.id: node for node in self.nodes}

    def successors(self) -> Dict[str, Set[str]]:
        """Reverse edges: who depends on each node."""
        index: Dict[str, Set[str]] = {n.id: set() for n in self.nodes}
        for node in self.nodes:
            for dep in node.depends_on:
                index[dep].add(node.id)
        return index

    def topological_order(self) -> List[str]:
        """Return node ids in an order where deps come before dependants.

        Raises :class:`DagDefinitionError` if a cycle is detected.
        """
        nodes = self.by_id()
        unresolved: Dict[str, Set[str]] = {
            node.id: set(node.depends_on) for node in self.nodes
        }
        order: List[str] = []
        while unresolved:
            ready = sorted(nid for nid, deps in unresolved.items() if not deps)
            if not ready:
                raise DagDefinitionError(
                    f"DAG has a cycle among: {sorted(unresolved)}",
                )
            order.extend(ready)
            for nid in ready:
                unresolved.pop(nid)
            for deps in unresolved.values():
                deps.difference_update(ready)
        if len(order) != len(nodes):
            raise DagDefinitionError(
                "topological_order: node count drift "
                f"(expected {len(nodes)}, got {len(order)})",
            )
        return order


def parse_definition(data: Mapping[str, Any]) -> DagDefinition:
    """Build a :class:`DagDefinition` from a JSON-shaped mapping.

    The expected structure mirrors the JSON serialisation: ``{"nodes":
    [{"id": ..., "host": ..., "actions": [...] | "action_file": ...,
    "depends_on": [...]}, ...]}``.
    """
    if not isinstance(data, Mapping):
        raise DagDefinitionError("DAG definition must be a mapping")
    raw_nodes = data.get("nodes")
    if not isinstance(raw_nodes, list) or not raw_nodes:
        raise DagDefinitionError("DAG definition needs a non-empty 'nodes' list")
    nodes: List[DagNode] = []
    for raw in raw_nodes:
        if not isinstance(raw, Mapping):
            raise DagDefinitionError(f"node entry must be a mapping: {raw!r}")
        nodes.append(DagNode(
            id=str(raw.get("id", "")),
            host=str(raw.get("host", "local")),
            actions=_coerce_actions(raw.get("actions")),
            action_file=raw.get("action_file") or None,
            depends_on=_coerce_deps(raw.get("depends_on")),
        ))
    return DagDefinition(nodes=tuple(nodes))


def _coerce_actions(value: Any) -> Optional[List[Any]]:
    if value is None:
        return None
    if not isinstance(value, list):
        raise DagDefinitionError(
            f"'actions' must be a list, got {type(value).__name__}",
        )
    return list(value)


def _coerce_deps(value: Any) -> Tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise DagDefinitionError(
            "'depends_on' must be a list of node ids",
        )
    return tuple(str(item) for item in value)


__all__ = [
    "DagDefinition", "DagDefinitionError", "DagNode", "parse_definition",
]
