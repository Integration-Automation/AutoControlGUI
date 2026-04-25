"""MCP tool registry for AutoControl.

The package is split into ``_base`` (value types and helpers),
``_handlers`` (adapter functions that bridge to the headless API), and
``_factories`` (per-domain ``MCPTool`` builders). Public consumers
should import only the names re-exported here.
"""
import os
from dataclasses import replace
from typing import Dict, List, Optional

from je_auto_control.utils.mcp_server.tools._base import (
    MCPContent, MCPTool, MCPToolAnnotations, read_only_env_flag,
)
from je_auto_control.utils.mcp_server.tools._factories import ALL_FACTORIES
from je_auto_control.utils.mcp_server.tools.plugin_tools import (
    make_plugin_tool, register_plugin_tools,
)


# Short, model-friendly aliases for the most-used tools. Each alias is
# registered as an additional MCPTool entry pointing at the same handler.
_DEFAULT_ALIASES: Dict[str, str] = {
    "click": "ac_click_mouse",
    "move_mouse": "ac_set_mouse_position",
    "mouse_pos": "ac_get_mouse_position",
    "scroll": "ac_mouse_scroll",
    "type": "ac_type_text",
    "press": "ac_press_key",
    "hotkey": "ac_hotkey",
    "screenshot": "ac_screenshot",
    "screen_size": "ac_screen_size",
    "find_image": "ac_locate_image_center",
    "find_text": "ac_locate_text",
    "click_text": "ac_click_text",
    "drag": "ac_drag",
    "list_windows": "ac_list_windows",
    "focus_window": "ac_focus_window",
    "wait_image": "ac_wait_for_image",
    "wait_pixel": "ac_wait_for_pixel",
    "diff_screens": "ac_diff_screenshots",
    "shell": "ac_shell",
}


def _aliases_enabled(explicit: Optional[bool]) -> bool:
    if explicit is not None:
        return bool(explicit)
    raw = os.environ.get("JE_AUTOCONTROL_MCP_ALIASES", "1")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _make_aliases(tools: List[MCPTool]) -> List[MCPTool]:
    by_name: Dict[str, MCPTool] = {tool.name: tool for tool in tools}
    aliases: List[MCPTool] = []
    for short, canonical in _DEFAULT_ALIASES.items():
        target = by_name.get(canonical)
        if target is None:
            continue
        aliases.append(replace(
            target, name=short,
            description=f"Alias for {canonical}: {target.description}",
        ))
    return aliases


def build_default_tool_registry(read_only: Optional[bool] = None,
                                aliases: Optional[bool] = None,
                                ) -> List[MCPTool]:
    """Return the full set of tools the MCP server exposes by default.

    :param read_only: when True, drop every tool whose annotations
        indicate it can mutate state. When None (default), the value
        of ``JE_AUTOCONTROL_MCP_READONLY`` is consulted, so deployments
        can pin the server in safe mode without code changes.
    :param aliases: when True, also register short model-friendly
        aliases (``click``, ``type``, ``screenshot`` ...) pointing at
        the canonical ``ac_*`` tools. Defaults to True; honour
        ``JE_AUTOCONTROL_MCP_ALIASES=0`` to disable globally.
    """
    enforce_read_only = (
        read_only_env_flag() if read_only is None else bool(read_only)
    )
    tools: List[MCPTool] = []
    for factory in ALL_FACTORIES:
        tools.extend(factory())
    if enforce_read_only:
        tools = [tool for tool in tools if tool.annotations.read_only]
    if _aliases_enabled(aliases):
        tools.extend(_make_aliases(tools))
    return tools


__all__ = [
    "MCPContent", "MCPTool", "MCPToolAnnotations",
    "build_default_tool_registry", "make_plugin_tool",
    "register_plugin_tools",
]
