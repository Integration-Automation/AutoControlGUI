"""MCP adapters for the executor, run history, recording and action files.

Same contract as :mod:`._handlers` -- normalise arguments and return values so
they survive the JSON-RPC boundary, with every project import lazy -- split out
by theme because ``_handlers.py`` is over the 750-line limit.
"""
import os
from typing import Any, Dict, List, Optional


# === Executor / history / recording =========================================

def execute_actions(actions: List[Any]) -> Dict[str, str]:
    from je_auto_control.utils.executor.action_executor import execute_action
    result = execute_action(actions)
    return {key: str(value) for key, value in result.items()}


def execute_action_file(file_path: str) -> Dict[str, str]:
    from je_auto_control.utils.executor.action_executor import execute_action
    from je_auto_control.utils.json.json_file import read_executable_action_json
    safe_path = os.path.realpath(os.fspath(file_path))
    result = execute_action(read_executable_action_json(safe_path))
    return {key: str(value) for key, value in result.items()}


def list_action_commands() -> List[str]:
    from je_auto_control.utils.executor.action_executor import executor
    return sorted(executor.known_commands())


def list_run_history(limit: int = 50,
                     source_type: Optional[str] = None
                     ) -> List[Dict[str, Any]]:
    from je_auto_control.utils.run_history.history_store import default_history_store
    rows = default_history_store.list_runs(limit=int(limit),
                                            source_type=source_type)
    return [{
        "id": row.id, "source_type": row.source_type,
        "source_id": row.source_id, "script_path": row.script_path,
        "started_at": str(row.started_at),
        "finished_at": str(row.finished_at),
        "status": row.status, "error_text": row.error_text,
        "duration_seconds": row.duration_seconds,
    } for row in rows]


def record_start() -> str:
    from je_auto_control.wrapper.auto_control_record import record
    record()
    return "recording started"


def record_stop() -> List[Any]:
    from je_auto_control.wrapper.auto_control_record import stop_record
    return stop_record() or []


def record_stop_timeline() -> List[Any]:
    from je_auto_control.wrapper.auto_control_record import (
        stop_record_timeline,
    )
    return stop_record_timeline() or []


def read_action_file(file_path: str) -> List[Any]:
    from je_auto_control.utils.json.json_file import read_action_json
    safe_path = os.path.realpath(os.fspath(file_path))
    return read_action_json(safe_path)


def write_action_file(file_path: str, actions: List[Any]) -> str:
    from je_auto_control.utils.json.json_file import write_action_json
    safe_path = os.path.realpath(os.fspath(file_path))
    parent = os.path.dirname(safe_path) or "."
    if not os.path.isdir(parent):
        raise ValueError(f"action-file directory does not exist: {parent}")
    write_action_json(safe_path, actions)
    return safe_path


def trim_actions(actions: List[Any], start: int = 0,
                 end: Optional[int] = None) -> List[Any]:
    from je_auto_control.utils.recording_edit.editor import trim_actions as _trim
    return _trim(actions, start=int(start),
                 end=None if end is None else int(end))


def adjust_delays(actions: List[Any], factor: float = 1.0,
                  clamp_ms: int = 0) -> List[Any]:
    from je_auto_control.utils.recording_edit.editor import adjust_delays as _adj
    return _adj(actions, factor=float(factor), clamp_ms=int(clamp_ms))


def scale_coordinates(actions: List[Any], x_factor: float = 1.0,
                      y_factor: float = 1.0) -> List[Any]:
    from je_auto_control.utils.recording_edit.editor import scale_coordinates as _scale
    return _scale(actions, x_factor=float(x_factor),
                  y_factor=float(y_factor))


def dedupe_moves(actions: List[Any],
                 move_commands: Optional[List[str]] = None) -> List[Any]:
    from je_auto_control.utils.recording_edit.editor import dedupe_moves as _dedupe
    return _dedupe(actions, move_commands=move_commands)


def merge_sleeps(actions: List[Any]) -> List[Any]:
    from je_auto_control.utils.recording_edit.editor import merge_sleeps as _merge
    return _merge(actions)
