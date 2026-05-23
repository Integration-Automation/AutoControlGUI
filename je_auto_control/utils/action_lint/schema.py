"""Generate a JSON Schema (draft 2020-12) from the executor dispatch table."""
from __future__ import annotations

import inspect
import json
from typing import Any, Dict, List, Optional


_TYPE_TO_JSON_SCHEMA: Dict[Any, str] = {
    int: "integer",
    float: "number",
    bool: "boolean",
    str: "string",
    bytes: "string",
    list: "array",
    tuple: "array",
    dict: "object",
}


def _ac_callables() -> Dict[str, Any]:
    from je_auto_control.utils.executor.action_executor import executor
    return {
        name: fn for name, fn in executor.event_dict.items()
        if isinstance(name, str) and name.startswith("AC_") and callable(fn)
    }


def _annotation_to_json_type(annotation: Any) -> str:
    if annotation is inspect.Parameter.empty:
        return "string"
    base = getattr(annotation, "__origin__", None) or annotation
    return _TYPE_TO_JSON_SCHEMA.get(base, "string")


def _params_schema(callable_obj: Any) -> Dict[str, Any]:
    """Build the ``properties`` + ``required`` object for one AC command."""
    try:
        sig = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return {"type": "object", "additionalProperties": True}
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for name, param in sig.parameters.items():
        if name == "self" or param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        properties[name] = {"type": _annotation_to_json_type(param.annotation)}
        if param.default is inspect.Parameter.empty:
            required.append(name)
    schema: Dict[str, Any] = {
        "type": "object",
        "properties": properties,
        "additionalProperties": False,
    }
    if required:
        schema["required"] = required
    return schema


def build_action_schema(*, include_only: Optional[List[str]] = None,
                        ) -> Dict[str, Any]:
    """Return a JSON Schema for the AutoControl action file format.

    Action files are arrays of two-element tuples — ``[command_name,
    params_object]`` — so the schema is ``{"type": "array", "items":
    {"oneOf": [<per-command tuple>]}}``.
    """
    callables = _ac_callables()
    allowed = set(include_only) if include_only else None
    one_of: List[Dict[str, Any]] = []
    for name in sorted(callables):
        if allowed is not None and name not in allowed:
            continue
        params = _params_schema(callables[name])
        one_of.append({
            "type": "array",
            "prefixItems": [
                {"const": name},
                params,
            ],
            "minItems": 1,
            "maxItems": 2,
        })
    return {
        "$schema": "https://json-schema.org/draft/2020-12/schema",
        "title": "AutoControl Action JSON",
        "description": (
            "Auto-generated from the live je_auto_control executor "
            "dispatch table. Edit the executor to regenerate."
        ),
        "type": "array",
        "items": {"oneOf": one_of},
    }


def render_schema_json(*, indent: int = 2,
                       include_only: Optional[List[str]] = None,
                       ) -> str:
    """Serialise :func:`build_action_schema` to a JSON string."""
    return json.dumps(
        build_action_schema(include_only=include_only),
        indent=indent, ensure_ascii=False,
    )


__all__ = ["build_action_schema", "render_schema_json"]
