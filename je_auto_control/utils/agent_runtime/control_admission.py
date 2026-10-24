"""Closed runtime stop requests share a bounded reserve separate from ordinary HTTP polling."""
from __future__ import annotations

from typing import Any

CONTROL_HEADER = 'X-AutoControl-Agent-Control'
CONTROL_PATHS = frozenset({'/agent/pause', '/agent/cancel', '/agent/stop_all', '/agent/shutdown'})


def control_request(path: str, body: Any) -> bool:
    """Recognize only existing stop operations; a marked DAG request cannot execute ordinary work."""
    if path in CONTROL_PATHS:
        return True
    if path != '/agent/dag' or not isinstance(body, dict) or set(body) != {'operation', 'request'}:
        return False
    request = body['request']
    if not isinstance(request, dict):
        return False
    if body['operation'] == 'pause_batch':
        return set(request) == {'batch_id'} and isinstance(request['batch_id'], str)
    return body['operation'] == 'local_task' and _node_pause(request)


def _node_pause(request: dict[str, Any]) -> bool:
    if set(request) != {'batch_id', 'attempt', 'node_id', 'operation', 'body'}:
        return False
    payload = request['body']
    return (request['operation'] == 'pause' and isinstance(payload, dict) and set(payload) == {'task_id'}
            and isinstance(payload['task_id'], str))
