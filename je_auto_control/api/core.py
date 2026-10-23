"""Stable, headless AutoControl API façade."""

from je_auto_control.utils.agent_runtime import (
    draft_agent_workflow, workflow_download, workflow_manifest, workflow_control, workflow_open, workflow_wait,
    AgentActionRequest, AgentActionResult, AgentControlBusy, AgentObservation, AgentRuntime,
    AgentTaskBudget, AgentTaskError, AgentTaskHandle, AgentTaskResult, AgentTaskSpec,
    get_agent_task_receipts, reconcile_agent_task, prune_agent_tasks, manage_agent_trigger, list_agent_triggers,
    act_agent_task, agent_runtime_status, cancel_agent_task, finish_agent_task, get_agent_task,
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
    "draft_agent_workflow", "workflow_download", "workflow_manifest", "workflow_control", "workflow_open",
    "workflow_wait",
    "AgentActionRequest", "AgentActionResult", "AgentControlBusy", "AgentObservation", "AgentRuntime",
    "AgentTaskBudget", "AgentTaskError", "AgentTaskHandle", "AgentTaskResult", "AgentTaskSpec",
    "get_agent_task_receipts", "reconcile_agent_task", "prune_agent_tasks",
    "manage_agent_trigger", "list_agent_triggers",
    "act_agent_task", "agent_runtime_status", "cancel_agent_task", "finish_agent_task", "get_agent_task",
    "list_agent_tasks", "observe_agent_task", "pause_agent_task", "resume_agent_task", "start_agent_runtime",
    "submit_agent_task",
    "stop_agent_runtime", "stop_all_agent_tasks",
    "CancellationToken", "TaskProgress", "cancellation_scope",
    "BackendContext", "CapabilitySnapshot", "CapabilityStatus", "probe_capabilities",
    "FailureBundleOptions", "create_failure_bundle", "execute_action",
    "execute_action_with_vars", "failure_bundle_on_error", "generate_code",
    "run_diagnostics",
]
