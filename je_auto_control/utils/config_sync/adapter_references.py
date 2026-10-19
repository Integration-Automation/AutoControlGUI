"""Portable adapter references never resolve vault values or serialize local machine bindings."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import PurePosixPath, PureWindowsPath
import re
from types import MappingProxyType
from typing import Literal, Mapping, Optional, cast

from je_auto_control.utils.config_sync.contract import ConfigSyncError, _encoded
from je_auto_control.utils.executor.action_redaction import _ALL_SECRET_COMMANDS, is_sensitive_argument
from je_auto_control.utils.logging.secret_scope import scrub_secret_data
from je_auto_control.utils.secrets_scan.secrets_scan import is_secret_key, scan_secrets

_TAG = '$autocontrol_ref'
_NAME = re.compile(r'[A-Za-z_][A-Za-z0-9_.-]{0,127}')
_VARIABLE = re.compile(r'\$\{[A-Za-z_][\w.]*\}')
_SECRET = re.compile(r'\$\{secrets\.([A-Za-z_][A-Za-z0-9_.]*)\}')
_REFERENCE_FIELDS = {'secret_env', 'api_key_env', 'secret_name', 'vault_name'}
_LOCAL_FIELDS = {'device_id', 'device_index', 'device_serial', 'serial', 'udid', 'android_serial', 'ios_udid',
                 'wda_url', 'wda_base_url', 'adb_path', 'connection_id', 'window_handle', 'hwnd',
                 'screen_index', 'monitor_index', 'x_display', 'display_id', 'pid', 'session_id'}


@dataclass(frozen=True)
class SyncReference:
    """A portable vault name or a named local machine value, without its resolved value."""

    kind: Literal['secret', 'local']
    name: str

    def __post_init__(self) -> None:
        if not isinstance(self.kind, str) or self.kind not in {'secret', 'local'}:
            raise ConfigSyncError('invalid adapter reference kind')
        if not isinstance(self.name, str) or _NAME.fullmatch(self.name) is None:
            raise ConfigSyncError('invalid adapter reference')
        if self.kind == 'secret' and ('-' in self.name or any(not part for part in self.name.split('.'))):
            raise ConfigSyncError('vault references require a name supported by action interpolation')

    def to_dict(self) -> dict[str, object]:
        """Copy the exact portable reference marker."""
        return {_TAG: {'kind': self.kind, 'name': self.name}}


@dataclass(frozen=True)
class SyncBindings:
    """Entry/JSON-pointer reference declarations and receiver-local values; neither is sent as sync metadata."""

    fields: Mapping[str, Mapping[str, SyncReference]] = field(default_factory=dict)
    local_values: Mapping[str, object] = field(default_factory=dict, repr=False)

    def __post_init__(self) -> None:
        fields = _fields(self.fields)
        local = _local_values(self.local_values)
        object.__setattr__(self, 'fields', MappingProxyType(fields))
        object.__setattr__(self, 'local_values', MappingProxyType(local))

    @classmethod
    def from_dict(cls, body: dict[str, object]) -> SyncBindings:
        """Parse private local binding configuration; this structure is never part of a portable sync entry."""
        if not isinstance(body, dict) or not set(body) <= {'fields', 'local_values'}:
            raise ConfigSyncError('invalid local adapter binding configuration')
        raw = body.get('fields', {})
        if not isinstance(raw, dict):
            raise ConfigSyncError('adapter reference fields require a mapping')
        fields: dict[str, dict[str, SyncReference]] = {}
        for entry_id, values in raw.items():
            if not isinstance(values, dict):
                raise ConfigSyncError('invalid adapter reference field map')
            fields[entry_id] = {pointer: _required_reference(value) for pointer, value in values.items()}
        return cls(fields, cast(Mapping[str, object], body.get('local_values', {})))


def _fields(values: Mapping[str, Mapping[str, SyncReference]]) -> dict[str, Mapping[str, SyncReference]]:
    if not isinstance(values, Mapping) or len(values) > 1000:
        raise ConfigSyncError('adapter field bindings must be a bounded mapping')
    result: dict[str, Mapping[str, SyncReference]] = {}
    for entry_id, fields in values.items():
        if not isinstance(entry_id, str):
            raise ConfigSyncError('invalid adapter field bindings')
        result[entry_id] = _field_map(fields)
    return result


def _field_map(fields: Mapping[str, SyncReference]) -> Mapping[str, SyncReference]:
    if not isinstance(fields, Mapping) or len(fields) > 1000:
        raise ConfigSyncError('invalid adapter field bindings')
    for pointer, reference in fields.items():
        if (not isinstance(pointer, str) or not pointer.startswith('/') or len(pointer) > 2048
                or not isinstance(reference, SyncReference) or re.search(r'~(?![01])', pointer)):
            raise ConfigSyncError('field bindings require JSON pointers and typed references')
    return MappingProxyType(dict(fields))


def _local_values(values: Mapping[str, object]) -> dict[str, object]:
    if not isinstance(values, Mapping) or len(values) > 1000:
        raise ConfigSyncError('local adapter values must be a bounded mapping')
    result: dict[str, object] = {}
    for name, value in values.items():
        SyncReference('local', name)
        if not _local_scalar(value) or is_secret_key(name) or scan_secrets({'value': value}):
            raise ConfigSyncError('local bindings cannot carry recognized plaintext credentials')
        result[name] = value
    _known_secrets(result)
    return result


def _local_scalar(value: object) -> bool:
    return value is None or isinstance(value, (str, int, float, bool))


def _reference(value: object) -> Optional[SyncReference]:
    if not isinstance(value, dict) or _TAG not in value:
        return None
    body = value[_TAG]
    if set(value) != {_TAG} or not isinstance(body, dict) or set(body) != {'kind', 'name'}:
        raise ConfigSyncError('invalid portable adapter reference marker')
    return SyncReference(cast(Literal['secret', 'local'], body['kind']), cast(str, body['name']))


def _required_reference(value: object) -> SyncReference:
    reference = _reference(value)
    if reference is None:
        raise ConfigSyncError('field declarations require typed adapter reference markers')
    return reference


def export_value(entry_id: str, value: dict[str, object], bindings: SyncBindings, *,
                    root_key: str = '') -> dict[str, object]:
    """Replace declared source fields before refusing remaining recognized secrets or absolute paths."""
    _encoded(value)
    walker = _ReferenceWalker(bindings.fields.get(entry_id, {}), bindings.local_values, True)
    result = cast(dict[str, object], walker.visit(value, '', root_key))
    _known_secrets(result)
    return result


def validate_portable(value: dict[str, object], *, root_key: str = '') -> None:
    """Validate received payloads without changing their causal operation's bytes or resolving references."""
    before = _encoded(value)
    walker = _ReferenceWalker({}, {}, False)
    if _encoded(cast(dict[str, object], walker.visit(value, '', root_key))) != before:
        raise ConfigSyncError('portable validation cannot alter an incoming operation')
    _known_secrets(value)


