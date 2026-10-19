"""Authoritative actor, membership, acknowledgement and causal frontier transitions."""
from __future__ import annotations

from dataclasses import replace
from typing import cast

from je_auto_control.utils.config_sync.causal_merge import relation
from je_auto_control.utils.config_sync.causal_models import CausalNode, DeletionFence, SyncActor
from je_auto_control.utils.config_sync.causal_state import CausalBucket
from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded
from je_auto_control.utils.config_sync.peers import FullResyncRequired, SyncPeers


def validate_transition(current: CausalBucket, candidate: CausalBucket, actor: SyncActor,
                        next_revision: int) -> CausalBucket:
    """Validate against the locked current snapshot and assign all new changes their server commit revision."""
    if candidate.user_id != current.user_id or candidate.revision != current.revision:
        raise ConfigSyncError("causal candidate must retain its account and exact base revision")
    _membership(current, candidate, actor)
    _frontier_transition(current, candidate, actor)
    nodes = candidate.nodes
    committed = {node.change_id: current.committed.get(node.change_id, next_revision) for node in nodes}
    for key, value in candidate.committed.items():
        if current.committed.get(key) != value:
            raise ConfigSyncError("clients cannot assign committed entry revisions")
    return replace(candidate, revision=next_revision, committed=committed)


def _membership(current: CausalBucket, candidate: CausalBucket, actor: SyncActor) -> None:
    expected = current.peers
    if actor.mode == "full_sync":
        _full_sync(expected, current.revision, actor)
    else:
        expected.require_active(actor.origin, epoch=actor.epoch)
        if actor.mode == "ack":
            if actor.revision is None or actor.revision > current.revision:
                raise ConfigSyncError("peer cannot acknowledge an unseen future revision")
            expected.acknowledge(actor.origin, actor.revision, epoch=actor.epoch)
        elif actor.mode == "retire":
            if actor.peer_id is None:
                raise ConfigSyncError("retirement requires a target")
            expected.retire(actor.peer_id)
    if _encoded(expected.to_dict()) != _encoded(candidate.peer_state):
        raise ConfigSyncError("candidate peer ledger does not match the authorized actor transition")


def _full_sync(peers: SyncPeers, revision: int, actor: SyncActor) -> None:
    if actor.revision != revision:
        raise ConfigSyncError("full sync must acknowledge the entire current snapshot")
    records = cast(list[dict[str, object]], peers.to_dict()["peers"])
    known = any(record["peer_id"] == actor.origin for record in records)
    record = peers.register(actor.origin, full_revision=revision, full_resync=known)
    if actor.epoch != record.epoch:
        raise FullResyncRequired("full sync must use the newly registered peer epoch")


def _frontier_transition(current: CausalBucket, candidate: CausalBucket, actor: SyncActor) -> None:
    if actor.mode == "collect":
        expected = current.collect()
        if _data(expected) != _data(candidate):
            raise ConfigSyncError("collection requires every active peer's committed acknowledgement")
        return
    if actor.mode != "edit":
        if _data(current) != _data(candidate):
            raise ConfigSyncError("membership and acknowledgement operations cannot change entry data")
        return
    old_nodes = current.nodes
    new_nodes = candidate.nodes
    _preserve_frontier(old_nodes, new_nodes)
    old_ids = {node.change_id: node for node in old_nodes}
    for node in new_nodes:
        if node.change_id in old_ids:
            if node.to_dict() != old_ids[node.change_id].to_dict():
                raise ConfigSyncError("existing causal change data cannot be replaced")
        else:
            _new_change(node, current, actor)


def _preserve_frontier(old_nodes: tuple[CausalNode, ...], new_nodes: tuple[CausalNode, ...]) -> None:
    by_key: dict[tuple[str, str], list[CausalNode]] = {}
    for node in new_nodes:
        by_key.setdefault(node.key, []).append(node)
    for old in old_nodes:
        alternatives = by_key.get(old.key, [])
        if not any(relation(old, new) in {"same", "right"} for new in alternatives):
            raise ConfigSyncError("causal commit cannot drop a retained alternative or deletion fence")


def _new_change(node: CausalNode, current: CausalBucket, actor: SyncActor) -> None:
    if isinstance(node, DeletionFence) or node.origin != actor.origin:
        raise ConfigSyncError("new entry changes require the active actor origin")
    observed = [old for old in current.nodes if old.key == node.key]
    floor = _observed_floor(node, observed)
    if node.version[node.origin] <= floor.get(node.origin, 0):
        raise ConfigSyncError("new entry must advance its origin counter")
    if any(counter > floor.get(origin, 0) for origin, counter in node.version.items() if origin != node.origin):
        raise ConfigSyncError("entry cannot claim unobserved versions from other origins")


def _observed_floor(node: CausalNode, observed: list[CausalNode]) -> dict[str, int]:
    floor: dict[str, int] = {}
    for old in observed:
        for origin, counter in old.version.items():
            floor[origin] = max(floor.get(origin, 0), counter)
        if old.origin == node.origin and old.operation_id == node.operation_id:
            raise ConfigSyncError("an entry operation cannot be reused for another change")
    return floor


def _data(state: CausalBucket) -> str:
    return _encoded({"entries": sorted((entry.to_dict() for entry in state.entries), key=_encoded),
                     "fences": sorted((fence.to_dict() for fence in state.fences), key=_encoded),
                     "committed": state.committed})
