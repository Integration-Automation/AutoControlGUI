"""Generate an MCP registry ``server.json`` manifest for AutoControl.

The MCP registry (https://registry.modelcontextprotocol.io) lists servers
described by a ``server.json`` document. Publishing one makes the
AutoControl MCP server discoverable and installable by MCP-aware agents
and IDEs. This module builds that manifest from the live package metadata
and (optionally) the real tool registry, so the advertised capabilities
never drift from what the server actually exposes.

Pure standard library; imports no ``PySide6``.
"""
import json
from importlib import metadata
from pathlib import Path
from typing import Any, Dict, List

_SCHEMA_URL = ("https://static.modelcontextprotocol.io/schemas/"
               "2025-09-29/server.schema.json")
_SERVER_NAME = "io.github.intergration-automation-testing/autocontrol"
_REPO_URL = "https://github.com/Intergration-Automation-Testing/AutoControl"
_PYPI_NAME = "je_auto_control"
_DEFAULT_VERSION = "0.0.189"
_DESCRIPTION = (
    "Cross-platform GUI automation: mouse/keyboard control, image and OCR "
    "recognition, native-UI (accessibility) control, and action scripting — "
    "exposed as MCP tools.")


def _package_version() -> str:
    """Best-effort installed version, falling back to a pinned default."""
    try:
        return metadata.version(_PYPI_NAME)
    except metadata.PackageNotFoundError:
        return _DEFAULT_VERSION


def _tool_names() -> List[str]:
    """Sorted names of every tool the default MCP registry exposes."""
    from je_auto_control.utils.mcp_server.tools import (
        build_default_tool_registry)
    return sorted(tool.name for tool in build_default_tool_registry())


def build_server_manifest(*, name: str = _SERVER_NAME,
                          version: str = "",
                          description: str = _DESCRIPTION,
                          repository_url: str = _REPO_URL,
                          pypi_name: str = _PYPI_NAME,
                          include_tools: bool = False) -> Dict[str, Any]:
    """Return an MCP registry ``server.json`` manifest as a dict.

    ``version`` defaults to the installed package version. With
    ``include_tools`` the live tool list is embedded under ``_meta`` for
    discovery without changing the registry-valid core fields.
    """
    resolved = version or _package_version()
    manifest: Dict[str, Any] = {
        "$schema": _SCHEMA_URL,
        "name": name,
        "description": description,
        "version": resolved,
        "repository": {"url": repository_url, "source": "github"},
        "packages": [{
            "registryType": "pypi",
            "identifier": pypi_name,
            "version": resolved,
            "transport": {"type": "stdio"},
        }],
    }
    if include_tools:
        names = _tool_names()
        manifest["_meta"] = {name: {"toolCount": len(names), "tools": names}}
    return manifest


def write_server_manifest(path: str = "server.json", *,
                          include_tools: bool = False,
                          **kwargs: Any) -> str:
    """Write a ``server.json`` manifest to ``path``; return the resolved path.

    Extra keyword arguments are forwarded to :func:`build_server_manifest`.
    """
    manifest = build_server_manifest(include_tools=include_tools, **kwargs)
    target = Path(path)
    target.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    return str(target.resolve())
