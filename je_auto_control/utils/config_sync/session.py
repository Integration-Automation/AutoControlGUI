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
    AssetManifest, AssetTransport, DirectoryAssetTransport, HttpAssetTransport,
    publish_assets, sync_assets,
)
from je_auto_control.utils.config_sync.client import (
    ConfigBucket, ConfigSyncClient, ConfigSyncError, FullResyncRequired, SyncResult,
)
from je_auto_control.utils.config_sync.device import default_device_id, default_device_id_path
from je_auto_control.utils.config_sync.outbox import (
    DEFAULT_DRAIN_ATTEMPTS, DrainReport, SyncOutbox,
)
from je_auto_control.utils.config_sync.versions import SyncOperation

STATE_SYNCED = "synced"
STATE_PENDING = "pending"
STATE_CONFLICT = "conflict"
STATE_OFFLINE = "offline"
#: Nothing was sent: an earlier failure's retry delay has not run out yet.
STATE_BACKING_OFF = "backing_off"
STATE_CANCELLED = "cancelled"
STATE_RESYNC_REQUIRED = "resync_required"

#: Sections synced when the caller does not choose: the three stores every
#: machine has. ``scripts`` and ``locators`` join them when their path is given.
DEFAULT_SECTIONS = ("hotkeys", "triggers", "address_book")
#: Every section :func:`default_adapters` can build, and the option each needs.
SYNCABLE_SECTIONS: Dict[str, Optional[str]] = {
    "hotkeys": None, "triggers": None, "address_book": None,
    "scripts": "scripts_dir", "locators": "locators_path",
}
_STATUS = "status"
_UNAPPLIED = "unapplied"
_OPTIONS = frozenset({
    "device_id", "secret", "sections", "scripts_dir", "locators_path", "outbox_path",
    "assets_dir", "assets_server", "timeout_s", "wait", "max_attempts", "force",
})


@dataclass
class SyncRunReport:
    """How one sync ended, in the terms the status view shows.

    ``state`` is one of ``synced`` / ``pending`` / ``conflict`` / ``offline``
    / ``backing_off`` / ``cancelled`` / ``resync_required``; ``revision`` the
    last revision merged from the server; ``pending`` the operations still
    queued; ``conflicts`` the ``section/key`` names waiting for a choice.

    ``offline`` means this run tried the server and failed. ``backing_off``
    means it did not try: an earlier failure is still inside its retry
    delay, so nothing is known about the server now. Either way
    ``retry_in_s`` says how long until the queue is sent again by itself.
    """
    state: str = STATE_SYNCED
    revision: int = 0
    pending: int = 0
    conflicts: List[str] = field(default_factory=list)
    #: The sections this run covered, in the order they were synced.
    sections: List[str] = field(default_factory=list)
    applied: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    withheld: Dict[str, str] = field(default_factory=dict)
    assets: Dict[str, Any] = field(default_factory=dict)
    error: str = ""
    finished_at: float = 0.0
    last_success: float = 0.0
    retry_in_s: float = 0.0

    def to_dict(self) -> Dict[str, Any]:
        """A JSON-ready copy."""
        return {"state": self.state, "revision": self.revision, "pending": self.pending,
                "conflicts": list(self.conflicts), "sections": list(self.sections),
                "applied": dict(self.applied),
                "withheld": dict(self.withheld), "assets": dict(self.assets),
                "error": self.error, "finished_at": self.finished_at,
                "last_success": self.last_success, "retry_in_s": self.retry_in_s}


def resolve_sections(sections: Any = None, *, scripts_dir: Optional[str] = None,
                     locators_path: Optional[str] = None) -> List[str]:
    """The sections a sync covers, in order, for the caller's choice.

    ``None`` (or ``""``, an empty form field) is the default:
    :data:`DEFAULT_SECTIONS` -- this machine's hotkeys, triggers and address
    book -- plus ``scripts`` when ``scripts_dir`` is given and ``locators``
    when ``locators_path`` is. Giving a path therefore *adds* a section; it
    does not narrow the sync to it. To sync only some sections, name them: a
    list, or one comma-separated string (``"scripts"``).

    A named section must be one of :data:`SYNCABLE_SECTIONS` and its store
    must have been given; a choice that names nothing (``[]``, ``","``) is an
    error rather than a silent fall back to everything.
    """
    if sections is None or sections == "":
        return [*DEFAULT_SECTIONS, *(["scripts"] if scripts_dir else []),
                *(["locators"] if locators_path else [])]
    given = {"scripts_dir": scripts_dir, "locators_path": locators_path}
    wanted: List[str] = []
    for name in _section_names(sections):
        needs = _checked_section(name)
        if needs is not None and not given[needs]:
            raise ConfigSyncError(f"cannot sync section {name!r}: its {needs} is missing")
        if name not in wanted:
            wanted.append(name)
    if not wanted:
        raise ConfigSyncError(
            "sections names no section; omit it for the default "
            f"({', '.join(DEFAULT_SECTIONS)}) or name some of: {', '.join(SYNCABLE_SECTIONS)}")
    return wanted


