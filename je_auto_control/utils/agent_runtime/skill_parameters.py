"""Explicit typed parameter slots modify data values without widening a skill's authority."""
from __future__ import annotations

import hashlib
import json
import re
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.models import detached

_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_]{0,63}")
_DATA = re.compile(r"/(?:actions/[0-9]+/(?:arguments/[^/]+(?:/[^/]+)*|expect_result|expect_not_result)|"
                   r"inputs/[^/]+(?:/[^/]+)*|"
                   r"success_criteria/[0-9]+/value)")


def digest(value: Any) -> str:
    """Hash a canonical finite JSON snapshot for immutable provenance comparisons."""
    return hashlib.sha256(json.dumps(detached(value), sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _slot(document: dict, pointer: str) -> tuple[Any, Any]:
    if not isinstance(pointer, str) or _DATA.fullmatch(pointer) is None or "~" in pointer:
        raise AgentTaskError("skill slots must address explicit action/input/criterion data values")
    pieces = pointer.split("/")[1:]
    current: Any = document
    try:
        for piece in pieces[:-1]:
            current = current[int(piece)] if isinstance(current, list) else current[piece]
        key: Any = int(pieces[-1]) if isinstance(current, list) else pieces[-1]
        current[key]
        return current, key
    except (IndexError, KeyError, TypeError, ValueError) as error:
        raise AgentTaskError("skill parameter path does not exist") from error


def _typed(value: Any, kind: str) -> Any:
    types: dict[str, Any] = {"string": str, "integer": int, "number": (int, float), "boolean": bool}
    if not isinstance(kind, str) or kind not in types or not isinstance(value, types[kind]):
        raise AgentTaskError("skill parameter value does not match its declared type")
    if kind in {"integer", "number"} and isinstance(value, bool):
        raise AgentTaskError("boolean is not a numeric skill parameter")
    if isinstance(value, str) and (len(value) > 8192 or "${" in value):
        raise AgentTaskError("skill parameter strings must be bounded literal data")
    return detached(value)


def parameter_schema(spec: dict, slots: Any) -> dict:
    """Freeze explicit primitive defaults from a recorded flow; reject duplicate/overlapping slots."""
    if not isinstance(slots, dict) or len(slots) > 50:
        raise AgentTaskError("skill parameters must be an object with at most fifty entries")
    schema: dict[str, Any] = {}
    occupied: list[str] = []
    for name, definition in slots.items():
        paths = _definition(name, definition)
        defaults = [_typed(parent[key], definition["type"]) for parent, key in (_slot(spec, path) for path in paths)]
        if any(value != defaults[0] for value in defaults):
            raise AgentTaskError("all paths for one skill parameter must have the same default")
        for path in paths:
            if _overlaps(path, occupied):
                raise AgentTaskError("skill parameter paths overlap")
            occupied.append(path)
        schema[name] = {**definition, "default": defaults[0]}
    return schema


def _definition(name: Any, definition: Any) -> list[str]:
    if not isinstance(name, str) or _NAME.fullmatch(name) is None or not isinstance(definition, dict):
        raise AgentTaskError("invalid skill parameter name or definition")
    if set(definition) != {"type", "paths"}:
        raise AgentTaskError("skill parameter definitions require type and paths")
    paths = definition["paths"]
    if not isinstance(paths, list) or not 1 <= len(paths) <= 50:
        raise AgentTaskError("skill parameters require bounded explicit paths")
    return paths


def _overlaps(path: str, occupied: list[str]) -> bool:
    return any(path == other or path.startswith(other + "/") or other.startswith(path + "/") for other in occupied)


def instantiate(spec: dict, schema: dict, parameters: Any) -> dict:
    """Apply only named literal parameters to detached, explicitly declared data slots."""
    if not isinstance(parameters, dict) or set(parameters) - set(schema):
        raise AgentTaskError("unknown skill parameters")
    result = detached(spec)
    for name, definition in schema.items():
        value = _typed(parameters.get(name, definition["default"]), definition["type"])
        for pointer in definition["paths"]:
            parent, key = _slot(result, pointer)
            parent[key] = value
    return result


def repair_data(spec: dict, changes: Any) -> dict:
    """Produce a detached repair proposal limited to existing semantic selector data."""
    if not isinstance(changes, list) or not 1 <= len(changes) <= 100:
        raise AgentTaskError("repair requires between one and one hundred semantic selector changes")
    result = detached(spec)
    for change in changes:
        if not isinstance(change, dict) or set(change) != {"path", "value"}:
            raise AgentTaskError("repair changes require path and value")
        pointer = change["path"]
        if not isinstance(pointer, str) or re.fullmatch(
                r"/actions/[0-9]+/arguments/selector/(?:name|role|automation_id)", pointer) is None:
            raise AgentTaskError("repair may change only existing semantic selector names/roles/IDs")
        parent, key = _slot(result, pointer)
        parent[key] = _typed(change["value"], "string")
    return result
