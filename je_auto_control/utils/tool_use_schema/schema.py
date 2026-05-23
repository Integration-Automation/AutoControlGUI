"""Introspect AC_* commands and emit Anthropic / OpenAI tool schemas."""
from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

_TYPE_TO_JSON_SCHEMA = {
    int: "integer",
    float: "number",
    bool: "boolean",
    str: "string",
    bytes: "string",
    list: "array",
    tuple: "array",
    dict: "object",
}


def _executor():
    """Lazy import to keep this module dependency-free at import time."""
    from je_auto_control.utils.executor.action_executor import executor
    return executor


def _ac_callables() -> Dict[str, Callable[..., Any]]:
    """Map ``AC_*`` command names to the underlying callable."""
    return {
        name: fn for name, fn in _executor().event_dict.items()
        if isinstance(name, str) and name.startswith("AC_")
        and callable(fn)
    }


def infer_parameters(callable_obj: Callable[..., Any]
                     ) -> Tuple[Dict[str, Any], List[str]]:
    """Build a JSON-schema ``properties`` dict + ``required`` list.

    Falls back to ``string`` for parameters with no type hint — the
    model can still call them, just without type guarantees.
    """
    try:
        sig = inspect.signature(callable_obj)
    except (TypeError, ValueError):
        return {}, []
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for name, param in sig.parameters.items():
        if name == "self" or param.kind in (
                inspect.Parameter.VAR_POSITIONAL,
                inspect.Parameter.VAR_KEYWORD,
        ):
            continue
        json_type = _annotation_to_json_type(param.annotation)
        prop: Dict[str, Any] = {"type": json_type}
        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            # JSON-schema doesn't require a ``default`` field but
            # including it helps the model pick sensible inputs.
            if param.default is not None:
                prop["default"] = param.default
        properties[name] = prop
    return properties, required


def _annotation_to_json_type(annotation: Any) -> str:
    """Best-effort map a Python type annotation to a JSON-schema type."""
    if annotation is inspect.Parameter.empty:
        return "string"
    base = getattr(annotation, "__origin__", None) or annotation
    return _TYPE_TO_JSON_SCHEMA.get(base, "string")


def _description_for(name: str, callable_obj: Callable[..., Any]) -> str:
    """One-line summary used as the tool's ``description``."""
    doc = inspect.getdoc(callable_obj) or ""
    if doc:
        return doc.splitlines()[0]
    return f"AutoControl command {name}"


def export_anthropic_tools(*, only: Optional[List[str]] = None,
                           ) -> List[Dict[str, Any]]:
    """Return the AC_* commands as Anthropic ``tools`` payload list."""
    allowed = set(only) if only else None
    tools: List[Dict[str, Any]] = []
    for name, fn in sorted(_ac_callables().items()):
        if allowed is not None and name not in allowed:
            continue
        properties, required = infer_parameters(fn)
        schema = {
            "type": "object",
            "properties": properties,
        }
        if required:
            schema["required"] = required
        tools.append({
            "name": name,
            "description": _description_for(name, fn),
            "input_schema": schema,
        })
    return tools


def export_openai_tools(*, only: Optional[List[str]] = None,
                        ) -> List[Dict[str, Any]]:
    """Return the AC_* commands as OpenAI ``tools`` payload list."""
    allowed = set(only) if only else None
    tools: List[Dict[str, Any]] = []
    for name, fn in sorted(_ac_callables().items()):
        if allowed is not None and name not in allowed:
            continue
        properties, required = infer_parameters(fn)
        parameters = {
            "type": "object",
            "properties": properties,
        }
        if required:
            parameters["required"] = required
        tools.append({
            "type": "function",
            "function": {
                "name": name,
                "description": _description_for(name, fn),
                "parameters": parameters,
            },
        })
    return tools


def run_tool_call(name: str, arguments: Mapping[str, Any]) -> Any:
    """Dispatch a model's ``tool_use`` request through the executor.

    Returns the callable's return value verbatim — typically a
    JSON-serialisable dict that the agent loop can feed back to the
    model as the tool's result.
    """
    callables = _ac_callables()
    if name not in callables:
        raise ValueError(f"unknown AC command: {name!r}")
    fn = callables[name]
    return fn(**dict(arguments or {}))


__all__ = [
    "export_anthropic_tools", "export_openai_tools",
    "infer_parameters", "run_tool_call",
]
