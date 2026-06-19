"""Headless tests for MCP structured tool output (2025-06-18 spec):
optional outputSchema on a tool + structuredContent in the tools/call
result. Pure stdlib; no Qt imports."""
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server.tools import (
    MCPTool, build_default_tool_registry)

_EMPTY_INPUT = {"type": "object", "properties": {}}
_OUT = {"type": "object", "properties": {"value": {"type": "integer"}}}


def test_output_schema_in_descriptor():
    typed = MCPTool(name="t", description="d", input_schema=_EMPTY_INPUT,
                    handler=lambda: {"value": 1}, output_schema=_OUT)
    plain = MCPTool(name="p", description="d", input_schema=_EMPTY_INPUT,
                    handler=lambda: {"value": 1})
    assert typed.to_descriptor()["outputSchema"] == _OUT
    assert "outputSchema" not in plain.to_descriptor()


def test_structured_content_only_with_output_schema():
    typed = MCPTool(name="typed", description="d", input_schema=_EMPTY_INPUT,
                    handler=lambda: {"value": 42}, output_schema=_OUT)
    plain = MCPTool(name="plain", description="d", input_schema=_EMPTY_INPUT,
                    handler=lambda: {"value": 7})
    server = MCPServer(tools=[typed, plain])
    typed_result = server._handle_tools_call(2, {"name": "typed",
                                                 "arguments": {}})
    plain_result = server._handle_tools_call(3, {"name": "plain",
                                                 "arguments": {}})
    assert typed_result["isError"] is False
    assert typed_result["structuredContent"] == {"value": 42}
    assert "structuredContent" not in plain_result


def test_non_dict_result_has_no_structured_content():
    listy = MCPTool(name="listy", description="d", input_schema=_EMPTY_INPUT,
                    handler=lambda: [1, 2, 3], output_schema=_OUT)
    server = MCPServer(tools=[listy])
    result = server._handle_tools_call(2, {"name": "listy", "arguments": {}})
    assert "structuredContent" not in result      # only dict results qualify


def test_default_registry_tool_declares_output_schema():
    tool = {t.name: t for t in build_default_tool_registry()}["ac_validate_rows"]
    assert tool.output_schema is not None
    assert "ok" in tool.output_schema["properties"]
    assert "outputSchema" in tool.to_descriptor()
