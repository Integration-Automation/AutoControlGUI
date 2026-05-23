"""Language Server Protocol implementation for AutoControl JSON files.

The package exposes a minimal LSP server (stdlib JSON-RPC over stdio)
that an editor can launch to get completion and hover for ``AC_*``
action commands. No external LSP framework dependency.
"""
from autocontrol_lsp.server.commands import (
    discover_actions, get_action_doc, known_action_names,
)
from autocontrol_lsp.server.handlers import (
    handle_completion, handle_hover, handle_initialize,
)

__all__ = [
    "discover_actions", "get_action_doc", "known_action_names",
    "handle_completion", "handle_hover", "handle_initialize",
]
