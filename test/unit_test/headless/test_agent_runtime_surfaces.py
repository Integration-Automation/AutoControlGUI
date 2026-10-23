"""Public task surfaces share commands and never construct native resources on import."""
import sys


def test_catalogue_is_available_in_executor_mcp_and_builder():
    import je_auto_control as ac
    from je_auto_control.utils.agent_runtime.commands import CATALOG
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS
    registry = {tool.name: tool for tool in build_default_tool_registry()}
    for name in CATALOG:
        assert name in ac.executor.known_commands()
        assert name in COMMAND_SPECS
        assert name.lower() in registry
    assert "AgentTaskSpec" in ac.__all__
    assert callable(ac.submit_agent_task)


def test_cli_task_commands_parse_without_starting_a_service():
    from je_auto_control.cli import build_parser
    parser = build_parser()
    for operation in ("start", "stop", "status", "list"):
        assert parser.parse_args(["agent-task", operation]).agent_operation == operation
    assert parser.parse_args(["agent-task", "submit", "task.json"]).spec == "task.json"


def test_headless_task_contract_does_not_load_qt():
    import subprocess
    result = subprocess.run([sys.executable, "-c", (
        "import sys, je_auto_control; "
        "assert not any(name.startswith('PySide6') for name in sys.modules)")],
        capture_output=True, text=True, timeout=30, check=False)
    assert result.returncode == 0, result.stderr


def test_managed_mcp_tools_preserve_readonly_and_sensitive_read_policy():
    from je_auto_control.utils.agent_runtime.commands import CATALOG
    from je_auto_control.utils.mcp_server.tools import build_default_tool_registry
    from je_auto_control.utils.rbac.policy import capability_for_tool
    registry = {tool.name: tool for tool in build_default_tool_registry(read_only=True)}
    for name, (_function, _properties, _required, readonly, _management) in CATALOG.items():
        assert (name.lower() in registry) == readonly
        if readonly:
            tool = registry[name.lower()]
            assert capability_for_tool(tool.name, tool.annotations.read_only) == "drive_input"
