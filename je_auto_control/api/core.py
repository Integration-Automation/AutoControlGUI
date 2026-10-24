"""Stable, headless AutoControl API façade."""

from je_auto_control.utils.dag import (
    DagDefinition, DagDefinitionError, DagNode, DagRunResult, NodeResult, parse_dag, run_dag,
)

from je_auto_control.utils.mcp_server.disclosure import ToolView, ToolPage, plan_mcp_tool_profile

from je_auto_control.utils.mcp_server.discovery import (
    ToolDiscoveryError, ToolIndex, ToolSummary, search_mcp_tools, get_mcp_tool_schema,
)

from je_auto_control.utils.agent_runtime import (
    browser_navigate, browser_click, browser_fill, browser_select, browser_check, browser_read, browser_wait,
    browser_link, browser_download, browser_upload,
    draft_agent_workflow, workflow_download, workflow_manifest, workflow_control, workflow_open, workflow_wait,
    AgentActionRequest, AgentActionResult, AgentControlBusy, AgentObservation, AgentRuntime,
    AgentTaskBudget, AgentTaskError, AgentTaskHandle, AgentTaskResult, AgentTaskSpec,
    AgentHumanReview, AgentObservationStale,
    AgentTargetProfile, manage_agent_target, list_agent_targets,
    recover_agent_target, manage_agent_skill, list_agent_skills,
    get_agent_task_receipts, reconcile_agent_task, prune_agent_tasks, manage_agent_trigger, list_agent_triggers,
    act_agent_task, agent_runtime_status, cancel_agent_task, finish_agent_task, get_agent_task, lookup_agent_task,
    list_agent_tasks, observe_agent_task, pause_agent_task, resume_agent_task,
    start_agent_runtime, stop_agent_runtime, submit_agent_task, stop_all_agent_tasks,
)

from je_auto_control.wrapper.capabilities import (
    BackendContext, CapabilitySnapshot, CapabilityStatus, probe_capabilities,
)

from je_auto_control.utils.codegen.codegen import generate_code
from je_auto_control.utils.diagnostics import run_diagnostics
from je_auto_control.utils.exception.cancellation import CancellationToken, TaskProgress, cancellation_scope
from je_auto_control.utils.executor.action_executor import (
    execute_action,
    execute_action_with_vars,
)
from je_auto_control.utils.failure_bundle import (
    FailureBundleOptions,
    create_failure_bundle,
    failure_bundle_on_error,
)

__all__ = [
    "DagDefinition", "DagDefinitionError", "DagNode", "DagRunResult", "NodeResult", "parse_dag", "run_dag",
    "ToolView", "ToolPage", "plan_mcp_tool_profile",
    "ToolDiscoveryError", "ToolIndex", "ToolSummary", "search_mcp_tools", "get_mcp_tool_schema",
    "AgentTargetProfile", "manage_agent_target", "list_agent_targets",
    "recover_agent_target", "manage_agent_skill", "list_agent_skills",
    "AgentHumanReview", "AgentObservationStale",
    "draft_agent_workflow", "workflow_download", "workflow_manifest", "workflow_control", "workflow_open",
    "workflow_wait", "browser_navigate", "browser_click", "browser_fill", "browser_select", "browser_check",
    "browser_read", "browser_wait", "browser_link", "browser_download", "browser_upload",
    "AgentActionRequest", "AgentActionResult", "AgentControlBusy", "AgentObservation", "AgentRuntime",
    "AgentTaskBudget", "AgentTaskError", "AgentTaskHandle", "AgentTaskResult", "AgentTaskSpec",
    "get_agent_task_receipts", "reconcile_agent_task", "prune_agent_tasks",
    "manage_agent_trigger", "list_agent_triggers",
    "act_agent_task", "agent_runtime_status", "cancel_agent_task", "finish_agent_task", "get_agent_task",
    "lookup_agent_task",
    "list_agent_tasks", "observe_agent_task", "pause_agent_task", "resume_agent_task", "start_agent_runtime",
    "submit_agent_task",
    "stop_agent_runtime", "stop_all_agent_tasks",
    "CancellationToken", "TaskProgress", "cancellation_scope",
    "BackendContext", "CapabilitySnapshot", "CapabilityStatus", "probe_capabilities",
    "FailureBundleOptions", "create_failure_bundle", "execute_action",
    "execute_action_with_vars", "failure_bundle_on_error", "generate_code",
    "run_diagnostics",
]
