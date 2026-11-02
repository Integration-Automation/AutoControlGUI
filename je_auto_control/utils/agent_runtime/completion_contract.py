"""Shared completion evidence and retirement checks without service or DAG transport dependencies."""
from __future__ import annotations

import json
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError

_BINDING_FIELDS = {'contract', 'source_task', 'source_snapshot', 'effect_task', 'effect_snapshot',
                   'reviewer', 'source_owner', 'effect_owner'}


def decode_private_object(value: str, message: str, *, error_type: type[AgentTaskError] = AgentTaskError) -> dict:
    """Decode a private JSON object with a typed refusal before any task capability is selected."""
    try:
        details = json.loads(value)
    except (ValueError, TypeError) as error:
        raise error_type(message) from error
    if not isinstance(details, dict):
        raise error_type(message)
    return details


def decode_completion_binding(value: str) -> dict:
    """Reject corrupt private completion markers without converting them to ordinary task admission."""
    details = decode_private_object(value, 'invalid private completion binding')
    if set(details) != _BINDING_FIELDS:
        raise AgentTaskError('invalid private completion binding')
    version = details['contract']
    if not isinstance(version, int) or isinstance(version, bool) or version != 1:
        raise AgentTaskError('invalid private completion binding version')
    if not all(isinstance(details[key], dict) for key in ('reviewer', 'source_owner', 'effect_owner')):
        raise AgentTaskError('invalid private completion principals')
    return details


def validate_recorded_completion(reply: dict[str, Any], spec: Mapping[str, Any]) -> None:
    """Require succeeded state and exact independent completion/retirement evidence."""
    if reply.get('state') != 'succeeded':
        raise AgentTaskError('recorded task has not succeeded')
    require_completion(reply, spec)


def require_completion(reply: dict[str, Any], spec: Mapping[str, Any]) -> None:
    """Match every pinned criterion and exact retirement flag before accepting completion."""
    metadata, reports = reply.get('metadata'), reply.get('verification')
    if not isinstance(metadata, dict) or not isinstance(reports, list):
        raise AgentTaskError('completion evidence is missing')
    version = metadata.get('completion_contract')
    # pylint: disable-next=unidiomatic-typecheck  # reason: only an exact JSON integer attests retirement
    if type(version) is not int or version != 1 or metadata.get('input_released') is not True:
        raise AgentTaskError('completion retirement contract is unconfirmed')
    criteria = spec['success_criteria']
    if len(reports) != len(criteria):
        raise AgentTaskError('completion criteria count changed')
    for report, clause in zip(reports, criteria):
        _require_clause(report, clause)


def _require_clause(report: Any, clause: Mapping[str, Any]) -> None:
    if not isinstance(report, dict) or report.get('kind') != clause['kind'] or report.get('status') != 'passed':
        raise AgentTaskError('completion criteria were not independently confirmed')
