"""One scoped token controls the existing SDK, executor and active MCP diagnostic path."""
from concurrent.futures import CancelledError
from contextvars import copy_context
import json
import threading

import pytest

import je_auto_control as ac
from je_auto_control import api
from je_auto_control.utils.diagnostics import diagnostics
from je_auto_control.utils.exception import cancellation
from je_auto_control.utils.mcp_server.context import OperationCancelledError, ToolCallContext
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.rbac import AuthorizationContext, Capability, Role, authorization_scope
from je_auto_control.utils.rbac.policy import capability_for_command


def _scope(token):
    return cancellation.cancellation_scope(token)


def test_cancellation_primitives_are_shared_by_both_public_sdk_namespaces():
    for name in ('CancellationToken', 'TaskProgress', 'cancellation_scope'):
        assert name in ac.__all__ and name in api.__all__
        assert getattr(ac, name) is getattr(api, name) is getattr(cancellation, name)


def test_nested_scope_restores_its_owner_and_explicit_none_only_suspends_cleanup():
    first, second = cancellation.CancellationToken(1), cancellation.CancellationToken(2)
    assert cancellation.current_cancellation_token() is None
    with _scope(first):
        assert cancellation.current_cancellation_token() is first
        with _scope(second):
            assert cancellation.current_cancellation_token() is second
            first.cancel()
            cancellation.cancellation_checkpoint()
        with pytest.raises(CancelledError):
            cancellation.cancellation_checkpoint()
        with _scope(None):
            assert cancellation.current_cancellation_token() is None
            cancellation.cancellation_checkpoint()
        assert cancellation.current_cancellation_token() is first
    assert cancellation.current_cancellation_token() is None


def test_scope_does_not_appear_in_an_independent_context():
    context = copy_context()
    token = cancellation.CancellationToken(1)
    with _scope(token):
        assert context.run(cancellation.current_cancellation_token) is None


@pytest.mark.parametrize('invalid', [1, True, 'token', object()])
def test_invalid_scope_values_are_rejected_before_changing_the_current_owner(invalid):
    owner = cancellation.CancellationToken(1)
    with _scope(owner):
        with pytest.raises(TypeError, match='CancellationToken or None'):
            with _scope(invalid):
                pytest.fail('invalid cancellation binding was accepted')
        assert cancellation.current_cancellation_token() is owner


@pytest.mark.parametrize('entry', ['core', 'sdk', 'executor'])
def test_cancelled_scope_prevents_even_the_first_diagnostic_check(monkeypatch, entry):
    calls = []
    monkeypatch.setattr(diagnostics, '_ALL_CHECKS', (lambda: calls.append('check'),))
    token = cancellation.CancellationToken(1)
    token.cancel()
    runners = {'core': diagnostics.run_diagnostics, 'sdk': api.run_diagnostics,
               'executor': ac.executor.event_dict['AC_diagnose']}
    with _scope(token), pytest.raises(CancelledError):
        runners[entry]()
    assert calls == []


@pytest.mark.parametrize('failure', [False, True])
def test_cancel_during_a_check_stops_before_error_reporting_progress_or_the_next_check(monkeypatch, failure):
    calls, progress = [], []
    token = cancellation.CancellationToken(1, progress.append)

    def stopping():
        calls.append('first')
        token.cancel()
        if failure:
            raise ValueError('ordinary provider failure after stop')
        return diagnostics.Check('first', True, 'info', 'controlled')

    def later():
        calls.append('later')
        return diagnostics.Check('later', True, 'info', 'controlled')

    monkeypatch.setattr(diagnostics, '_ALL_CHECKS', (stopping, later))
    with _scope(token), pytest.raises(CancelledError):
        diagnostics.run_diagnostics()
    assert calls == ['first'] and [item.completed for item in progress] == [0]


