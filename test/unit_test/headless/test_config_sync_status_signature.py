"""``config_sync_status`` takes the options its three siblings take.

``config_sync_run`` / ``_resolve`` / ``_full_resync`` are
``(server_url, user_id, ..., **options)``; ``config_sync_status`` was
``(server_url, user_id, outbox_path=None)``. A caller holding one options
dict for an account -- the GUI tab, a script, an MCP client -- could pass it
to three of the four and got ``TypeError`` from the fourth.
"""
import inspect

import pytest

from je_auto_control.utils.config_sync import (
    ConfigSyncError, config_sync_full_resync, config_sync_resolve, config_sync_run,
    config_sync_status,
)

_URL = "https://sync.invalid"


def test_the_options_of_a_run_are_accepted_by_status(tmp_path):
    options = {"device_id": "laptop", "secret": "s3cret", "sections": "scripts",
               "scripts_dir": str(tmp_path), "outbox_path": str(tmp_path / "o.sqlite3"),
               "assets_dir": str(tmp_path), "timeout_s": 2.0, "wait": False, "force": True,
               "max_attempts": 1, "locators_path": None}
    status = config_sync_status(_URL, "alice", **options)
    assert status["state"] == "never"
    assert not (tmp_path / "o.sqlite3").exists(), "asking still creates nothing"


def test_the_positional_outbox_path_still_works(tmp_path):
    path = str(tmp_path / "o.sqlite3")
    assert config_sync_status(_URL, "alice", path) == config_sync_status(
        _URL, "alice", outbox_path=path)


def test_an_unknown_option_is_refused_like_everywhere_else(tmp_path):
    with pytest.raises(ConfigSyncError, match="unknown config sync option"):
        config_sync_status(_URL, "alice", str(tmp_path / "o.sqlite3"), enable_everything=True)


def test_the_four_entry_points_share_one_shape():
    for function in (config_sync_run, config_sync_status, config_sync_resolve,
                     config_sync_full_resync):
        parameters = list(inspect.signature(function).parameters.values())
        assert [parameter.name for parameter in parameters[:2]] == ["server_url", "user_id"]
        assert parameters[-1].kind is inspect.Parameter.VAR_KEYWORD, function.__name__


def test_the_mcp_tool_accepts_the_shared_options():
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    tools = {tool.name: tool
             for tool in build_default_tool_registry(read_only=False, aliases=False)}
    status = set(tools["ac_config_sync_status"].input_schema["properties"])
    resync = set(tools["ac_config_sync_full_resync"].input_schema["properties"])
    assert resync <= status
