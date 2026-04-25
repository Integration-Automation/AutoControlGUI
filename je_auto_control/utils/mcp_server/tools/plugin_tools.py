"""Wrap plugin-loaded ``AC_*`` callables as :class:`MCPTool` objects.

Plugins register arbitrary callables under ``AC_<name>`` via
:mod:`je_auto_control.utils.plugin_loader`. This module bridges that
dynamic catalogue into the live MCP server so a plugin a user drops
into their plugin directory shows up as a tool the model can call,
and the client gets notified to refresh its tool list.
"""
import inspect
from typing import Any, Callable, Dict, List

from je_auto_control.utils.mcp_server.tools._base import (
    DESTRUCTIVE, MCPTool, schema,
)


def make_plugin_tool(name: str,
                     handler: Callable[..., Any],
                     description: str = "") -> MCPTool:
    """Build an :class:`MCPTool` from a plugin callable's signature.

    The schema is derived from ``inspect.signature(handler)``: every
    parameter becomes a property, parameters without defaults are
    marked required, and a parameter named ``ctx`` is excluded so
    progress / cancellation context plumbing keeps working.
    """
    properties, required = _properties_from_signature(handler)
    tool_name = f"plugin_{name.lower()}" if not name.lower().startswith(
        "plugin_") else name.lower()
    docstring = (handler.__doc__ or "").strip().splitlines()[0] if handler.__doc__ else ""
    desc = description or docstring or f"Plugin command {name!r}."
    return MCPTool(
        name=tool_name,
        description=desc,
        input_schema=schema(properties, required=required or None),
        handler=handler,
        annotations=DESTRUCTIVE,
    )


def register_plugin_tools(server, commands: Dict[str, Callable[..., Any]]
                           ) -> List[str]:
    """Wrap each entry in ``commands`` and add it to ``server``.

    Returns the list of MCP tool names that were registered.
    """
    registered: List[str] = []
    for raw_name, handler in commands.items():
        tool = make_plugin_tool(raw_name, handler)
        server.register_tool(tool)
        registered.append(tool.name)
    return registered


_TYPE_FROM_ANNOTATION = {
    int: "integer", float: "number", bool: "boolean",
    str: "string", list: "array", dict: "object",
}


def _properties_from_signature(handler: Callable[..., Any]
                               ) -> tuple:
    """Return (properties, required) derived from the callable signature."""
    try:
        signature = inspect.signature(handler)
    except (TypeError, ValueError):
        return {}, []
    properties: Dict[str, Any] = {}
    required: List[str] = []
    for param in signature.parameters.values():
        if param.name == "ctx":
            continue
        if param.kind in (inspect.Parameter.VAR_POSITIONAL,
                          inspect.Parameter.VAR_KEYWORD):
            continue
        prop: Dict[str, Any] = {}
        annotation_type = _TYPE_FROM_ANNOTATION.get(param.annotation)
        if annotation_type is not None:
            prop["type"] = annotation_type
        properties[param.name] = prop
        if param.default is inspect.Parameter.empty:
            required.append(param.name)
    return properties, required


__all__ = ["make_plugin_tool", "register_plugin_tools"]
