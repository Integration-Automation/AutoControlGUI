"""Portable JSON definitions keep confidential literals and machine paths local."""
from __future__ import annotations

import json
import inspect
import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Dict, Mapping, Set
from urllib.parse import urlsplit

from je_auto_control.utils.action_journal.privacy import private_input, secret_values
from je_auto_control.utils.executor.action_redaction import is_sensitive_argument

from .models import ConfigSyncError

_SECRET_REFERENCE = re.compile(r'\$\{secrets\.[^{}]+\}')


def _local(value: object, key: str) -> bool:
    if isinstance(value, str) and _SECRET_REFERENCE.fullmatch(value):
        return False
    if is_sensitive_argument('', key):
        return True
    if not isinstance(value, str):
        return False
    if PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute():
        return True
    return _credential_url(value)


def _credential_url(value: str) -> bool:
    parsed = urlsplit(value)
    return bool(parsed.username or parsed.password or (parsed.scheme and (parsed.query or parsed.fragment)))


def _masked_references(raw: Any, cleaned: Any, path: str) -> Any:
    if isinstance(raw, dict) and set(raw) == {'$local'}:
        return dict(raw)
    if cleaned == '***':
        return {'$local': path}
    if isinstance(cleaned, dict) and isinstance(raw, dict):
        return {key: _masked_references(raw.get(key), value, f'{path}/{key}') for key, value in cleaned.items()}
    if isinstance(cleaned, list) and isinstance(raw, list):
        return [_masked_references(before, after, f'{path}/{index}')
                for index, (before, after) in enumerate(zip(raw, cleaned))]
    return cleaned


def _portable(value: Any, path: str, key: str = '') -> Any:
    if _local(value, key):
        return {'$local': path}
    if isinstance(value, dict):
        return _portable_mapping(value, path)
    if isinstance(value, list):
        if value and isinstance(value[0], str) and value[0].startswith('AC_'):
            return _portable_action(value, path)
        return [_portable(item, f'{path}/{index}') for index, item in enumerate(value)]
    return value


def _portable_mapping(value: Dict[str, Any], path: str) -> Dict[str, Any]:
    if '$local' in value:
        if set(value) != {'$local'} or not isinstance(value['$local'], str):
            raise ConfigSyncError('invalid local definition reference')
        return dict(value)
    return {name: _portable(item, f'{path}/{name}', name) for name, item in value.items()}


def _portable_action(value: list, path: str) -> list:
    named = _named_arguments(value[0], value[1] if len(value) > 1 else None)
    cleaned, reasons = private_input(value[0], named)
    if reasons and not all(reason == 'masked secret input requires an explicit secret reference' for reason in reasons):
        raise ConfigSyncError('script arguments cannot be safely exported')
    args = _masked_references(named, cleaned, f'{path}/1')
    portable = _portable(args, f'{path}/1')
    if value[0] == 'AC_write' and isinstance(named, dict) and isinstance(named.get('secret'), bool):
        portable['secret'] = named['secret']
    return [value[0], portable] if len(value) > 1 else [value[0]]


def _named_arguments(command: str, arguments: Any) -> Any:
    if not isinstance(arguments, list):
        return arguments
    # Signature lookup is lazy to preserve the executor's import graph.
    from je_auto_control.utils.executor.action_executor import executor  # pylint: disable=import-outside-toplevel
    handler = executor.event_dict.get(command)
    if handler is None:
        raise ConfigSyncError('unknown positional command cannot be safely synchronized')
    try:
        return dict(inspect.signature(handler).bind(*arguments).arguments)
    except (TypeError, ValueError) as error:
        raise ConfigSyncError('positional script arguments do not match their command') from error


def portable_definition(value: Mapping[str, object]) -> Dict[str, Any]:
    """Copy JSON data and replace sensitive fields or absolute paths with local references."""
    try:
        snapshot = _normalize_actions(json.loads(json.dumps(dict(value), allow_nan=False)))
        return _mask_known(_portable(snapshot, ''), secret_values('', snapshot, snapshot), '')
    except (TypeError, ValueError) as error:
        raise ConfigSyncError('definition must contain finite portable JSON data') from error


def _mask_known(value: Any, secrets: Set[str], path: str) -> Any:
    if isinstance(value, str):
        if not _SECRET_REFERENCE.fullmatch(value) and any(secret in value for secret in secrets):
            return {'$local': path}
        return value
    if isinstance(value, dict):
        return _mask_known_mapping(value, secrets, path)
    if isinstance(value, list):
        return [_mask_known(item, secrets, f'{path}/{index}') for index, item in enumerate(value)]
    return value


def _mask_known_mapping(value: Dict[str, Any], secrets: Set[str], path: str) -> Dict[str, Any]:
    if '$local' in value:
        return value
    if any(secret in key for key in value for secret in secrets):
        raise ConfigSyncError('definition key contains a confidential literal')
    return {key: _mask_known(item, secrets, f'{path}/{key}') for key, item in value.items()}


def _resolve(incoming: Any, current: Any) -> Any:
    if isinstance(incoming, dict):
        return _resolve_mapping(incoming, current)
    if isinstance(incoming, list):
        local_items = current if isinstance(current, list) else []
        return [_resolve(value, local_items[index] if index < len(local_items) else None)
                for index, value in enumerate(incoming)]
    return incoming


def _resolve_mapping(incoming: Dict[str, Any], current: Any) -> Any:
    if '$local' in incoming:
        if current is None:
            raise ConfigSyncError('definition requires an unresolved local reference')
        return current
    local = current if isinstance(current, dict) else {}
    result = {key: _resolve(value, local.get(key)) for key, value in incoming.items()}
    # A missing remote field cannot erase a destination's confidential setting.
    result.update({key: value for key, value in local.items() if key not in result and _local(value, key)})
    return result


def _normalize_actions(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _normalize_actions(item) for key, item in value.items()}
    if not isinstance(value, list):
        return value
    if value and isinstance(value[0], str) and value[0].startswith('AC_'):
        return _normalize_action(value)
    return [_normalize_actions(item) for item in value]


def _normalize_action(value: list) -> list:
    named = _named_arguments(value[0], value[1] if len(value) > 1 else None)
    if value[0] == 'AC_execute_journaled' and isinstance(named, dict) and isinstance(named.get('actions'), str):
        named['actions'] = json.loads(named['actions'])
    return [value[0], _normalize_actions(named)] if len(value) > 1 else [value[0]]


def resolve_definition(value: Mapping[str, object], local: Mapping[str, object]) -> Dict[str, Any]:
    """Resolve references only at the corresponding destination field, never by arbitrary path."""
    if portable_definition(value) != dict(value):
        raise ConfigSyncError('received definition contains a confidential literal or machine path')
    return _resolve(dict(value), _normalize_actions(dict(local)))
