"""Tiny JSON-Schema validator covering the subset MCP tools use here.

The default tool registry only references a handful of schema
features — ``type``, ``properties``, ``required``, ``items``,
``enum`` — so a 50-line validator is enough and avoids pulling in
``jsonschema`` as a runtime dependency. The validator intentionally
returns the first violation it finds rather than collecting them
all, which keeps the JSON-RPC error message short.
"""
from typing import Any, Dict, Optional

_TYPE_CHECKS = {
    "object": lambda value: isinstance(value, dict),
    "array": lambda value: isinstance(value, list),
    "string": lambda value: isinstance(value, str),
    "boolean": lambda value: isinstance(value, bool),
    # JSON Schema integer accepts bool subclass; we exclude bool below.
    "integer": lambda value: isinstance(value, int) and not isinstance(value, bool),
    "number": lambda value: (
        isinstance(value, (int, float)) and not isinstance(value, bool)
    ),
    "null": lambda value: value is None,
}


def validate_arguments(schema: Dict[str, Any],
                       arguments: Dict[str, Any]) -> Optional[str]:
    """Return the first schema violation as a message, or ``None`` if valid."""
    return _validate(schema, arguments, path="$")


def _validate(schema: Dict[str, Any], value: Any, path: str) -> Optional[str]:
    expected = schema.get("type")
    if expected is not None:
        check = _TYPE_CHECKS.get(expected)
        if check is None:
            return None  # unknown type — nothing we can check
        if not check(value):
            return f"{path}: expected {expected}, got {type(value).__name__}"
    enum = schema.get("enum")
    if enum is not None and value not in enum:
        return f"{path}: must be one of {enum!r}"
    if expected == "object":
        return _validate_object(schema, value, path)
    if expected == "array":
        return _validate_array(schema, value, path)
    return None


def _validate_object(schema: Dict[str, Any], value: Dict[str, Any],
                     path: str) -> Optional[str]:
    required = schema.get("required") or []
    for name in required:
        if name not in value:
            return f"{path}: missing required property {name!r}"
    properties = schema.get("properties") or {}
    for name, child_value in value.items():
        child_schema = properties.get(name)
        if child_schema is None:
            continue
        error = _validate(child_schema, child_value, f"{path}.{name}")
        if error is not None:
            return error
    return None


def _validate_array(schema: Dict[str, Any], value: list,
                    path: str) -> Optional[str]:
    item_schema = schema.get("items")
    if not isinstance(item_schema, dict):
        return None
    for index, item in enumerate(value):
        error = _validate(item_schema, item, f"{path}[{index}]")
        if error is not None:
            return error
    return None


__all__ = ["validate_arguments"]
