"""Passive backend capability MCP tool with no consent or input effects."""
from je_auto_control.utils.mcp_server.tools._base import MCPTool, READ_ONLY, schema


def _probe() -> dict[str, object]:
    from je_auto_control.wrapper.capabilities import probe_capabilities
    return probe_capabilities().to_dict()


def capability_tools() -> list[MCPTool]:
    """Expose the same passive snapshot as the headless and action surfaces."""
    return [MCPTool(
        "ac_probe_capabilities",
        "Report independent input/capture states, recovery instructions and XWayland scope; "
        "does not request consent, emit input, capture screens or load native libraries.",
        schema({}, required=[]), _probe, READ_ONLY,
    )]
