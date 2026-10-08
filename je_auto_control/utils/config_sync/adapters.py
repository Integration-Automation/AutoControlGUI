"""Adapters between local AutoControl state and synced entries.

Each :class:`SyncAdapter` owns one bucket section. :meth:`SyncAdapter.snapshot`
turns what this machine holds into :class:`SyncEntry` values, measured
against the *baseline* (the state last merged) so only real changes get a
new version; :meth:`SyncAdapter.apply` writes merged entries back.

Three rules hold for every adapter:

* **Secrets stay here.** A field whose name marks it as a secret is replaced
  by a ``{"$local": "secret"}`` reference before it leaves, and a script
  containing a literal secret is not synced at all. The receiving machine
  keeps its own value for that field.
* **Machine paths stay here.** A path inside the adapter's script directory
  travels as a relative reference and is resolved against the receiver's own
  directory; any other path becomes a ``{"$local": "path"}`` reference.
* **Syncing never arms anything.** ``enabled`` is not synced. A hotkey or
  trigger that arrives is created disabled, one that already exists keeps
  the state this machine gave it, and nothing here starts an engine or runs
  a script.

Pure standard library; imports no ``PySide6``.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, fields
from pathlib import Path, PurePosixPath
from typing import Any, ClassVar, Dict, Iterable, List, Mapping, Optional, Set, Tuple, Union

from je_auto_control.utils.config_sync.client import ConfigSyncError
from je_auto_control.utils.config_sync.versions import SyncEntry, SyncOperation
from je_auto_control.utils.exception.exceptions import AutoControlException

#: Marks a value that only means something on the machine it came from.
LOCAL_REF = "$local"
#: A script up to this size travels inside its entry; a larger one is listed
#: by hash and has to come through an asset transport.
MAX_INLINE_SCRIPT_BYTES = 64 * 1024


def is_local_ref(value: Any) -> bool:
    """Whether ``value`` is a reference to something kept on its own machine."""
    return isinstance(value, Mapping) and LOCAL_REF in value


@dataclass
class ApplyReport:
    """What :meth:`SyncAdapter.apply` did to this machine.

    ``skipped`` maps a key to why it was left alone; ``conflicts`` lists the
    keys still waiting for a choice between concurrent changes;
    ``left_disabled`` the hotkeys / triggers that arrived and were not armed.
    """
    section: str = ""
    written: List[str] = field(default_factory=list)
    removed: List[str] = field(default_factory=list)
    skipped: Dict[str, str] = field(default_factory=dict)
    conflicts: List[str] = field(default_factory=list)
    left_disabled: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict[str, Any]:
        """A JSON-ready copy."""
        return {"section": self.section, "written": list(self.written),
                "removed": list(self.removed), "skipped": dict(self.skipped),
                "conflicts": list(self.conflicts), "left_disabled": list(self.left_disabled)}


class SyncAdapter:
    """One section of the bucket, backed by some local store.

    Subclasses provide :meth:`read_local`, :meth:`write_local` and
    :meth:`delete_local`; the portable-form rules and the baseline
    bookkeeping are here.
    """

    section: ClassVar[str] = ""
    #: Fields holding filesystem paths, made portable through ``scripts_dir``.
    path_fields: ClassVar[Tuple[str, ...]] = ()
    #: Fields that describe this machine only and are never sent.
    local_fields: ClassVar[Tuple[str, ...]] = ()

    def __init__(self, origin: str, *, scripts_dir: Union[str, Path, None] = None) -> None:
        if not origin:
            raise ConfigSyncError("an adapter needs this device's id")
        self.origin = origin
        self._scripts_dir = None if scripts_dir is None else Path(scripts_dir)
        self._baseline: Dict[str, SyncEntry] = {}
        self._unapplied: Set[str] = set()

    def rebase(self, baseline: Mapping[str, SyncEntry], unapplied: Iterable[str] = ()) -> None:
        """Set the entries local changes are measured against.

        ``unapplied`` names baseline keys that could not be written to this
        machine (a path that does not exist here, a key combination this
        platform refuses). Their absence here is not a deletion.
        """
        self._baseline = dict(baseline)
        self._unapplied = set(unapplied)

    # --- the local store (subclass responsibility) ---------------------------

    def read_local(self) -> Dict[str, Dict[str, Any]]:
        """This machine's items, by key."""
        raise NotImplementedError

    def write_local(self, key: str, value: Dict[str, Any],
                    existing: Optional[Dict[str, Any]]) -> None:
        """Create or replace ``key``; ``existing`` is the current local item."""
        raise NotImplementedError

    def delete_local(self, key: str) -> None:
        """Remove ``key`` from this machine."""
        raise NotImplementedError

    # --- portable form -------------------------------------------------------

    def _portable_path(self, name: str, raw: Any) -> Any:
        if not isinstance(raw, str) or not raw:
            return raw
        root = self._scripts_dir
        if root is not None:
            try:
                relative = Path(raw).resolve().relative_to(root.resolve())
            except (OSError, ValueError):
                relative = None
            if relative is not None:
                return {LOCAL_REF: "path", "root": "scripts", "relative": relative.as_posix()}
        return {LOCAL_REF: "path", "field": name, "name": Path(raw).name}

    def _local_path(self, reference: Any) -> Optional[str]:
        """The local path a reference names, or ``None`` when it has none here."""
        if not is_local_ref(reference):
            return reference if isinstance(reference, str) else None
        parts = _contained_parts(reference.get("relative"))
        if self._scripts_dir is None or reference.get("root") != "scripts" or parts is None:
            return None
        return str(self._scripts_dir.joinpath(*parts))

    def to_portable(self, value: Mapping[str, Any]) -> Dict[str, Any]:
        """``value`` as it may leave this machine: no secrets, no local paths."""
        from je_auto_control.utils.secret_ref import is_ref
        from je_auto_control.utils.secrets_scan.secrets_scan import is_secret_key, scan_secrets
        portable: Dict[str, Any] = {}
        for name, item in value.items():
            if name in self.local_fields or name.startswith("_"):
                continue
            if name in self.path_fields:
                portable[name] = self._portable_path(name, item)
            elif is_local_ref(item) or is_ref(item):
                portable[name] = item
            elif (scan_secrets({name: item}) if is_secret_key(name)
                  else isinstance(item, (dict, list)) and scan_secrets(item)):
                # A secret by its field name, or one nested inside a structure.
                # scan_secrets passes ${secrets.NAME}: a reference may travel.
                portable[name] = {LOCAL_REF: "secret", "field": name}
            else:
                portable[name] = item
        return portable

    def from_portable(self, value: Mapping[str, Any],
                      existing: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
        """``value`` made usable here: references filled from this machine.

        Raises :class:`ConfigSyncError` when a path the item needs does not
        exist on this machine in any form.
        """
        local: Dict[str, Any] = {}
        for name, item in value.items():
            if not is_local_ref(item):
                local[name] = item
                continue
            resolved = self._local_path(item) if name in self.path_fields else None
            if resolved is None and existing is not None and name in existing:
                resolved = existing[name]
            if resolved is None and name in self.path_fields:
                raise ConfigSyncError(f"{name} refers to a path kept on another machine")
            if resolved is not None:
                local[name] = resolved
        return local

    # --- snapshot / apply ----------------------------------------------------

    def snapshot(self) -> Mapping[str, SyncEntry]:
        """This machine's items as entries, versioned against the baseline.

        An item equal to the baseline keeps its entry; a changed or new one
        becomes a new version made by this device; a baseline item that is
        gone here becomes a tombstone. An entry still in conflict is left as
        it is -- a local edit must not settle a conflict by accident.
        """
        current = {key: self.to_portable(value) for key, value in self.read_local().items()}
        entries = {key: self._present(key, value) for key, value in current.items()}
        for key, base in self._baseline.items():
            if key not in current:
                keep = base.deleted or base.in_conflict or key in self._unapplied
                entries[key] = base if keep else base.removed(self.origin)
        return entries

    def _present(self, key: str, value: Dict[str, Any]) -> SyncEntry:
        """The entry for an item this machine holds."""
        base = self._baseline.get(key)
        if base is None:
            return SyncEntry.create(key, value, self.origin)
        if base.in_conflict or (not base.deleted and base.value == value):
            return base
        return base.edited(value, self.origin)

    def pending_operations(self) -> List[SyncOperation]:
        """The changes :meth:`snapshot` holds that the baseline does not."""
        return [SyncOperation(section=self.section, entry=entry)
                for key, entry in sorted(self.snapshot().items())
                if key not in self._baseline
                or self._baseline[key].operation_id != entry.operation_id]

    def apply(self, entries: Mapping[str, SyncEntry]) -> ApplyReport:
        """Bring this machine to ``entries``; never enables or runs anything.

        A key the baseline held that ``entries`` no longer has was deleted
        elsewhere and is removed here. A key only this machine has is a
        change not yet sent and is kept.
        """
        report = ApplyReport(section=self.section)
        local = self.read_local()
        for key in sorted(entries):
            self._apply_one(key, entries[key], local.get(key), report)
        for key, base in sorted(self._baseline.items()):
            if key not in entries and not base.deleted and key in local:
                self._remove(key, report)
        return report

    def _remove(self, key: str, report: ApplyReport) -> None:
        try:
            self.delete_local(key)
        except (AutoControlException, OSError, ValueError) as error:
            report.skipped[key] = str(error) or type(error).__name__
            return
        report.removed.append(key)

    def _apply_one(self, key: str, entry: SyncEntry, existing: Optional[Dict[str, Any]],
                   report: ApplyReport) -> None:
        if entry.in_conflict:
            report.conflicts.append(key)
            return
        if entry.deleted:
            if existing is not None:
                self._remove(key, report)
            return
        value = dict(entry.value or {})
        if existing is None or self.to_portable(existing) != value:
            self._write(key, value, existing, report)

    def _write(self, key: str, value: Dict[str, Any], existing: Optional[Dict[str, Any]],
               report: ApplyReport) -> None:
        try:
            self.write_local(key, self.from_portable(value, existing), existing)
        except (AutoControlException, OSError, ValueError, TypeError, KeyError) as error:
            report.skipped[key] = str(error) or type(error).__name__
            return
        report.written.append(key)
        if self.arms_on_enable and existing is None:
            report.left_disabled.append(key)

    #: Whether items of this section do something once enabled.
    arms_on_enable: ClassVar[bool] = False


def _contained_parts(relative: Any) -> Optional[Tuple[str, ...]]:
    """The parts of a relative posix path that cannot leave its folder, else ``None``.

    Refuses an absolute path, ``..``, and -- because the join happens with
    the receiving machine's rules -- a drive letter or a backslash, either of
    which lets a Windows join walk out of the folder.
    """
    if not isinstance(relative, str) or ":" in relative or "\\" in relative:
        return None
    path = PurePosixPath(relative)
    if not path.parts or path.is_absolute() or ".." in path.parts:
        return None
    return path.parts


def _safe_relative(root: Path, key: str) -> Path:
    """``root / key`` for a relative posix key that stays inside ``root``."""
    parts = _contained_parts(key)
    if parts is None:
        raise ConfigSyncError(f"refusing path {key!r}: it does not stay inside the folder")
    return root.joinpath(*parts)


class ScriptSyncAdapter(SyncAdapter):
    """The ``*.json`` action scripts under one directory, by relative path.

    A script travels with its SHA-256; :meth:`write_local` refuses content
    whose hash does not match and replaces the file atomically. Receiving a
    script only writes the file -- nothing executes it. A script holding a
    literal secret is not sent: put ``${secrets.NAME}`` in the script instead.
    """

    section = "scripts"

    def __init__(self, origin: str, scripts_dir: Union[str, Path]) -> None:
        super().__init__(origin, scripts_dir=scripts_dir)
        self._root = Path(scripts_dir)
        #: Scripts left out of the last snapshot, and why.
        self.withheld: Dict[str, str] = {}

    @property
    def root(self) -> Path:
        """The directory whose scripts this adapter syncs."""
        return self._root

    def read_local(self) -> Dict[str, Dict[str, Any]]:
        from je_auto_control.utils.secrets_scan.secrets_scan import scan_secrets
        items: Dict[str, Dict[str, Any]] = {}
        self.withheld = {}
        if not self._root.is_dir():
            return items
        for path in sorted(self._root.rglob("*.json")):
            key = path.relative_to(self._root).as_posix()
            try:
                data = path.read_bytes()
                parsed = json.loads(data.decode("utf-8"))
            except (OSError, ValueError, RecursionError) as error:
                self.withheld[key] = f"unreadable: {error}"
                continue
            if scan_secrets(parsed):
                self.withheld[key] = "contains a literal secret; use a ${secrets.NAME} reference"
                continue
            item: Dict[str, Any] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
            if len(data) <= MAX_INLINE_SCRIPT_BYTES:
                item["content"] = data.decode("utf-8")
            items[key] = item
        return items

    def snapshot(self) -> Mapping[str, SyncEntry]:
        entries = dict(super().snapshot())
        # A withheld script is still on this machine: it must not be turned
        # into a deletion for everyone else.
        for key in self.withheld:
            base = self._baseline.get(key)
            if base is not None:
                entries[key] = base
            else:
                entries.pop(key, None)
        return entries

    def write_local(self, key: str, value: Dict[str, Any],
                    existing: Optional[Dict[str, Any]]) -> None:
        from je_auto_control.utils.json_store.json_store import atomic_write_bytes
        content = value.get("content")
        if not isinstance(content, str):
            raise ConfigSyncError("content travels as an asset; run the asset sync for it")
        data = content.encode("utf-8")
        if hashlib.sha256(data).hexdigest() != value.get("sha256"):
            raise ConfigSyncError("content does not match its SHA-256; not written")
        target = _safe_relative(self._root, key)
        target.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_bytes(target, data)

    def delete_local(self, key: str) -> None:
        _safe_relative(self._root, key).unlink(missing_ok=True)


class LocatorSyncAdapter(SyncAdapter):
    """The named accessibility locators of an ``ElementRepository``."""

    section = "locators"

    def __init__(self, origin: str, repository: Any) -> None:
        super().__init__(origin)
        self._repository = repository

    def read_local(self) -> Dict[str, Dict[str, Any]]:
        return {key: dict(value) for key, value in self._repository.all().items()}

    def write_local(self, key: str, value: Dict[str, Any],
                    existing: Optional[Dict[str, Any]]) -> None:
        self._repository.save(key, name=value.get("name"), role=value.get("role"),
                              app_name=value.get("app_name"))

    def delete_local(self, key: str) -> None:
        self._repository.remove(key)


class HotkeySyncAdapter(SyncAdapter):
    """The bindings of a ``HotkeyDaemon``; an arriving binding is never armed."""

    section = "hotkeys"
    path_fields = ("script_path",)
    local_fields = ("enabled", "fired", "binding_id")
    arms_on_enable = True

    def __init__(self, origin: str, daemon: Any, *,
                 scripts_dir: Union[str, Path, None] = None) -> None:
        super().__init__(origin, scripts_dir=scripts_dir)
        self._daemon = daemon

    def _bindings(self) -> Dict[str, Any]:
        return {binding.binding_id: binding for binding in self._daemon.list_bindings()}

    def read_local(self) -> Dict[str, Dict[str, Any]]:
        return {key: {"combo": binding.combo, "script_path": binding.script_path,
                      "enabled": binding.enabled}
                for key, binding in self._bindings().items()}

    def write_local(self, key: str, value: Dict[str, Any],
                    existing: Optional[Dict[str, Any]]) -> None:
        # A new binding starts disabled; an existing one keeps what this
        # machine chose. The synced value has no say in either.
        enabled = bool(existing.get("enabled")) if existing is not None else False
        self._daemon.bind(str(value["combo"]), str(value["script_path"]), binding_id=key,
                          enabled=enabled)

    def delete_local(self, key: str) -> None:
        self._daemon.unbind(key)


def _trigger_types() -> Dict[str, Any]:
    from je_auto_control.utils.triggers import trigger_engine
    return {cls.__name__: cls for cls in (
        trigger_engine.ImageAppearsTrigger, trigger_engine.WindowAppearsTrigger,
        trigger_engine.PixelColorTrigger, trigger_engine.FilePathTrigger,
        trigger_engine.CronTrigger)}


class TriggerSyncAdapter(SyncAdapter):
    """The triggers of a ``TriggerEngine``; an arriving trigger is never armed.

    Image, window, pixel, file and cron triggers are synced. Composite
    triggers (all-of / any-of / sequence) hold other trigger objects and stay
    local; they are listed in :attr:`withheld`.
    """

    section = "triggers"
    path_fields = ("script_path", "image_path", "watch_path")
    local_fields = ("enabled", "fired", "trigger_id")
    arms_on_enable = True

    def __init__(self, origin: str, engine: Any, *,
                 scripts_dir: Union[str, Path, None] = None) -> None:
        super().__init__(origin, scripts_dir=scripts_dir)
        self._engine = engine
        #: Triggers left out of the last snapshot, and why.
        self.withheld: Dict[str, str] = {}

    def read_local(self) -> Dict[str, Dict[str, Any]]:
        known = _trigger_types()
        items: Dict[str, Dict[str, Any]] = {}
        self.withheld = {}
        for trigger in self._engine.list_triggers():
            kind = type(trigger).__name__
            if kind not in known:
                self.withheld[trigger.trigger_id] = f"{kind} is not synced"
                continue
            item = {spec.name: getattr(trigger, spec.name) for spec in fields(trigger)
                    if not spec.name.startswith("_")}
            if isinstance(item.get("target_rgb"), tuple):
                item["target_rgb"] = list(item["target_rgb"])
            items[trigger.trigger_id] = {"type": kind, **item}
        return items

    def snapshot(self) -> Mapping[str, SyncEntry]:
        entries = dict(super().snapshot())
        for key in self.withheld:
            entries.pop(key, None)
        return entries

    def write_local(self, key: str, value: Dict[str, Any],
                    existing: Optional[Dict[str, Any]]) -> None:
        known = _trigger_types()
        kind = value.get("type")
        if kind not in known:
            raise ConfigSyncError(f"unknown trigger type {kind!r}")
        allowed = {spec.name for spec in fields(known[kind]) if not spec.name.startswith("_")}
        arguments = {name: item for name, item in value.items()
                     if name in allowed and name not in self.local_fields}
        if "target_rgb" in arguments:
            arguments["target_rgb"] = tuple(arguments["target_rgb"])
        # Disabled unless this machine had already enabled the same trigger.
        enabled = bool(existing.get("enabled")) if existing is not None else False
        self._engine.add(known[kind](trigger_id=key, enabled=enabled, **arguments))

    def delete_local(self, key: str) -> None:
        self._engine.remove(key)


class AddressBookSyncAdapter(SyncAdapter):
    """The remote-desktop address book: hosts, labels, tags and favourites.

    ``last_used`` describes this machine's own history and is not synced;
    any credential-like field stays local as a reference.
    """

    section = "address_book"
    local_fields = ("last_used",)
    _SEPARATOR = "|"

    def __init__(self, origin: str, book: Any) -> None:
        super().__init__(origin)
        self._book = book

    def read_local(self) -> Dict[str, Dict[str, Any]]:
        return {f"{entry.get('server_url', '')}{self._SEPARATOR}{entry.get('host_id', '')}": dict(entry)
                for entry in self._book.list_entries()
                if entry.get("server_url") and entry.get("host_id")}

    def write_local(self, key: str, value: Dict[str, Any],
                    existing: Optional[Dict[str, Any]]) -> None:
        host_id, server_url = str(value["host_id"]), str(value["server_url"])
        self._book.upsert(host_id=host_id, server_url=server_url,
                          label=str(value.get("label", "")),
                          mac_address=value.get("mac_address"),
                          broadcast_address=value.get("broadcast_address"))
        self._book.set_tags(host_id=host_id, server_url=server_url,
                            tags=list(value.get("tags") or []))
        favourite = bool(existing.get("favorite")) if existing is not None else False
        if bool(value.get("favorite")) != favourite:
            self._book.toggle_favorite(host_id=host_id, server_url=server_url)

    def delete_local(self, key: str) -> None:
        server_url, _separator, host_id = key.rpartition(self._SEPARATOR)
        self._book.remove(host_id=host_id, server_url=server_url)


__all__ = [
    "AddressBookSyncAdapter", "ApplyReport", "HotkeySyncAdapter", "LOCAL_REF",
    "LocatorSyncAdapter", "MAX_INLINE_SCRIPT_BYTES", "ScriptSyncAdapter", "SyncAdapter",
    "TriggerSyncAdapter", "is_local_ref",
]
