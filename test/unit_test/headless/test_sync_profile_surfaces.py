"""Reviewed native-profile loading shares private AC/MCP/Builder routing, live roots and prestart cancellation."""
from pathlib import Path

import pytest

from headless.test_sync_profile_load import materialized
import je_auto_control as ac
from je_auto_control.gui.script_builder.step_model import action_to_step, step_to_action
from je_auto_control.utils.mcp_server.context import OperationCancelledError, ToolCallContext
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.path_guard import PathNotAllowedError, PathPolicy
from je_auto_control.utils.rbac import AuthorizationContext, Role, authorization_scope
from je_auto_control.utils.rbac.authorization import AuthorizationError
from je_auto_control.utils.rbac.policy import authorize_command, capability_for_tool


def tool():
    return next(item for item in build_default_tool_registry() if item.name == 'ac_sync_profile_load')


def arguments(tmp_path):
    result = materialized(tmp_path)
    return {'directory': result['directory'], 'target_root': str(tmp_path / 'workspaces'),
            'expected_digest': result['manifest_digest']}


def test_private_native_load_ac_mcp_builder_create_disabled_independent_workspaces(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    values = arguments(tmp_path)
    initial_running = (ac.default_hotkey_daemon.is_running, ac.default_trigger_engine.is_running)
    action = ['AC_sync_profile_load', values]
    assert step_to_action(action_to_step(action)) == action
    ac.executor.execute_action([action], raise_on_error=True)
    first = list((tmp_path / 'workspaces').iterdir())
    assert len(first) == 1 and (first[0] / 'hotkeys.json').is_file()
    result = tool().handler(**values)
    assert Path(result['directory']) != first[0]
    assert all(item['enabled'] is False for item in result['hotkeys'] + result['triggers'])
    assert (ac.default_hotkey_daemon.is_running, ac.default_trigger_engine.is_running) == initial_running


def test_native_load_requires_drive_and_is_excluded_from_read_only_discovery():
    with authorization_scope(AuthorizationContext('viewer', Role.VIEWER)):
        with pytest.raises(AuthorizationError):
            authorize_command('AC_sync_profile_load')
        assert capability_for_tool('ac_sync_profile_load', True) == 'drive_input'
    assert 'ac_sync_profile_load' not in {item.name for item in build_default_tool_registry(read_only=True)}


def test_native_load_mcp_rechecks_explicit_roots_and_cancellation_before_copy(tmp_path, monkeypatch):
    monkeypatch.setenv('AUTOCONTROL_ALLOWED_PATH_ROOTS', str(tmp_path))
    values = arguments(tmp_path)
    context = ToolCallContext('outside', path_policy=PathPolicy([tmp_path / 'other-root']))
    with pytest.raises(PathNotAllowedError):
        tool().handler(**values, ctx=context)
    context = ToolCallContext('cancelled')
    context.cancelled_event.set()
    with pytest.raises(OperationCancelledError):
        tool().handler(**values, ctx=context)
    assert not (tmp_path / 'workspaces').exists()
