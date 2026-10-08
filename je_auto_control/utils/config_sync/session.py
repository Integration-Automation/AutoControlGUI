"""Run one config sync end to end: adapters -> outbox -> server -> adapters.

:func:`run_sync` is the whole cycle the GUI tab, the ``AC_config_sync_*``
commands and the MCP tools share:

1. each adapter's local changes become operations in the durable outbox;
2. the outbox is drained to the server (resent by operation id, bounded
   back-off, cancellable);
3. the merged state is applied back through the adapters -- which never
   enable a hotkey or trigger and never run a script;
4. the merged bucket becomes the new baseline, and the outcome is stored so
   the status can be shown without touching the network.

Pure standard library; imports no ``PySide6``.
"""
from __future__ import annotations

import os
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

from je_auto_control.utils.config_sync.adapters import (
    AddressBookSyncAdapter, HotkeySyncAdapter, LocatorSyncAdapter, ScriptSyncAdapter,
    SyncAdapter, TriggerSyncAdapter,
)
from je_auto_control.utils.config_sync.assets import (
    AssetManifest, AssetTransport, DirectoryAssetTransport, publish_assets, sync_assets,
)
from je_auto_control.utils.config_sync.client import (
    ConfigBucket, ConfigSyncClient, ConfigSyncError, FullResyncRequired, SyncResult,
)
from je_auto_control.utils.config_sync.device import default_device_id, default_device_id_path
from je_auto_control.utils.config_sync.outbox import DEFAULT_DRAIN_ATTEMPTS, SyncOutbox
from je_auto_control.utils.config_sync.versions import SyncOperation

STATE_SYNCED = "synced"
STATE_PENDING = "pending"
STATE_CONFLICT = "conflict"
STATE_OFFLINE = "offline"
STATE_CANCELLED = "cancelled"
STATE_RESYNC_REQUIRED = "resync_required"

#: Sections synced when the caller does not choose.
DEFAULT_SECTIONS = ("hotkeys", "triggers", "address_book")
_STATUS = "status"
_UNAPPLIED = "unapplied"
_OPTIONS = frozenset({
    "device_id", "secret", "sections", "scripts_dir", "locators_path", "outbox_path",
    "assets_dir", "timeout_s", "wait", "max_attempts",
})


@dataclass
class SyncRunReport:
    """How one sync ended, in the terms the status view shows.

    ``state`` is one of ``synced`` / ``pending`` / ``conflict`` / ``offline``
    / ``cancelled`` / ``resync_required``; ``revision`` the last revision
    merged from the server; ``pending`` the operations still queued;
    ``conflicts`` the ``section/key`` names waiting for a choice.
    """
    state: str = STATE_SYNCED
    revision: int = 0
    pending: int = 0
    conflicts: List[str] = field(default_factory=list)
    applied: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    withheld: Dict[str, str] = field(default_factory=dict)
    assets: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    finished_at: float = 0.0
    last_success: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """A JSON-ready copy."""
        return {"state": self.state, "revision": self.revision, "pending": self.pending,
                "conflicts": list(self.conflicts), "applied": dict(self.applied),
                "withheld": dict(self.withheld), "assets": dict(self.assets),
                "error": self.error, "finished_at": self.finished_at,
                "last_success": self.last_success}


def default_adapters(device_id: str, *, sections: Optional[Sequence[str]] = None,
                     scripts_dir: Optional[str] = None,
                     locators_path: Optional[str] = None) -> List[SyncAdapter]:
    """Adapters over this process's hotkey daemon, trigger engine and address book.

    ``scripts`` needs ``scripts_dir`` and ``locators`` needs ``locators_path``;
    naming a section whose store was not given, or an unknown section, is an
    error rather than a silent omission.
    """
    wanted = list(sections) if sections else [
        *DEFAULT_SECTIONS, *(["scripts"] if scripts_dir else []),
        *(["locators"] if locators_path else [])]
    return [_build_adapter(name, device_id, scripts_dir, locators_path) for name in wanted]


def _build_adapter(name: str, device_id: str, scripts_dir: Optional[str],
                   locators_path: Optional[str]) -> SyncAdapter:
    if name == "hotkeys":
        from je_auto_control.utils.hotkey.hotkey_daemon import default_hotkey_daemon
        return HotkeySyncAdapter(device_id, default_hotkey_daemon, scripts_dir=scripts_dir)
    if name == "triggers":
        from je_auto_control.utils.triggers.trigger_engine import default_trigger_engine
        return TriggerSyncAdapter(device_id, default_trigger_engine, scripts_dir=scripts_dir)
    if name == "address_book":
        from je_auto_control.utils.remote_desktop.address_book import default_address_book
        return AddressBookSyncAdapter(device_id, default_address_book())
    if name == "scripts" and scripts_dir:
        return ScriptSyncAdapter(device_id, scripts_dir)
    if name == "locators" and locators_path:
        from je_auto_control.utils.element_repository import ElementRepository
        return LocatorSyncAdapter(device_id, ElementRepository(locators_path))
    raise ConfigSyncError(
        f"cannot sync section {name!r}: unknown, or its scripts_dir / locators_path is missing")


