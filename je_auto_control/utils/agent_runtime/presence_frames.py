"""Closed, finite JSON byte frames for presence-only helper connections."""
from __future__ import annotations

import json
import math
import re
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError

_FIELDS = {'inspect': set(), 'acquire': set(), 'check': {'generation', 'lease_id'},
           'release': {'generation', 'lease_id'}}
_STATES = {'not_started', 'waiting_idle', 'monitoring', 'locked', 'unavailable'}


def encode_frame(value: dict) -> bytes:
    """Encode one bounded finite object without arbitrary object serialization."""
    if not isinstance(value, dict):
        raise AgentTaskError('physical presence frame must be an object')
    try:
        result = json.dumps(value, ensure_ascii=False, allow_nan=False, separators=(',', ':')).encode('utf-8')
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise AgentTaskError('physical presence frame must be finite UTF-8 JSON') from error
    if len(result) > 4096:
        raise AgentTaskError('physical presence frame exceeds4096bytes')
    return result


def _unique(pairs: list[tuple[str, Any]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise AgentTaskError('physical presence frame has duplicate fields')
        result[key] = value
    return result


def decode_frame(raw: bytes) -> dict:
    """Reject oversized/invalid/duplicate JSON before any presence operation is dispatched."""
    if not isinstance(raw, bytes) or len(raw) > 4096:
        raise AgentTaskError('physical presence frame must be at most4096bytes')
    try:
        value = json.loads(raw.decode('utf-8'), object_pairs_hook=_unique)
        encode_frame(value)
        return value
    except (TypeError, ValueError, UnicodeError, RecursionError) as error:
        raise AgentTaskError('physical presence frame is invalid') from error


def identifier(value: Any) -> str:
    """Validate one lower-case random source/lease/challenge identifier."""
    if not isinstance(value, str) or not re.fullmatch('[0-9a-f]{32}', value):
        raise AgentTaskError('physical presence identity is invalid')
    return value


def unsigned(value: Any, maximum: int, minimum: int = 0) -> int:
    """Require a bounded integer while excluding boolean aliases."""
    if isinstance(value, bool) or not isinstance(value, int) or not minimum <= value <= maximum:
        raise AgentTaskError('physical presence integer is invalid')
    return value


def _fields(value: Any, expected: set[str]) -> dict:
    if not isinstance(value, dict) or set(value) != expected:
        raise AgentTaskError('physical presence fields are invalid')
    return value


def presence_body(operation: str, value: dict) -> dict:
    """Share the source's exact finite operation/lease body contract."""
    if not isinstance(operation, str) or operation not in _FIELDS:
        raise AgentTaskError('unknown physical presence operation')
    body = _fields(value, _FIELDS[operation])
    for item in body.values():
        identifier(item)
    return dict(body)


def validate_request(value: dict) -> tuple[int, str, dict]:
    """Read a closed request with a bounded integer connection sequence."""
    value = _fields(value, {'request_id', 'operation', 'body'})
    sequence = unsigned(value['request_id'], (1 << 63) - 1, 1)
    body = presence_body(value['operation'], value['body'])
    return sequence, value['operation'], body


def _snapshot(value: dict, generation: str) -> None:
    value = _fields(value, {'state', 'idle_seconds', 'interactive', 'held', 'generation',
                            'revision', 'native_evidence'})
    if not isinstance(value['state'], str) or value['state'] not in _STATES:
        raise AgentTaskError('physical presence state is invalid')
    if identifier(value['generation']) != generation or value['native_evidence'] != 'not_recorded':
        raise AgentTaskError('physical presence source evidence is invalid')
    unsigned(value['revision'], (1 << 63) - 1)
    if not isinstance(value['interactive'], bool) or not isinstance(value['held'], bool):
        raise AgentTaskError('physical presence flags must be boolean')
    _idle(value['idle_seconds'])


def _idle(idle: Any) -> None:
    if isinstance(idle, bool) or not isinstance(idle, (int, float)) or idle < 0 or not math.isfinite(idle):
        raise AgentTaskError('physical presence idle is invalid')


def _result(operation: str, value: dict, generation: str) -> None:
    if operation in ('inspect', 'check'):
        _snapshot(value, generation)
    elif operation == 'acquire':
        body = presence_body('check', value)
        if body['generation'] != generation:
            raise AgentTaskError('physical presence source generation changed')
    elif operation == 'release':
        if _fields(value, {'released'})['released'] is not True:
            raise AgentTaskError('physical presence release was not confirmed')
    else:
        raise AgentTaskError('unknown physical presence response operation')


def validate_response(value: dict, operation: str, sequence: int, generation: str) -> dict:
    """Validate exact result/status/sequence and the actual live connection's generation."""
    try:
        value = _fields(value, {'request_id', 'status', 'result'})
        if unsigned(value['request_id'], (1 << 63) - 1, 1) != sequence:
            raise AgentTaskError('physical presence response sequence changed')
        identifier(generation)
        status = value['status']
        if not isinstance(status, str) or status not in {'ok', 'busy', 'lease_lost', 'source_lost'}:
            raise AgentTaskError('physical presence response status is invalid')
        if status == 'ok':
            _result(operation, value['result'], generation)
        elif value['result'] is not None:
            raise AgentTaskError('physical presence failure cannot carry permission')
        encode_frame(value)
        return dict(value)
    except (TypeError, ValueError, OverflowError) as error:
        raise AgentTaskError('physical presence response is invalid') from error