def resolve_value(value: dict[str, object], bindings: SyncBindings) -> tuple[dict[str, object], tuple[str, ...]]:
    """Produce a local profile copy; vault references stay interpolation placeholders and never read a vault."""
    missing: set[str] = set()
    result = _resolve(value, bindings.local_values, missing)
    return cast(dict[str, object], result), tuple(sorted(missing))


def _resolve(value: object, local: Mapping[str, object], missing: set[str]) -> object:
    reference = _reference(value)
    if reference is not None:
        if reference.kind == 'secret':
            return '${secrets.' + reference.name + '}'
        if reference.name not in local:
            missing.add(reference.name)
            return value
        return local[reference.name]
    if isinstance(value, dict):
        return {key: _resolve(item, local, missing) for key, item in value.items()}
    if isinstance(value, list):
        return [_resolve(item, local, missing) for item in value]
    return value


def _known_secrets(value: Mapping[str, object]) -> None:
    body = dict(value)
    if _encoded(body) != _encoded(cast(dict[str, object], scrub_secret_data(body))):
        raise ConfigSyncError('resolved credentials cannot enter adapter metadata')


# pylint: disable-next=too-few-public-methods  # reason: one bounded JSON visitor delegates private scalar policies
class _ReferenceWalker:
    """Bounded JSON traversal keeps source conversion separate from immutable incoming validation."""

    def __init__(self, fields: Mapping[str, SyncReference], local: Mapping[str, object], source: bool) -> None:
        self._fields = fields
        self._local = local
        self._source = source

    def visit(self, value: object, pointer: str, key: str = '', command: str = '', depth: int = 0) -> object:
        """Validate one bounded node, tracking action context and an RFC-6901 pointer."""
        if depth > 32:
            raise ConfigSyncError('adapter definitions exceed the nesting limit')
        if pointer in self._fields:
            return self._fields[pointer].to_dict()
        reference = _reference(value)
        if reference is not None:
            return reference.to_dict()
        if isinstance(value, dict):
            return {name: self.visit(item, pointer + '/' + _escape(name),
                                     _field_key(pointer, key, name), command, depth + 1)
                    for name, item in value.items()}
        if isinstance(value, list):
            action = _action_name(value) or command
            return [self.visit(item, pointer + '/' + str(index), key, action, depth + 1)
                    for index, item in enumerate(value)]
        return self._scalar(value, pointer, key, command)

    def _scalar(self, value: object, pointer: str, key: str, command: str) -> object:
        if isinstance(value, str):
            if _action_token(value, pointer, key, command):
                return value
            converted = self._string_reference(value)
            if converted is not None:
                return converted
            if _reference_name(key, value):
                return value
            if _machine_path(value):
                raise ConfigSyncError(f'unbound local path at {pointer}')
        _validate_scalar(value, pointer, key, command)
        return value

    def _string_reference(self, value: str) -> Optional[object]:
        if _VARIABLE.fullmatch(value):
            secret = _SECRET.fullmatch(value)
            if secret is not None and self._source:
                return SyncReference('secret', secret.group(1)).to_dict()
            return value
        if self._source:
            names = [name for name, item in self._local.items() if item == value]
            if len(names) > 1:
                raise ConfigSyncError('local value has ambiguous adapter reference names')
            if names:
                return SyncReference('local', names[0]).to_dict()
        return None