def test_progress_and_report_stay_shared_with_read_only_executor_and_active_mcp(monkeypatch, tmp_path):
    from je_auto_control.utils.mcp_server.audit import AuditLogger
    from je_auto_control.utils.mcp_server.server import MCPServer
    monkeypatch.setattr(diagnostics, '_ALL_CHECKS', (
        lambda: diagnostics.Check('controlled', True, 'info', 'controlled'),))
    tool = next((item for item in build_default_tool_registry(read_only=True) if item.name == 'ac_diagnose'), None)
    assert tool is not None, 'the documented active diagnostic MCP entry point is absent'
    assert tool.input_schema.get('additionalProperties') is False
    assert capability_for_command('AC_diagnose') == Capability.READ_SCREEN
    expected = diagnostics.run_diagnostics().to_dict()
    progress = []
    ctx = ToolCallContext('diagnostic', progress_token='p', notifier=lambda _method, value: progress.append(value))
    with authorization_scope(AuthorizationContext('reader', Role.VIEWER)):
        assert tool.invoke({}, ctx=ctx) == expected
        record = ac.execute_action([['AC_diagnose']])
        assert expected in record.values()
        server = MCPServer(tools=[tool], audit_logger=AuditLogger(str(tmp_path/'audit.jsonl')))
        request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                   'params': {'name': 'ac_diagnose', 'arguments': {}}}
        reply = json.loads(server.handle_line(json.dumps(request)))
    assert not reply['result']['isError'] and reply['result']['structuredContent'] == expected
    assert [item['progress'] for item in progress] == [0, 1]
    request['params']['arguments'] = {'token': 'caller-supplied-authority'}
    refused = json.loads(server.handle_line(json.dumps(request)))
    assert refused['result']['isError']


def test_mcp_request_cancellation_stops_providers_and_keeps_its_established_signal(monkeypatch):
    calls = []
    monkeypatch.setattr(diagnostics, '_ALL_CHECKS', (lambda: calls.append('check'),))
    tool = next((item for item in build_default_tool_registry() if item.name == 'ac_diagnose'), None)
    assert tool is not None
    ctx = ToolCallContext('diagnostic-request')
    ctx.cancelled_event.set()
    with pytest.raises(OperationCancelledError) as caught:
        tool.invoke({}, ctx=ctx)
    assert caught.value.request_id == 'diagnostic-request' and calls == []


def test_real_jsonrpc_cancel_is_connection_scoped_and_never_becomes_an_error_screenshot(monkeypatch, tmp_path):
    from je_auto_control.utils.mcp_server import server as server_module
    from je_auto_control.utils.mcp_server.audit import AuditLogger
    tool = next(item for item in build_default_tool_registry(read_only=True) if item.name == 'ac_diagnose')
    server = server_module.MCPServer(tools=[tool], audit_logger=AuditLogger(str(tmp_path/'audit.jsonl')))
    entered = {name: threading.Event() for name in ('first', 'second')}
    release = threading.Event()
    replies, calls = {}, []

    def check():
        connection = server._connection_id
        token = cancellation.current_cancellation_token()
        assert token is not None
        calls.append('start '+connection)
        entered[connection].set()
        if connection == 'first':
            token.wait(3)
            token.checkpoint()
        else:
            assert release.wait(3)
        calls.append('finish '+connection)
        return diagnostics.Check(connection, True, 'info', 'controlled')

    def no_error_capture(_tool):
        pytest.fail('a cancelled diagnostic request reached ordinary error screenshot recovery')

    monkeypatch.setattr(diagnostics, '_ALL_CHECKS', (check,))
    monkeypatch.setattr(server_module, '_capture_error_screenshot', no_error_capture)
    request = {'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
               'params': {'name': 'ac_diagnose', 'arguments': {}}}

    def call(connection):
        with server.connection_scope(connection_id=connection):
            with authorization_scope(AuthorizationContext(connection, Role.VIEWER)):
                replies[connection] = json.loads(server.handle_line(json.dumps(request)))

    workers = {name: threading.Thread(target=call, args=(name,)) for name in entered}
    for worker in workers.values():
        worker.start()
    try:
        assert all(event.wait(1) for event in entered.values())
        with server.connection_scope(connection_id='first'):
            assert server.handle_line(json.dumps({'jsonrpc': '2.0', 'method': 'notifications/cancelled',
                                                 'params': {'requestId': 1}})) is None
        workers['first'].join(1)
        assert not workers['first'].is_alive() and workers['second'].is_alive()
        assert replies['first']['error']['code'] == -32800
        assert 'finish first' not in calls
    finally:
        release.set()
        for worker in workers.values():
            worker.join(3)
    assert not replies['second']['result']['isError']
    assert replies['second']['result']['structuredContent']['checks'][0]['name'] == 'second'
