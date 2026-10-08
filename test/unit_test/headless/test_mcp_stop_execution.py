"""MCP tools for the stoppable runs: ``ac_stop_execution`` and ``ac_list_executions``.

The run under test is ``ac_execute_actions`` given an ``AC_run_stoppable``
block whose body is ``AC_sleep``: no input and no screen access.
"""
import threading
from typing import Any, Dict

from je_auto_control.utils.executor.run_control import (
    ExecutionStopped, active_executions, stoppable_run,
)
from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
from je_auto_control.utils.rbac.policy import capability_for_tool
from je_auto_control.utils.rbac.users import Capability

_WAIT = 10.0


def _tools(**kwargs: Any) -> Dict[str, Any]:
    return {tool.name: tool for tool in build_default_tool_registry(aliases=False, **kwargs)}


def test_both_tools_are_registered_with_their_annotations():
    tools = _tools(read_only=False)
    stop, listing = tools["ac_stop_execution"], tools["ac_list_executions"]
    assert stop.annotations.read_only is False
    assert listing.annotations.read_only is True
    assert set(stop.input_schema["properties"]) == {"run_id", "reason"}
    assert stop.input_schema.get("required", []) == []
    assert listing.input_schema["properties"] == {}


def test_stopping_needs_drive_input_and_listing_only_read_screen():
    tools = _tools(read_only=False)
    stop, listing = tools["ac_stop_execution"], tools["ac_list_executions"]
    assert capability_for_tool(stop.name, stop.annotations.read_only) == Capability.DRIVE_INPUT
    assert capability_for_tool(listing.name, listing.annotations.read_only) == Capability.READ_SCREEN


def test_a_read_only_server_lists_runs_but_cannot_stop_them():
    tools = _tools(read_only=True)
    assert "ac_list_executions" in tools
    assert "ac_stop_execution" not in tools


def test_list_reports_a_run_and_stop_ends_it():
    tools = _tools(read_only=False)
    assert tools["ac_list_executions"].handler() == []
    with stoppable_run("mcp-listed") as token:
        listed = tools["ac_list_executions"].handler()
        assert [row["run_id"] for row in listed] == ["mcp-listed"]
        assert listed[0]["stopping"] is False
        assert isinstance(listed[0]["started_at"], float)
        assert tools["ac_stop_execution"].handler(run_id="mcp-listed", reason="via mcp") == {"stopped": 1}
        assert token.stopped and token.reason == "via mcp"
        assert tools["ac_list_executions"].handler()[0]["stopping"] is True
    assert tools["ac_stop_execution"].handler(run_id="mcp-listed") == {"stopped": 0}


def test_stop_without_a_run_id_stops_every_run():
    tools = _tools(read_only=False)
    with stoppable_run("mcp-a") as first:
        assert tools["ac_stop_execution"].handler() == {"stopped": 0}  # the caller's own run is spared
        assert not first.stopped
        outcome: Dict[str, Any] = {}
        worker = threading.Thread(
            target=lambda: outcome.update(reply=tools["ac_stop_execution"].handler()), daemon=True)
        worker.start()
        worker.join(_WAIT)
        assert outcome == {"reply": {"stopped": 1}}
        assert first.stopped


def test_an_action_list_run_through_mcp_is_stopped_by_the_mcp_tool():
    tools = _tools(read_only=False)
    outcome: Dict[str, Any] = {}

    def run() -> None:
        try:
            outcome["result"] = tools["ac_execute_actions"].handler(actions=[
                ["AC_run_stoppable", {"run_id": "mcp-run", "body": [["AC_sleep", {"seconds": 60}]]}]])
        except ExecutionStopped as error:
            outcome["error"] = error

    worker = threading.Thread(target=run, daemon=True)
    worker.start()
    started = threading.Event()

    def poll() -> None:
        while not started.is_set():
            if any(row["run_id"] == "mcp-run" for row in tools["ac_list_executions"].handler()):
                started.set()
            else:
                started.wait(0.01)

    watcher = threading.Thread(target=poll, daemon=True)
    watcher.start()
    assert started.wait(_WAIT), "the run never appeared in ac_list_executions"
    assert tools["ac_stop_execution"].handler(run_id="mcp-run", reason="enough") == {"stopped": 1}
    worker.join(_WAIT)
    assert not worker.is_alive()
    assert isinstance(outcome.get("error"), ExecutionStopped)
    assert outcome["error"].reason == "enough"
    assert active_executions() == []
