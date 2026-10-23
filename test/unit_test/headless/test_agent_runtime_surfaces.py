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
    assert "workflow_wait" in ac.__all__
    assert callable(ac.workflow_wait)


def test_builder_preserves_json_numeric_and_boolean_workflow_parameters():
    from je_auto_control.gui.script_builder.command_schema import COMMAND_SPECS, FieldType
    wait = {field.name: field.field_type for field in COMMAND_SPECS["AC_workflow_wait"].fields}
    assert wait == {"selector": FieldType.JSON, "expected": FieldType.JSON,
                    "state": FieldType.BOOL, "timeout_seconds": FieldType.FLOAT}
    manifest = {field.name: field.field_type for field in COMMAND_SPECS["AC_workflow_manifest"].fields}
    assert manifest["names"] == FieldType.JSON


def test_cli_task_commands_parse_without_starting_a_service():
    from je_auto_control.cli import build_parser
    parser = build_parser()
    for operation in ("start", "stop", "status", "list"):
        assert parser.parse_args(["agent-task", operation]).agent_operation == operation
    assert parser.parse_args(["agent-task", "submit", "task.json"]).spec == "task.json"
    assert parser.parse_args(["agent-task", "skill", "list"]).request is None
    assert parser.parse_args(["agent-task", "skill", "record", "record.json"]).skill_operation == "record"
    assert parser.parse_args(["agent-task", "targets"]).agent_operation == "targets"
    assert parser.parse_args(["agent-task", "target", "register", "profile.json"]).target_operation == "register"


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


def test_service_routes_have_explicit_operator_or_host_capabilities():
    from je_auto_control.utils.agent_runtime.routes import OPERATIONS
    from je_auto_control.utils.rbac.policy import capability_for_route
    for operation in OPERATIONS:
        assert capability_for_route("POST", f"/agent/{operation}") == (
            "manage_hosts" if operation in {"shutdown", "recover_target", "target"} else "drive_input")
def test_versioned_namespace_exposes_every_managed_task_public_api():
    """The versioned namespace must offer the same managed contracts as the package root."""
    import je_auto_control
    from je_auto_control import api
    from je_auto_control.api import core
    from je_auto_control.utils import agent_runtime
    for name in agent_runtime.__all__:
        expected = getattr(agent_runtime, name)
        assert getattr(core, name) is expected
        assert getattr(api, name) is expected
        assert getattr(je_auto_control, name) is expected


