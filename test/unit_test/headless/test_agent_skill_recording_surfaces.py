"""Existing shared operations record the original workflow; GUI prepares an inert review request."""
import json

import pytest

from headless.test_agent_skill_recording_completion import recording as _recording, request_for
from headless.test_agent_skill_recording_security import assert_no_draft
from je_auto_control.utils.agent_runtime import AgentTaskError
from je_auto_control.utils.agent_runtime.client import AgentRuntimeClient
from je_auto_control.utils.rest_api.rest_server import RestApiServer

recording = _recording


@pytest.mark.parametrize('surface', ['python', 'executor', 'cli', 'rest', 'mcp'])
def test_shared_surfaces_record_original_actions_as_an_unpublished_draft(recording, monkeypatch, tmp_path, surface):
    import je_auto_control as ac
    from je_auto_control.cli import build_parser
    from je_auto_control.utils.agent_runtime.cli import run
    from je_auto_control.utils.tool_use_schema import run_tool_call
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    from je_auto_control.utils.rbac.authorization import AuthorizationContext, authorization_scope
    server = RestApiServer(port=0, token='owned-recording-completion', agent_runtime=recording.runtime,
                           enable_audit=False, use_environment_users=False)
    server.start()
    try:
        connection = tmp_path / 'connection.json'
        connection.write_text(json.dumps({'url': server.base_url, 'token': server.token}), encoding='utf-8')
        monkeypatch.setattr('je_auto_control.utils.agent_runtime.client.default_connection_path', lambda: connection)
        request = request_for(recording)
        tools = {tool.name: tool for tool in build_default_tool_registry()}
        if surface == 'python':
            value = ac.manage_agent_skill('record', request)
        elif surface == 'executor':
            value = run_tool_call('AC_agent_skill', {'operation': 'record', 'request': request})
        elif surface == 'cli':
            path = tmp_path / 'record.json'
            path.write_text(json.dumps(request), encoding='utf-8')
            value = run(build_parser().parse_args(['agent-task', 'skill', 'record', str(path)]))
        elif surface == 'mcp':
            with authorization_scope(AuthorizationContext('owned-record-reviewer', 'admin')):
                value = tools['ac_agent_skill'].invoke({'operation': 'record', 'request': request})
        else:
            value = AgentRuntimeClient(connection).call('skill', {'operation': 'record', 'request': request})
        assert value['state'] == 'draft' and value['publication'] is None
        assert value['provenance']['source_task'] == recording.task_id
        assert value['provenance']['completion_review']['task_id'] == recording.child_id
        assert value['spec']['actions'] == [recording.action]
        assert recording.runtime.get(recording.task_id).state == 'paused'
        assert 'record' in tools['ac_agent_skill'].input_schema['properties']['operation']['enum']
        assert 'AC_agent_skill' in COMMAND_SPECS
    finally:
        server.stop()


@pytest.mark.parametrize('recording', ['named'], indirect=True)
def test_http_revoked_reviewer_refuses_recording_with_409(recording, tmp_path):
    server = RestApiServer(port=0, token='owned-recording-authority', agent_runtime=recording.runtime,
                           enable_audit=False, use_environment_users=False)
    server.start()
    try:
        connection = tmp_path / 'connection.json'
        connection.write_text(json.dumps({'url': server.base_url, 'token': server.token}), encoding='utf-8')
        recording.users.remove_user('reviewer')
        with pytest.raises(AgentTaskError) as error:
            AgentRuntimeClient(connection).call('skill', {'operation': 'record', 'request': request_for(recording)})
        assert '(409)' in str(error.value)
        assert_no_draft(recording)
    finally:
        server.stop()


def test_gui_prepares_original_source_and_reader_fields_without_recording(monkeypatch):
    pytest.importorskip('PySide6')
    from PySide6.QtWidgets import QApplication
    from je_auto_control.gui.agent_tasks_tab import AgentTasksTab
    import shiboken6
    app = QApplication.instance() or QApplication([])
    tab = AgentTasksTab()
    monkeypatch.setattr(tab, '_dispatch', lambda *_args: pytest.fail('Preparing recording must not dispatch'))
    try:
        tab._task_id.setText('reviewed-completion')
        dict(tab.menu_actions())['agent_skill_recording_completion_example']()
        assert tab._skill_operation.currentData() == 'record'
        assert json.loads(tab._skill_request.toPlainText()) == {
            'task_id': '<original-workflow-task-id>', 'completion_task_id': 'reviewed-completion', 'name': ''}
        assert tab._pages.currentIndex() == tab._page_keys.index('agent_page_skills')
    finally:
        tab.close()
        shiboken6.delete(tab)
        app.processEvents()
