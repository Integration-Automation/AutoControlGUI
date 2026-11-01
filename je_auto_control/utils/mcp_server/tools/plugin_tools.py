"""Wrap plugin-loaded ``AC_*`` callables as :class:`MCPTool` objects.

Plugins register arbitrary callables under ``AC_<name>`` via
:mod:`je_auto_control.utils.plugin_loader`. This module bridges that
dynamic catalogue into the live MCP server so a plugin a user drops
into their plugin directory shows up as a tool the model can call,
and the client gets notified to refresh its tool list.

A plugin tool is registered as mutating (``DESTRUCTIVE``) unless the plugin
says otherwise: a callable whose ``mcp_read_only`` attribute is exactly
``True`` is registered read-only, which is what lets it run on a read-only
server and makes it need only ``read_screen`` under RBAC. That is the plugin
author's word and nothing checks it -- the server cannot tell what arbitrary
Python does -- so each declaration is logged when the tool is registered.
Anything other than the boolean ``True`` (``"yes"``, ``1``, a callable, an
attribute that raises) leaves the tool mutating.
"""
import inspect
from typing import Any, Callable, Dict, List

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.mcp_server.tools._base import (
    DESTRUCTIVE, MCPTool, MCPToolAnnotations, schema,
)

#: Attribute a plugin sets to ``True`` on a callable to declare it read-only.
PLUGIN_READ_ONLY_ATTRIBUTE = "mcp_read_only"

#: Annotations of a plugin tool that declared itself read-only. Only the
#: read-only hint is the plugin's claim; idempotence was not declared.
PLUGIN_READ_ONLY = MCPToolAnnotations(read_only=True)

_UNSET = object()


def plugin_declares_read_only(handler: Callable[..., Any]) -> bool:
    """Whether ``handler`` carries ``mcp_read_only = True``, and nothing looser.

    The declaration is trusted, not verified. A value that is present but is
    not a boolean is logged and treated as no declaration, so a typo fails
    towards the tool staying mutating.
    """
    try:
        declared = getattr(handler, PLUGIN_READ_ONLY_ATTRIBUTE, _UNSET)
    except Exception as error:  # noqa: BLE001  # reason: untrusted plugin object; raising means undeclared
        autocontrol_logger.warning(
            "plugin %r: reading %s raised %r; the tool stays mutating",
            getattr(handler, "__name__", handler), PLUGIN_READ_ONLY_ATTRIBUTE, error)
        return False
    if declared is True:
        return True
    if declared is not _UNSET and declared is not False:
        autocontrol_logger.warning(
            "plugin %r: %s must be the boolean True, not %s; the tool stays mutating",
            getattr(handler, "__name__", handler), PLUGIN_READ_ONLY_ATTRIBUTE,
            type(declared).__name__)
    return False


def log_read_only_declaration(tool: MCPTool) -> None:
    """Log that the plugin tool ``tool`` is registered on its own read-only claim."""
    if tool.annotations.read_only:
        autocontrol_logger.warning(
            "plugin tool %r is registered read-only because its plugin declared "
            "%s=True; the declaration is trusted, not verified",
            tool.name, PLUGIN_READ_ONLY_ATTRIBUTE)


def make_plugin_tool(name: str,
                     handler: Callable[..., Any],
                     description: str = "") -> MCPTool:
    """Build an :class:`MCPTool` from a plugin callable's signature.

    The schema is derived from ``inspect.signature(handler)``: every
    parameter becomes a property, parameters without defaults are
    marked required, and a parameter named ``ctx`` is excluded so
    progress / cancellation context plumbing keeps working. The tool is
    mutating unless :func:`plugin_declares_read_only` says otherwise.
    """
    properties, required = _properties_from_signature(handler)
    tool_name = f"plugin_{name.lower()}" if not name.lower().startswith(
        "plugin_") else name.lower()
    # A whitespace-only docstring strips to "" whose .splitlines() is empty,
    # so index [0] would raise IndexError — guard on the stripped text.
    stripped_doc = (handler.__doc__ or "").strip()
    docstring = stripped_doc.splitlines()[0] if stripped_doc else ""
    desc = description or docstring or f"Plugin command {name!r}."
    return MCPTool(
        name=tool_name,
        description=desc,
        input_schema=schema(properties, required=required or None),
        handler=handler,
        annotations=PLUGIN_READ_ONLY if plugin_declares_read_only(handler) else DESTRUCTIVE,
    )


def register_plugin_tools(server, commands: Dict[str, Callable[..., Any]]
                           ) -> List[str]:
    """Wrap each entry in ``commands`` and add it to ``server``.

    Returns the list of MCP tool names that were registered. A tool whose
    plugin declared it read-only is logged by name.
    """
    registered: List[str] = []
    for raw_name, handler in commands.items():
        tool = make_plugin_tool(raw_name, handler)
        server.register_tool(tool)
        log_read_only_declaration(tool)
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


__all__ = [
    "PLUGIN_READ_ONLY", "PLUGIN_READ_ONLY_ATTRIBUTE", "log_read_only_declaration",
    "make_plugin_tool", "plugin_declares_read_only", "register_plugin_tools",
]
