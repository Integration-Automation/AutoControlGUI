"""The SDK, executor, Builder and read-only MCP expose the same passive capability snapshot."""
import json

import pytest

import je_auto_control as ac
from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.rbac import AuthorizationContext, Capability, Role, authorization_scope
from je_auto_control.utils.rbac.policy import capability_for_command, capability_for_tool
from je_auto_control.wrapper.capabilities import BackendContext, probe_capabilities


@pytest.fixture
def current(monkeypatch):
    context = BackendContext('linux', {'XDG_SESSION_TYPE': 'wayland',
                                      'JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND': 'cli'}, frozenset({'grim'}))
    monkeypatch.setattr(BackendContext, 'current', classmethod(lambda _cls: context))
    return context


def test_sdk_exposes_the_required_typed_capability_api(current):
    names = {'BackendContext', 'CapabilityStatus', 'CapabilitySnapshot', 'probe_capabilities'}
    assert names <= set(ac.__all__)
    assert ac.probe_capabilities(current) == probe_capabilities(current)


def test_versioned_headless_sdk_exposes_the_same_capability_contract(current):
    from je_auto_control import api
    from je_auto_control.api import core
    assert set(api.__all__) == set(core.__all__)
    for name in api.__all__:
        assert getattr(api, name) is getattr(core, name)
    assert api.BackendContext is ac.BackendContext
    assert api.CapabilityStatus is ac.CapabilityStatus
    assert api.CapabilitySnapshot is ac.CapabilitySnapshot
    assert api.probe_capabilities(current) == ac.probe_capabilities(current)


def test_executor_and_read_only_mcp_share_the_sdk_snapshot_without_accepting_supplied_context(current):
    expected = probe_capabilities(current).to_dict()
    command = ac.executor.event_dict['AC_probe_capabilities']
    tools = {tool.name: tool for tool in build_default_tool_registry(read_only=True)}
    tool = tools['ac_probe_capabilities']
    assert command() == tool.invoke({}) == expected
    assert tool.annotations.read_only and tool.output_schema['type'] == 'object'
    assert tool.input_schema.get('additionalProperties') is False
    with pytest.raises(TypeError):
        tool.invoke({'context': {'input_state': 'available'}})


def test_builder_and_rbac_declare_passive_capabilities_as_read_only():
    spec = COMMAND_SPECS['AC_probe_capabilities']
    assert not spec.fields
    assert capability_for_command('AC_probe_capabilities') == Capability.READ_SCREEN
    assert capability_for_tool('ac_probe_capabilities', True) == Capability.READ_SCREEN


def test_read_only_viewer_can_use_the_real_executor_and_jsonrpc_dispatcher(current, tmp_path):
    from je_auto_control.utils.mcp_server.audit import AuditLogger
    from je_auto_control.utils.mcp_server.server import MCPServer
    tools = [tool for tool in build_default_tool_registry(read_only=True) if tool.name == 'ac_probe_capabilities']
    server = MCPServer(tools=tools, audit_logger=AuditLogger(str(tmp_path/'audit.jsonl')))
    request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
               'params': {'name': 'ac_probe_capabilities', 'arguments': {}}}
    expected = probe_capabilities(current).to_dict()
    with authorization_scope(AuthorizationContext('reader', Role.VIEWER)):
        record = ac.execute_action([['AC_probe_capabilities']])
        response = json.loads(server.handle_line(json.dumps(request)))
    assert expected in record.values()
    assert response['result']['isError'] is False
    assert response['result']['structuredContent'] == expected
    request['params']['arguments'] = {'context': {'input_state': 'available'}}
    refused = json.loads(server.handle_line(json.dumps(request)))
    # Existing MCP contract: schema violations are tool failures, not malformed JSON-RPC envelopes.
    assert refused['result']['isError'] is True
    assert refused['result']['content'][0]['text'].startswith('Invalid arguments for ac_probe_capabilities:')