def _conflict_names(bucket: ConfigBucket) -> List[str]:
    return [f"{section}/{entry.key}" for section, entry in bucket.conflicts()]


def _unapplied(outbox: SyncOutbox) -> Dict[str, List[str]]:
    stored = outbox.get_state(_UNAPPLIED)
    return stored if isinstance(stored, dict) else {}


def _stage(outbox: SyncOutbox, adapters: Sequence[SyncAdapter],
           baseline: ConfigBucket) -> Dict[str, str]:
    """Queue every adapter's local changes; returns what was withheld and why."""
    unapplied = _unapplied(outbox)
    withheld: Dict[str, str] = {}
    for adapter in adapters:
        adapter.rebase(baseline.sync_entries(adapter.section),
                       unapplied=unapplied.get(adapter.section, ()))
        for operation in adapter.pending_operations():
            outbox.enqueue(operation)
            baseline.put_entry(operation.section, operation.entry)
        for key, reason in getattr(adapter, "withheld", {}).items():
            withheld[f"{adapter.section}/{key}"] = reason
    # The baseline now includes the queued changes, so the next run does not
    # mint a second version of an edit that is merely waiting to be sent.
    outbox.save_baseline(baseline)
    return withheld


def _apply(outbox: SyncOutbox, adapters: Sequence[SyncAdapter], merged: ConfigBucket,
           report: SyncRunReport) -> None:
    unapplied: Dict[str, List[str]] = {}
    for adapter in adapters:
        applied = adapter.apply(merged.sync_entries(adapter.section))
        report.applied[adapter.section] = applied.to_dict()
        if applied.skipped:
            # Present in the bucket but not on this machine: the next snapshot
            # must not mistake that for a local deletion.
            unapplied[adapter.section] = sorted(applied.skipped)
    outbox.set_state(_UNAPPLIED, unapplied)
    outbox.save_baseline(merged)
    report.revision = merged.revision
    report.conflicts = _conflict_names(merged)


def _script_assets(adapters: Sequence[SyncAdapter], bucket: ConfigBucket,
                   ) -> Optional[AssetManifest]:
    """The scripts too large to travel in their entry, as an asset manifest."""
    for adapter in adapters:
        if isinstance(adapter, ScriptSyncAdapter):
            large = {key: value for key, value in bucket.values("scripts").items()
                     if "content" not in value}
            return AssetManifest.from_entries(adapter.root, large)
    return None


def _present(manifest: AssetManifest) -> AssetManifest:
    """The part of ``manifest`` this machine actually has on disk."""
    return AssetManifest(root=manifest.root, assets=tuple(
        asset for asset in manifest.assets if manifest.destination(asset).is_file()))


def _finish(outbox: SyncOutbox, report: SyncRunReport) -> SyncRunReport:
    previous = outbox.get_state(_STATUS)
    report.finished_at = time.time()
    report.pending = len(outbox.pending())
    earlier = previous.get("last_success", 0.0) if isinstance(previous, dict) else 0.0
    report.last_success = report.finished_at if report.state in (
        STATE_SYNCED, STATE_CONFLICT) else float(earlier or 0.0)
    outbox.set_state(_STATUS, report.to_dict())
    return report


def _exchange(client: ConfigSyncClient, outbox: SyncOutbox, device_id: str,
              cancel: Optional[threading.Event], wait: bool,
              max_attempts: int) -> Tuple[Optional[SyncResult], str, bool]:
    """Drain the outbox and pull; ``(result, error, cancelled)``."""
    results: List[SyncResult] = []

    def send(batch: List[SyncOperation]) -> None:
        results.append(client.push_operations(batch, device_id=device_id))

    drained = outbox.drain(send, cancel=cancel, wait=wait, max_attempts=max_attempts)
    if drained.cancelled or drained.offline:
        return None, drained.error, drained.cancelled
    if not results:
        try:
            results.append(client.push_operations([], device_id=device_id))
        except FullResyncRequired:
            raise
        except ConfigSyncError as error:
            return None, str(error), False
    return results[-1], "", False