def _validate_scalar(value: object, pointer: str, key: str, command: str) -> None:
    if key.lower() in _LOCAL_FIELDS and value is not None:
        raise ConfigSyncError(f'unbound local connection or display value at {pointer}')
    if _private_command(command) and value is not None:
        raise ConfigSyncError(f'unbound private-command argument at {pointer}')
    sensitive = is_sensitive_argument(command, key) or is_secret_key(key)
    if scan_secrets({key or 'value': value}) or sensitive and value not in (None, False, True, ''):
        raise ConfigSyncError(f'unbound credential at {pointer}')


def _private_command(command: str) -> bool:
    return command in _ALL_SECRET_COMMANDS or command.startswith('AC_secret_')


def _action_token(value: str, pointer: str, key: str, command: str) -> bool:
    return (value == command and pointer.endswith('/0') and not is_secret_key(key)
            and not is_sensitive_argument(command, key))


def _escape(value: str) -> str:
    return value.replace('~', '~0').replace('/', '~1')


def _field_key(pointer: str, parent_key: str, name: str) -> str:
    return parent_key if not pointer and name == 'value' and parent_key else name


def _action_name(value: list[object]) -> str:
    return value[0] if value and isinstance(value[0], str) and value[0].startswith('AC_') else ''


def _reference_name(key: str, value: str) -> bool:
    return key in _REFERENCE_FIELDS and re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]{0,127}', value) is not None


def _machine_path(value: str) -> bool:
    return (PurePosixPath(value).is_absolute() or bool(PureWindowsPath(value).drive)
            or value.startswith(('~/', '~\\', 'file://')))
