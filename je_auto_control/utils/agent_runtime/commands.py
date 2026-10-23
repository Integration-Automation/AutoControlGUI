"""One command catalogue shared by executor, MCP and the visual script editor."""
from __future__ import annotations

from typing import Any

from je_auto_control.utils.agent_runtime import api
from je_auto_control.utils.agent_runtime.workflow_specs import draft_agent_workflow, WORKFLOWS
from je_auto_control.utils.agent_runtime.workflow_files import workflow_download, workflow_manifest
from je_auto_control.utils.agent_runtime.workflow_desktop import workflow_control, workflow_open
from je_auto_control.utils.agent_runtime.task_triggers import OPERATIONS as TRIGGER_OPERATIONS

_ID = {"task_id": {"type": "string", "minLength": 1}}

# name: (function, JSON properties, required, read_only, host_management)
CATALOG: dict[str, tuple[Any, dict, tuple[str, ...], bool, bool]] = {
    "AC_agent_target_recover": (api.recover_agent_target, {"target": {"type": "string"},
                                                        "note": {"type": "string", "maxLength": 2000}},
                                ("target", "note"), False, True),
    "AC_agent_trigger": (api.manage_agent_trigger, {"operation": {"type": "string", "enum": list(TRIGGER_OPERATIONS)},
                                                  "request": {"type": "object"}}, ("operation",), False, False),
    "AC_agent_trigger_list": (api.list_agent_triggers, {}, (), True, False),
    "AC_agent_task_receipts": (api.get_agent_task_receipts, {**_ID, "offset": {"type": "integer", "minimum": 0},
                                   "limit": {"type": "integer", "minimum": 1, "maximum": 200}},
                                  ("task_id",), True, False),
    "AC_agent_task_reconcile": (api.reconcile_agent_task, {**_ID, "review": {"type": "object"}},
                               ("task_id", "review"), False, False),
    "AC_agent_task_prune": (api.prune_agent_tasks, {"keep_days": {"type": "integer", "minimum": 1}}, (), False, False),
    "AC_agent_task_stop_all": (api.stop_all_agent_tasks, {}, (), False, False),
    "AC_agent_task_draft": (draft_agent_workflow, {"workflow": {"type": "string", "enum": list(WORKFLOWS)},
                                                  "config": {"type": "object"}}, ("workflow", "config"), True, False),
    "AC_workflow_download": (workflow_download, {"url": {"type": "string"}, "directory": {"type": "string"},
                               "name": {"type": "string"}, "sha256": {"type": "string"}},
                              ("url", "directory", "name"), False, False),
    "AC_workflow_manifest": (workflow_manifest, {"directory": {"type": "string"}, "path": {"type": "string"},
                               "names": {"type": "array", "items": {"type": "string"}}},
                              ("directory", "path", "names"), False, False),
    "AC_workflow_control": (workflow_control, {"operation": {"type": "string",
                                                          "enum": ["get", "set", "invoke", "state"]},
                              "selector": {"type": "object"}, "value": {"type": "string"}},
                             ("operation", "selector"), False, False),
    "AC_workflow_open": (workflow_open, {"path": {"type": "string"}}, ("path",), False, False),
    "AC_agent_runtime_stop": (api.stop_agent_runtime, {}, (), False, True),
    "AC_agent_runtime_start": (api.start_agent_runtime, {"directory": {"type": "string", "format": "path"}},
                               (), False, True),
    "AC_agent_runtime_status": (api.agent_runtime_status, {}, (), True, False),
    "AC_agent_task_submit": (api.submit_agent_task, {"spec": {"type": "object"},
                                                   "idempotency_key": {"type": "string", "maxLength": 256}},
                            ("spec",), False, False),
    "AC_agent_task_list": (api.list_agent_tasks, {}, (), True, False),
    "AC_agent_task_get": (api.get_agent_task, _ID, ("task_id",), True, False),
    "AC_agent_task_observe": (api.observe_agent_task, _ID, ("task_id",), False, False),
    "AC_agent_task_act": (api.act_agent_task, {**_ID, "action": {"type": "object"}},
                         ("task_id", "action"), False, False),
    "AC_agent_task_finish": (api.finish_agent_task, _ID, ("task_id",), False, False),
    "AC_agent_task_pause": (api.pause_agent_task, _ID, ("task_id",), False, False),
    "AC_agent_task_resume": (api.resume_agent_task, _ID, ("task_id",), False, False),
    "AC_agent_task_cancel": (api.cancel_agent_task, _ID, ("task_id",), False, False),
}
COMMANDS = {name: entry[0] for name, entry in CATALOG.items()}
