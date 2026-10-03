"""Remote command delivery preserves named ownership across every entry point."""
import importlib
import inspect

import pytest

from je_auto_control.utils.executor.action_executor import Executor

REMOTE_COMMANDS = (
    'AC_start_remote_host', 'AC_stop_remote_host', 'AC_remote_host_status',
    'AC_remote_connect', 'AC_remote_disconnect', 'AC_remote_viewer_status', 'AC_remote_send_input',
    'AC_start_ws_host', 'AC_stop_ws_host', 'AC_ws_host_status', 'AC_ws_connect',
    'AC_ws_disconnect', 'AC_ws_viewer_status', 'AC_ws_send_input',
    'AC_start_webrtc_host', 'AC_webrtc_create_offer', 'AC_webrtc_accept_answer',
    'AC_stop_webrtc_host', 'AC_webrtc_host_status', 'AC_start_webrtc_viewer',
    'AC_webrtc_process_offer', 'AC_webrtc_send_input', 'AC_stop_webrtc_viewer', 'AC_webrtc_viewer_status',
)


class Viewer:
    """Transport double that records which connection receives input or closes."""
    connected = True
    authenticated = True
    remote_host_id = '123456789'

    def __init__(self):
        self.inputs = []

    def send_input(self, action):
        self.inputs.append(action)

    def disconnect(self, timeout=2.0):
        self.connected = False

    def stop(self):
        self.connected = False


@pytest.fixture
def registry(monkeypatch):
    module = importlib.import_module('je_auto_control.utils.remote_desktop.registry')
    directory = module._RemoteDesktopRegistry()
    monkeypatch.setattr(module, 'registry', directory)
    executor_module = importlib.import_module('je_auto_control.utils.executor.action_executor')
    monkeypatch.setattr(executor_module, 'remote_desktop_registry', directory)
    return directory


@pytest.mark.parametrize('command', REMOTE_COMMANDS)
def test_commands_accept_optional_named_session(command):
    parameter = inspect.signature(Executor().event_dict[command]).parameters['session_id']
    assert parameter.kind is inspect.Parameter.KEYWORD_ONLY and parameter.default is None


@pytest.mark.parametrize('transport,command', [
    ('tcp', 'AC_remote_send_input'), ('ws', 'AC_ws_send_input'), ('webrtc', 'AC_webrtc_send_input'),
])
def test_named_executor_input_keeps_script_default(registry, transport, command):
    default, named = Viewer(), Viewer()
    script = registry.register_session(default, owner='script', transport=transport, role='viewer', script_default=True)
    gui = registry.register_session(named, owner='gui:test', transport=transport, role='viewer')
    assert Executor().event_dict[command]({'action': 'ping'}, session_id=gui.id) == {'sent': True}
    assert named.inputs == [{'action': 'ping'}] and default.inputs == []
    assert registry.script_session_id(transport, 'viewer') == script.id


def test_mcp_named_disconnect_preserves_default(registry):
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    default, named = Viewer(), Viewer()
    registry.register_session(default, owner='script', transport='tcp', role='viewer', script_default=True)
    gui = registry.register_session(named, owner='gui:test', transport='tcp', role='viewer')
    tools = build_default_tool_registry()
    tool = next(tool for tool in tools if tool.name == 'ac_remote_viewer_disconnect')
    assert 'session_id' in tool.input_schema['properties']
    tool.handler(session_id=gui.id)
    assert default.connected and not named.connected


def test_session_wire_operations_and_public_exports(registry):
    import je_auto_control as facade
    import je_auto_control.api as beta
    default, named = Viewer(), Viewer()
    registry.register_session(default, owner='script', transport='tcp', role='viewer', script_default=True)
    gui = registry.register_session(named, owner='gui:test', transport='tcp', role='viewer')
    for namespace in (facade, beta):
        assert namespace.get_remote_session(gui.id, owner=gui.owner).id == gui.id
        assert namespace.RemoteSession is namespace.SessionStatus
    commands = Executor().event_dict
    assert commands['AC_remote_session_status'](gui.id, owner=gui.owner)['owner'] == gui.owner
    assert commands['AC_remote_disconnect_session'](gui.id, owner=gui.owner)['state'] == 'closed'
    events = commands['AC_remote_session_events'](owner=gui.owner)
    assert [event['state'] for event in events] == ['active', 'closing', 'closed']
    assert default.connected and not named.connected


def test_builder_remote_input_and_region_are_json():
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS, FieldType
    from je_auto_control.gui.script_builder.step_form_view import _read_field_value, _set_editor_value
    from PySide6.QtWidgets import QApplication, QLineEdit
    application = QApplication.instance() or QApplication([])
    for command in REMOTE_COMMANDS:
        identity = next(field for field in COMMAND_SPECS[command].fields if field.name == 'session_id')
        assert identity.optional
    for command, name, value in [
        ('AC_remote_send_input', 'action', {'action': 'mouse_move', 'x': 10, 'y': 20}),
        ('AC_start_ws_host', 'region', [0, 0, 100, 100]),
    ]:
        spec = next(field for field in COMMAND_SPECS[command].fields if field.name == name)
        assert spec.field_type is FieldType.JSON
        editor = QLineEdit()
        _set_editor_value(editor, spec, value)
        assert _read_field_value(editor, spec) == (True, value)
        editor.setText('{invalid')
        assert _read_field_value(editor, spec) == (False, None)
        editor.deleteLater()
    application.processEvents()
