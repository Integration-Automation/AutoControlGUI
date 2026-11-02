"""Closed owner-only line envelopes shared by private presence helpers, with no task authority fields."""
from __future__ import annotations

from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.presence_frames import decode_frame, encode_frame, identifier


def read_request(source: Any) -> dict | None:
    """Require a complete bounded line before accepting any owner operation."""
    line = source.readline(4097)
    if not line:
        return None
    if not line.endswith(b'\n'):
        raise AgentTaskError('physical presence owner frame is incomplete')
    request = decode_frame(line)
    if set(request) != {'id', 'operation', 'payload'}:
        raise AgentTaskError('physical presence owner envelope is invalid')
    identifier(request['id'])
    if not isinstance(request['operation'], str) or not isinstance(request['payload'], dict):
        raise AgentTaskError('physical presence owner operation is invalid')
    return request


def send_result(sink: Any, request_id: str, result: dict) -> None:
    """Return only a closed JSON result over the owner's existing stream."""
    _write(sink, {'id': request_id, 'result': result})


def send_error(sink: Any, request_id: str, error: BaseException) -> None:
    """Project only an error class, never raw input frames or sensitive values."""
    _write(sink, {'id': request_id, 'error': type(error).__name__, 'error_type': type(error).__name__})


def _write(sink: Any, packet: dict) -> None:
    sink.write(encode_frame(packet) + b'\n')
    sink.flush()
