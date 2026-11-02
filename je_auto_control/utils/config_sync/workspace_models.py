"""Typed workspace outcomes and strict portable frontier validation precede any caching or prepared request."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, cast

from je_auto_control.utils.config_sync.adapter_schema import AdapterKind, KINDS
from je_auto_control.utils.config_sync.adapter_state import _validate_incoming
from je_auto_control.utils.config_sync.causal_models import DeletionFence
from je_auto_control.utils.config_sync.causal_state import CausalBucket
from je_auto_control.utils.config_sync.contract import ConfigSyncError, _identifier
from je_auto_control.utils.config_sync.versions import SyncEntry
from je_auto_control.utils.exception.exceptions import AutoControlException

WorkspaceState = Literal['ready', 'pending', 'offline', 'conflict', 'unresolved', 'requires_full_resync', 'invalid']


class SyncWorkspaceError(AutoControlException, RuntimeError):
    """A workspace safety boundary failed; transport retry must not turn it into an ordinary offline failure."""

    def __init__(self, message: str, *, code: str = 'workspace_error') -> None:
        _identifier(code, 'workspace error code')
        super().__init__(message)
        self.code = code


@dataclass(frozen=True)
class WorkspaceSyncResult:
    """Definition edit counts, pending work including controls, latest revision and inert profile readiness."""

    captured: int
    delivered: int
    pending: int
    revision: int
    conflicts: tuple[tuple[str, str], ...]
    unresolved: tuple[tuple[str, str], ...]
    state: WorkspaceState


def workspace_frontier(snapshot: CausalBucket, kind: AdapterKind) -> tuple[dict[str, SyncEntry], frozenset[str]]:
    """Project one validated causal section, retaining compacted deletion metadata without inventing payloads."""
    entries: dict[str, SyncEntry] = {}
    compacted: set[str] = set()
    for node in snapshot.nodes:
        if node.section != kind:
            continue
        if isinstance(node, DeletionFence):
            entry = SyncEntry(node.section, node.entry_id, {}, node.version, node.operation_id, node.origin, True)
            compacted.add(entry.change_id)
        else:
            entry = node
        entries[entry.change_id] = entry
    return entries, frozenset(compacted)


def validate_workspace_snapshot(snapshot: CausalBucket) -> None:
    """Reject unknown domains, raw recognized credentials and invalid native values before they reach durable state."""
    try:
        snapshot.to_dict()
        if any(node.section not in KINDS for node in snapshot.nodes):
            raise ConfigSyncError('unsupported workspace section')
        for name in KINDS:
            kind = cast(AdapterKind, name)
            entries, _compacted = workspace_frontier(snapshot, kind)
            _validate_incoming(kind, entries)
    except ConfigSyncError as error:
        raise SyncWorkspaceError('workspace snapshot violates portable domain validation',
                                 code='invalid_snapshot') from error
