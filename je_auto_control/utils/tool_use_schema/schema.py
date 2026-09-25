"""Introspect AC_* commands and emit Anthropic / OpenAI tool schemas."""
from __future__ import annotations

import inspect
from typing import Any, Callable, Dict, List, Mapping, Optional, Tuple

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
    from je_auto_control.utils.action_lint.schema import _json_type, _resolved_hints
    properties: Dict[str, Any] = {}
    required: List[str] = []
    hints = _resolved_hints(callable_obj)
    for name, param in sig.parameters.items():
        hint = hints.get(name, param.annotation)
        if _not_for_the_model(name, param, hint):
            continue
        # Resolved, unions included: postponed annotations reached here as
        # strings, so Optional[int] -- AC_click_mouse's x -- was "string".
        json_type = _json_type(hint)
        prop: Dict[str, Any] = {} if json_type is None else {"type": json_type}
        if param.default is inspect.Parameter.empty:
            required.append(name)
        else:
            # JSON-schema doesn't require a ``default`` field but
            # including it helps the model pick sensible inputs.
            if param.default is not None:
                prop["default"] = param.default
        properties[name] = prop
    return properties, required


def _not_for_the_model(name: str, param: inspect.Parameter, hint: Any) -> bool:
    """Parameters a tool call must not set: ``self``, ``*args``, private ones, callbacks.

    ``AC_execute_action``'s ``_validated`` let the model skip validation (a
    stray AC_break then escaped the agent loop), and ``step_callback`` is a
    function no JSON can give.
    """
    if name == "self" or name.startswith("_"):
        return True
    if param.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
        return True
    return _is_callable_type(hint)


def _is_callable_type(hint: Any) -> bool:
    """Whether ``hint`` is ``Callable`` or a union holding one."""
    import collections.abc
    import typing
    origin = typing.get_origin(hint)
    if hint is collections.abc.Callable or origin is collections.abc.Callable:
        return True
    return any(_is_callable_type(arg) for arg in typing.get_args(hint)) if origin is typing.Union else False


def _description_for(name: str, callable_obj: Callable[..., Any]) -> str:
    """One-line summary used as the tool's ``description``."""
    doc = inspect.getdoc(callable_obj) or ""
    if doc:
        return doc.splitlines()[0]
    return f"AutoControl command {name}"


def _allowed_names(only: Optional[List[str]]) -> Optional[set]:
    """``None`` exports every command; any list, even an empty one, is the whole set.

    An empty list used to export every command, so a filter that matched
    nothing handed the agent all of them, AC_shell_command included.
    """
    return None if only is None else set(only)


def export_anthropic_tools(*, only: Optional[List[str]] = None,
                           ) -> List[Dict[str, Any]]:
    """Return the AC_* commands as Anthropic ``tools`` payload list."""
    allowed = _allowed_names(only)
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
    allowed = _allowed_names(only)
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