def _section_names(sections: Any) -> List[Any]:
    """The names in a ``sections`` value: a list as it is, a string split on commas."""
    if isinstance(sections, str):
        # "a,,b" and a trailing comma name nothing extra.
        return [name.strip() for name in sections.split(",") if name.strip()]
    return [name.strip() if isinstance(name, str) else name for name in sections]


def _checked_section(name: Any) -> Optional[str]:
    """The option ``name`` needs (``None`` for none); an unknown name is an error."""
    if not isinstance(name, str) or name not in SYNCABLE_SECTIONS:
        raise ConfigSyncError(
            f"cannot sync section {name!r}: unknown; choose from {', '.join(SYNCABLE_SECTIONS)}")
    return SYNCABLE_SECTIONS[name]


def default_adapters(device_id: str, *, sections: Optional[Sequence[str]] = None,
                     scripts_dir: Optional[str] = None,
                     locators_path: Optional[str] = None) -> List[SyncAdapter]:
    """Adapters over this process's hotkey daemon, trigger engine and address book.

    Which sections is decided by :func:`resolve_sections`: without
    ``sections`` that is hotkeys, triggers and the address book, plus
    ``scripts`` / ``locators`` when their path is given -- so pass
    ``sections=["scripts"]`` to sync scripts and nothing else. Naming a
    section whose store was not given, or an unknown section, is an error
    rather than a silent omission.
    """
    wanted = resolve_sections(sections, scripts_dir=scripts_dir, locators_path=locators_path)
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
    raise ConfigSyncError(f"cannot sync section {name!r}: its store was not given")


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


@dataclass(frozen=True)
class _DrainOptions:
    """How :func:`run_sync` drains: the caller's cancel, wait, attempts and force."""
    cancel: Optional[threading.Event] = None
    wait: bool = False
    max_attempts: int = DEFAULT_DRAIN_ATTEMPTS
    force: bool = False


def _exchange(client: ConfigSyncClient, outbox: SyncOutbox, device_id: str,
              options: _DrainOptions) -> Tuple[Optional[SyncResult], DrainReport]:
    """Drain the outbox and pull; the server's state (``None`` if not reached)."""
    results: List[SyncResult] = []

    def send(batch: List[SyncOperation]) -> None:
        results.append(client.push_operations(batch, device_id=device_id))

    drained = outbox.drain(send, cancel=options.cancel, wait=options.wait,
                           max_attempts=options.max_attempts, force=options.force)
    if drained.cancelled or drained.offline:
        return None, drained
    if not results:
        try:
            results.append(client.push_operations([], device_id=device_id))
        except FullResyncRequired:
            raise
        except ConfigSyncError as error:
            return None, DrainReport(offline=True, error=str(error))
    return results[-1], drained


def _stopped_state(drained: DrainReport) -> str:
    """The run state for a drain that did not reach the server."""
    if drained.cancelled:
        return STATE_CANCELLED
    return STATE_BACKING_OFF if drained.backing_off else STATE_OFFLINE


def run_sync(client: ConfigSyncClient, outbox: SyncOutbox, adapters: Sequence[SyncAdapter], *,
             device_id: str, cancel: Optional[threading.Event] = None, wait: bool = False,
             max_attempts: int = DEFAULT_DRAIN_ATTEMPTS,
             asset_transport: Optional[AssetTransport] = None,
             force: bool = False) -> SyncRunReport:
    """Sync once and report the outcome; see the module docstring for the steps.

    A failure to reach the server is not an exception: the changes stay in
    the outbox and the report says ``offline``. A run that falls inside the
    retry delay of an earlier failure does not contact the server and says
    ``backing_off`` with ``retry_in_s``; ``force`` (a person asking for a
    sync *now*) skips that delay once, ``wait`` sleeps through it. A device
    the group retired gets ``resync_required`` -- call
    :func:`run_full_resync`.
    """
    baseline = outbox.load_baseline() or ConfigBucket(user_id=client.user_id)
    report = SyncRunReport(revision=baseline.revision,
                           sections=[adapter.section for adapter in adapters])
    report.withheld = _stage(outbox, adapters, baseline)
    manifest = _script_assets(adapters, baseline)
    if asset_transport is not None and manifest is not None:
        report.assets["published"] = publish_assets(
            _present(manifest), asset_transport, cancel=cancel).to_dict()
    try:
        result, drained = _exchange(client, outbox, device_id, _DrainOptions(
            cancel=cancel, wait=wait, max_attempts=max_attempts, force=force))
    except FullResyncRequired as required:
        report.state, report.error = STATE_RESYNC_REQUIRED, str(required)
        return _finish(outbox, report)
    if result is None:
        report.state = _stopped_state(drained)
        report.error, report.retry_in_s = drained.error, drained.retry_in_s
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
    report = SyncRunReport(revision=baseline.revision,
                           sections=[adapter.section for adapter in adapters])
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
    # Live, not the figure the last run stored: the delay keeps running down.
    status["retry_in_s"] = float(outbox.seconds_until_due(time.time()) or 0.0)
    waiting_over = status["state"] == STATE_BACKING_OFF and not status["retry_in_s"]
    if status["pending"] and (status["state"] == STATE_SYNCED or waiting_over):
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