def run_sync(client: ConfigSyncClient, outbox: SyncOutbox, adapters: Sequence[SyncAdapter], *,
             device_id: str, cancel: Optional[threading.Event] = None, wait: bool = False,
             max_attempts: int = DEFAULT_DRAIN_ATTEMPTS,
             asset_transport: Optional[AssetTransport] = None) -> SyncRunReport:
    """Sync once and report the outcome; see the module docstring for the steps.

    A failure to reach the server is not an exception: the changes stay in
    the outbox and the report says ``offline``. A device the group retired
    gets ``resync_required`` -- call :func:`run_full_resync`.
    """
    baseline = outbox.load_baseline() or ConfigBucket(user_id=client.user_id)
    report = SyncRunReport(revision=baseline.revision)
    report.withheld = _stage(outbox, adapters, baseline)
    manifest = _script_assets(adapters, baseline)
    if asset_transport is not None and manifest is not None:
        report.assets["published"] = publish_assets(
            _present(manifest), asset_transport, cancel=cancel).to_dict()
    try:
        result, error, cancelled = _exchange(client, outbox, device_id, cancel, wait, max_attempts)
    except FullResyncRequired as required:
        report.state, report.error = STATE_RESYNC_REQUIRED, str(required)
        return _finish(outbox, report)
    if result is None:
        report.state = STATE_CANCELLED if cancelled else STATE_OFFLINE
        report.error = error
        report.conflicts = _conflict_names(baseline)
        return _finish(outbox, report)
    incoming = _script_assets(adapters, result.bucket)
    if asset_transport is not None and incoming is not None:
        report.assets["received"] = sync_assets(incoming, asset_transport, cancel=cancel).to_dict()
    _apply(outbox, adapters, result.bucket, report)
    report.state = STATE_CONFLICT if report.conflicts else STATE_SYNCED
    return _finish(outbox, report)


def run_full_resync(client: ConfigSyncClient, outbox: SyncOutbox,
                    adapters: Sequence[SyncAdapter], *, device_id: str) -> SyncRunReport:
    """Re-admit a retired device: adopt the server's state, drop pending changes.

    The discarded operations are listed under ``withheld`` so nothing
    disappears without a trace. Items this machine never synced are kept and
    offered again by the next :func:`run_sync`.
    """
    baseline = outbox.load_baseline() or ConfigBucket(user_id=client.user_id)
    report = SyncRunReport(revision=baseline.revision)
    try:
        adopted = client.full_resync(device_id=device_id)
    except ConfigSyncError as error:
        report.state, report.error = STATE_OFFLINE, str(error)
        return _finish(outbox, report)
    for operation in outbox.clear():
        report.withheld[f"{operation.section}/{operation.entry.key}"] = (
            "discarded by the full resync: made against state the group has moved past")
    for adapter in adapters:
        adapter.rebase(baseline.sync_entries(adapter.section))
    _apply(outbox, adapters, adopted, report)
    report.state = STATE_CONFLICT if report.conflicts else STATE_SYNCED
    return _finish(outbox, report)


def _conflict_details(bucket: ConfigBucket) -> List[Dict[str, Any]]:
    """Each conflicted entry with its candidates, in the order ``choice`` counts."""
    return [{"section": section, "key": entry.key, "choices": [
        {"origin": sibling.origin, "deleted": sibling.deleted,
         "value": None if sibling.value is None else dict(sibling.value)}
        for sibling in entry.siblings]} for section, entry in bucket.conflicts()]


def sync_status(outbox: SyncOutbox) -> Dict[str, Any]:
    """The last recorded outcome plus the live queue length; no network.

    Read-only in full: asking about an account that never synced does not
    create its outbox database.
    """
    if not outbox.exists():
        return {**SyncRunReport(state="never").to_dict(), "conflict_details": []}
    stored = outbox.get_state(_STATUS)
    status = dict(stored) if isinstance(stored, dict) else SyncRunReport(state="never").to_dict()
    baseline = outbox.load_baseline()
    status["pending"] = len(outbox.pending())
    known = baseline if baseline is not None else ConfigBucket(user_id="")
    status["conflicts"] = _conflict_names(known)
    status["conflict_details"] = _conflict_details(known)
    status["revision"] = known.revision
    if status["pending"] and status["state"] == STATE_SYNCED:
        status["state"] = STATE_PENDING
    return status


def resolve_conflict(outbox: SyncOutbox, adapters: Sequence[SyncAdapter], *, device_id: str,
                     section: str, key: str, choice: int) -> Dict[str, Any]:
    """Settle a conflict by picking sibling number ``choice`` (0-based).

    The choice is applied to this machine and queued; the next
    :func:`run_sync` sends it, and it supersedes every candidate everywhere.
    """
    baseline = outbox.load_baseline() or ConfigBucket(user_id="")
    entry = baseline.get_entry(section, key)
    if entry is None or not entry.in_conflict:
        raise ConfigSyncError(f"{section}/{key} is not in conflict")
    if choice not in range(len(entry.siblings)) or isinstance(choice, bool):
        raise ConfigSyncError(f"choice must be 0..{len(entry.siblings) - 1}")
    picked = entry.siblings[choice]
    settled = entry.resolved(None if picked.deleted else picked.value, device_id,
                             modified_at=time.time())
    for adapter in adapters:
        if adapter.section == section:
            adapter.rebase(baseline.sync_entries(section))
            adapter.apply({**baseline.sync_entries(section), key: settled})
    outbox.enqueue(SyncOperation(section=section, entry=settled))
    baseline.put_entry(section, settled)
    outbox.save_baseline(baseline)
    return {"section": section, "key": key, "deleted": settled.deleted,
            "value": None if settled.value is None else dict(settled.value)}


