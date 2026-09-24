"""Generate a JSON Schema (draft 2020-12) from the executor dispatch table."""
from __future__ import annotations

import inspect
import json
import typing
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


def _block_commands() -> Dict[str, Any]:
    from je_auto_control.utils.executor.action_executor import executor
    return dict(executor._block_commands)  # noqa: SLF001  # reason: the dispatch table's other half


def _json_type(annotation: Any) -> Optional[Any]:
    """The JSON Schema ``type`` for an annotation, or ``None`` for "anything".

    Unions (``int | None``, ``Optional[str]``) become a list of types. An
    unknown or missing annotation places no constraint: it used to become
    ``"string"``, so ``{"x": 100}`` for AC_click_mouse failed the schema.
    """
    if annotation is inspect.Parameter.empty or annotation is Any:
        return None
    if annotation is type(None):
        return "null"
    if _is_union(annotation):
        return _union_type(typing.get_args(annotation))
    base = typing.get_origin(annotation) or annotation
    return _TYPE_TO_JSON_SCHEMA.get(base)


def _union_type(members: Any) -> Optional[List[str]]:
    """A list of JSON types for a union, or ``None`` if one member is unconstrained."""
    types = [_json_type(member) for member in members]
    if any(kind is None for kind in types):
        return None
    return sorted({kind for kind in types if isinstance(kind, str)})


def _is_union(annotation: Any) -> bool:
    origin = typing.get_origin(annotation)
    return origin is typing.Union or type(annotation).__name__ == "UnionType"


def _resolved_hints(callable_obj: Any) -> Dict[str, Any]:
    """Annotations with postponed (string) ones evaluated; empty if they cannot be."""
    try:
        return typing.get_type_hints(callable_obj)
    except (NameError, TypeError, AttributeError):
        return {}


def _params_schema(callable_obj: Any) -> Dict[str, Any]:
    """Build the ``properties`` + ``required`` object for one AC command."""
    try:
        sig = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return {"type": "object", "additionalProperties": True}
    properties: Dict[str, Any] = {}
    required: List[str] = []
    hints = _resolved_hints(callable_obj)
    for name, param in sig.parameters.items():
        if name == "self" or param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        kind = _json_type(hints.get(name, param.annotation))
        properties[name] = {} if kind is None else {"type": kind}
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


def _block_params_schema(name: str) -> Dict[str, Any]:
    """A block command's arguments: its required keys, anything else allowed."""
    from je_auto_control.utils.executor.action_schema import BLOCK_REQUIRED_KEYS
    schema: Dict[str, Any] = {"type": "object", "additionalProperties": True}
    required = list(BLOCK_REQUIRED_KEYS.get(name, ()))
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
    blocks = _block_commands()
    allowed = set(include_only) if include_only else None
    one_of: List[Dict[str, Any]] = []
    for name in sorted(set(callables) | set(blocks)):
        if allowed is not None and name not in allowed:
            continue
        # Block commands (AC_sleep, AC_loop, AC_set_var...) are not in the
        # dispatch table; they were missing, so no action file using one
        # could validate.
        params = (_block_params_schema(name) if name in blocks
                  else _params_schema(callables[name]))
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