def _chosen(options: Mapping[str, Any]) -> Dict[str, Any]:
    """The options that were given a value; an unknown name is an error."""
    unknown = sorted(set(options) - _OPTIONS)
    if unknown:
        raise ConfigSyncError(f"unknown config sync option(s): {', '.join(unknown)}")
    return {name: value for name, value in options.items() if value not in (None, "")}


def _session(server_url: str, user_id: str, options: Mapping[str, Any],
             ) -> Tuple[ConfigSyncClient, SyncOutbox, List[SyncAdapter], str]:
    chosen = _chosen(options)
    device_id = str(chosen.get("device_id") or default_device_id())
    client = ConfigSyncClient(
        server_url, user_id=user_id, timeout_s=float(chosen.get("timeout_s", 5.0)),
        device_id=device_id,
        secret=chosen.get("secret") or os.environ.get("AC_SIGNALING_SECRET") or None)
    outbox = SyncOutbox(chosen.get("outbox_path"), account=user_id, endpoint=client.server_url)
    adapters = default_adapters(device_id, sections=options.get("sections"),
                                scripts_dir=chosen.get("scripts_dir"),
                                locators_path=chosen.get("locators_path"))
    return client, outbox, adapters, device_id


def config_sync_run(server_url: str, user_id: str, *,
                    cancel: Optional[threading.Event] = None, **options: Any) -> Dict[str, Any]:
    """Sync this machine's settings with ``server_url`` once; returns the report.

    Options: ``device_id`` (default: this machine's stored id), ``secret``
    (default ``$AC_SIGNALING_SECRET``), ``sections`` (see
    :func:`resolve_sections`: the default is this machine's hotkeys,
    triggers and address book, and ``scripts_dir`` / ``locators_path`` *add*
    their section -- pass ``sections="scripts"`` to sync scripts alone; the
    report's ``sections`` lists what was covered), ``scripts_dir``,
    ``locators_path``, ``outbox_path``, ``assets_dir`` (a folder both
    machines reach, for scripts too large to inline) or ``assets_server``
    (true: keep those on the sync server itself, at ``/blobs``), ``timeout_s``,
    ``wait`` (sleep through a retry back-off instead of returning
    ``backing_off``), ``force`` (skip that back-off once: someone asked for
    a sync now) and ``max_attempts``.
    """
    if cancel is not None and not isinstance(cancel, threading.Event):
        raise ConfigSyncError("cancel must be a threading.Event")
    client, outbox, adapters, device_id = _session(server_url, user_id, options)
    return run_sync(
        client, outbox, adapters, device_id=device_id, cancel=cancel,
        wait=bool(options.get("wait", False)), force=bool(options.get("force", False)),
        max_attempts=int(options.get("max_attempts") or DEFAULT_DRAIN_ATTEMPTS),
        asset_transport=_asset_transport(client, options)).to_dict()


def _asset_transport(client: ConfigSyncClient,
                     options: Mapping[str, Any]) -> Optional[AssetTransport]:
    """Where large scripts travel: a shared folder, the sync server, or nowhere."""
    assets_dir = options.get("assets_dir")
    if not options.get("assets_server"):
        return DirectoryAssetTransport(assets_dir) if assets_dir else None
    if assets_dir:
        raise ConfigSyncError("give assets_dir or assets_server, not both")
    return HttpAssetTransport(
        client.server_url, user_id=client.user_id, timeout_s=client.timeout_s,
        secret=options.get("secret") or os.environ.get("AC_SIGNALING_SECRET") or None)


def config_sync_status(server_url: str, user_id: str, outbox_path: Optional[str] = None,
                       **options: Any) -> Dict[str, Any]:
    """The recorded sync state for this account and server; no network.

    Takes the same options as :func:`config_sync_run`, so one options dict
    serves all four entry points. Only ``outbox_path`` (which may also be
    given positionally, as before) changes the answer; the others are
    checked for their names and otherwise ignored, because reading the
    recorded state needs no device, secret or section.
    """
    _chosen(options)
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
    "DEFAULT_SECTIONS", "STATE_BACKING_OFF", "STATE_CANCELLED", "STATE_CONFLICT",
    "STATE_OFFLINE", "STATE_PENDING",
    "STATE_RESYNC_REQUIRED", "STATE_SYNCED", "SyncRunReport", "config_sync_full_resync",
    "SYNCABLE_SECTIONS", "config_sync_resolve", "config_sync_run", "config_sync_status",
    "default_adapters", "default_device_id", "default_device_id_path", "resolve_conflict",
    "resolve_sections", "run_full_resync", "run_sync", "sync_status",
]