# --- one-call entry points for the executor, MCP and the GUI -------------------

def _session(server_url: str, user_id: str, options: Mapping[str, Any],
             ) -> Tuple[ConfigSyncClient, SyncOutbox, List[SyncAdapter], str]:
    unknown = sorted(set(options) - _OPTIONS)
    if unknown:
        raise ConfigSyncError(f"unknown config sync option(s): {', '.join(unknown)}")
    chosen = {name: value for name, value in options.items() if value not in (None, "")}
    device_id = str(chosen.get("device_id") or default_device_id())
    client = ConfigSyncClient(
        server_url, user_id=user_id, timeout_s=float(chosen.get("timeout_s", 5.0)),
        device_id=device_id,
        secret=chosen.get("secret") or os.environ.get("AC_SIGNALING_SECRET") or None)
    outbox = SyncOutbox(chosen.get("outbox_path"), account=user_id, endpoint=client.server_url)
    sections = chosen.get("sections")
    if isinstance(sections, str):
        sections = [name.strip() for name in sections.split(",") if name.strip()]
    adapters = default_adapters(device_id, sections=sections,
                                scripts_dir=chosen.get("scripts_dir"),
                                locators_path=chosen.get("locators_path"))
    return client, outbox, adapters, device_id


def config_sync_run(server_url: str, user_id: str, *,
                    cancel: Optional[threading.Event] = None, **options: Any) -> Dict[str, Any]:
    """Sync this machine's settings with ``server_url`` once; returns the report.

    Options: ``device_id`` (default: this machine's stored id), ``secret``
    (default ``$AC_SIGNALING_SECRET``), ``sections``, ``scripts_dir``,
    ``locators_path``, ``outbox_path``, ``assets_dir`` (a folder both
    machines reach, for scripts too large to inline), ``timeout_s``,
    ``wait`` (sleep through a retry back-off instead of returning) and
    ``max_attempts``.
    """
    if cancel is not None and not isinstance(cancel, threading.Event):
        raise ConfigSyncError("cancel must be a threading.Event")
    client, outbox, adapters, device_id = _session(server_url, user_id, options)
    assets_dir = options.get("assets_dir")
    return run_sync(
        client, outbox, adapters, device_id=device_id, cancel=cancel,
        wait=bool(options.get("wait", False)),
        max_attempts=int(options.get("max_attempts") or DEFAULT_DRAIN_ATTEMPTS),
        asset_transport=DirectoryAssetTransport(assets_dir) if assets_dir else None).to_dict()


def config_sync_status(server_url: str, user_id: str,
                       outbox_path: Optional[str] = None) -> Dict[str, Any]:
    """The recorded sync state for this account and server; no network."""
    endpoint = str(server_url).rstrip("/")
    return sync_status(SyncOutbox(outbox_path or None, account=user_id, endpoint=endpoint))


def config_sync_full_resync(server_url: str, user_id: str, **options: Any) -> Dict[str, Any]:
    """Adopt the server's state after this device was retired; see :func:`run_full_resync`."""
    client, outbox, adapters, device_id = _session(server_url, user_id, options)
    return run_full_resync(client, outbox, adapters, device_id=device_id).to_dict()


def config_sync_resolve(server_url: str, user_id: str, section: str, key: str,
                        choice: int, **options: Any) -> Dict[str, Any]:
    """Pick one side of a conflict; see :func:`resolve_conflict`."""
    _client, outbox, adapters, device_id = _session(server_url, user_id, options)
    return resolve_conflict(outbox, adapters, device_id=device_id, section=section,
                            key=key, choice=choice)


__all__ = [
    "DEFAULT_SECTIONS", "STATE_CANCELLED", "STATE_CONFLICT", "STATE_OFFLINE", "STATE_PENDING",
    "STATE_RESYNC_REQUIRED", "STATE_SYNCED", "SyncRunReport", "config_sync_full_resync",
    "config_sync_resolve", "config_sync_run", "config_sync_status", "default_adapters",
    "default_device_id", "default_device_id_path", "resolve_conflict", "run_full_resync",
    "run_sync", "sync_status",
]
