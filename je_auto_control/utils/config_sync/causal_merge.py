"""Deterministic causal frontiers retain concurrent values and compact deletion evidence."""
from __future__ import annotations

from collections import defaultdict
from typing import Iterable

from je_auto_control.utils.config_sync.causal_models import CausalNode, DeletionFence
from je_auto_control.utils.config_sync.contract import ConfigSyncError
from je_auto_control.utils.config_sync.versions import SyncEntry, dominates, merge_entries


def relation(left: CausalNode, right: CausalNode) -> str:
    """Compare one key without choosing between concurrent changes or restoring a collected payload."""
    if left.key != right.key:
        raise ConfigSyncError("cannot compare different causal entry keys")
    left.to_dict()
    right.to_dict()
    if isinstance(left, SyncEntry) and isinstance(right, SyncEntry):
        return merge_entries(left, right).relation
    if left.change_id == right.change_id:
        return _same_deletion(left, right)
    if (left.origin, left.operation_id) == (right.origin, right.operation_id):
        raise ConfigSyncError("a causal operation cannot identify different changes")
    if dominates(left.version, right.version):
        return "left"
    if dominates(right.version, left.version):
        return "right"
    return "conflict"


def _same_deletion(left: CausalNode, right: CausalNode) -> str:
    if isinstance(left, DeletionFence) and isinstance(right, DeletionFence):
        if left.deletion_revision != right.deletion_revision:
            raise ConfigSyncError("deletion fence revision changed")
        return "same"
    return "left" if isinstance(left, DeletionFence) else "right"


def frontier(nodes: Iterable[CausalNode]) -> tuple[CausalNode, ...]:
    """Keep all nondominated alternatives in stable order, with bounded per-key fanout."""
    grouped: dict[tuple[str, str], list[CausalNode]] = defaultdict(list)
    count = 0
    for node in nodes:
        if not isinstance(node, (SyncEntry, DeletionFence)):
            raise ConfigSyncError("causal frontier requires typed entries or deletion fences")
        node.to_dict()
        grouped[node.key].append(node)
        count += 1
        if count > 4096 or len(grouped[node.key]) > 256:
            raise ConfigSyncError("causal frontier capacity exceeded")
    kept = []
    for key in sorted(grouped):
        kept.extend(_key_frontier(grouped[key]))
    return tuple(kept)


def _key_frontier(nodes: list[CausalNode]) -> list[CausalNode]:
    # Compare every pair before discarding: an earlier dominated value must not hide an operation fork.
    excluded = set()
    for index, left in enumerate(nodes):
        for other in range(index + 1, len(nodes)):
            outcome = relation(left, nodes[other])
            if outcome in {"left", "same"}:
                excluded.add(other)
            elif outcome == "right":
                excluded.add(index)
    return sorted((node for index, node in enumerate(nodes) if index not in excluded),
                  key=lambda node: node.change_id)
