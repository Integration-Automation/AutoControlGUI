"""MCP session roots, detached roots refresh and policy replacement remain owner-local."""
import pytest

from je_auto_control.utils.agent_runtime import origin_policy
from je_auto_control.utils.mcp_server.server import MCPServer
from je_auto_control.utils.mcp_server._argument_policy import ArgumentPolicy
from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.path_guard.path_guard import PathNotAllowedError


def server(tmp_path, monkeypatch):
    monkeypatch.setattr(origin_policy, "_directory", lambda: tmp_path / "origins")
    result = MCPServer(tools=[])
    result.argument_policy = ArgumentPolicy(PathPolicy(use_client_roots=True))
    return result


def test_each_connection_has_independent_client_roots_and_drop_revokes_only_its_witness(tmp_path, monkeypatch):
    bridge = server(tmp_path, monkeypatch)
    left, right = tmp_path / "left", tmp_path / "right"
    left.mkdir()
    right.mkdir()
    with bridge.connection_scope(connection_id="left"):
        first = bridge._active_argument_policy.path_policy
        first.set_client_roots([left])
        left_id = first.managed_origin()
    with bridge.connection_scope(connection_id="right"):
        second = bridge._active_argument_policy.path_policy
        second.set_client_roots([right])
        right_id = second.managed_origin()
        with pytest.raises(PathNotAllowedError):
            second.validate(left, operation="foreign root")
    bridge.forget_connection("left")
    assert origin_policy._read(right_id)["active"] is True
    with pytest.raises(origin_policy.AgentTaskError):
        origin_policy._read(left_id)
    bridge.stop()


def test_detached_roots_refresh_preserves_its_original_connection_and_policy(tmp_path, monkeypatch):
    bridge = server(tmp_path, monkeypatch)
    seen = []
    with bridge.connection_scope(connection_id="left", writer=lambda value: None):
        first = bridge._active_argument_policy
        worker = bridge._root_refresh_worker()

    def refresh():
        seen.append((bridge._connection_id, bridge._local.root_refresh_policy))

    monkeypatch.setattr(bridge, "_refresh_roots_safely", refresh)
    with bridge.connection_scope(connection_id="right"):
        worker()
        assert bridge._connection_id == "right"
    assert seen == [("left", first)]
    bridge.stop()


def test_policy_replacement_and_stop_refuse_late_root_replies(tmp_path, monkeypatch):
    bridge = server(tmp_path, monkeypatch)
    first = bridge._active_argument_policy.path_policy
    first.set_client_roots([tmp_path])
    identity = first.managed_origin()
    bridge.argument_policy = ArgumentPolicy(PathPolicy([tmp_path]))
    with pytest.raises(origin_policy.AgentTaskError):
        origin_policy._read(identity)
    with pytest.raises(PathNotAllowedError):
        first.set_client_roots([tmp_path])
    bridge.stop()


def test_real_late_refresh_uses_retired_policy_without_recreating_connection_state(tmp_path, monkeypatch):
    bridge = server(tmp_path, monkeypatch)
    with bridge.connection_scope(connection_id="left", writer=lambda value: None):
        policy = bridge._active_argument_policy.path_policy
        policy.set_client_roots([tmp_path])
        identity = policy.managed_origin()
        worker = bridge._root_refresh_worker()
    monkeypatch.setattr(bridge, "_send_outbound_request", lambda *a, **k: {"roots": [{"uri": tmp_path.as_uri()}]})
    bridge.forget_connection("left")
    worker()
    assert "left" not in bridge._origin_policy_entries
    with pytest.raises(origin_policy.AgentTaskError):
        origin_policy._read(identity)
    bridge.stop()


def test_static_host_policy_survives_view_disconnect_until_explicit_replacement(tmp_path, monkeypatch):
    bridge = server(tmp_path, monkeypatch)
    bridge.argument_policy = ArgumentPolicy(PathPolicy([tmp_path]))
    with bridge.connection_scope(connection_id="left"):
        identity = bridge._active_argument_policy.path_policy.managed_origin()
    bridge.forget_connection("left")
    bridge.stop()
    assert origin_policy._read(identity)["active"] is True
    bridge.argument_policy = ArgumentPolicy(PathPolicy([tmp_path]))
    with pytest.raises(origin_policy.AgentTaskError):
        origin_policy._read(identity)
