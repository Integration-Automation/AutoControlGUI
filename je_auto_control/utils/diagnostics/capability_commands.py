"""Shared executor/MCP serialization of a passive capability snapshot."""
from je_auto_control.wrapper.capabilities import BackendContext, probe_capabilities


def probe_current_capabilities() -> dict[str, object]:
    """Inspect current prerequisites and existing local state without active diagnostics or caller-supplied grants."""
    return probe_capabilities(BackendContext.current()).to_dict()
