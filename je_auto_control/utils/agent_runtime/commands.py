"""One command catalogue shared by executor, MCP and the visual script editor."""
from __future__ import annotations

from typing import Any

from je_auto_control.utils.agent_runtime import api

_ID = {"task_id": {"type": "string", "minLength": 1}}

# name: (function, JSON properties, required, read_only, host_management)
CATALOG: dict[str, tuple[Any, dict, tuple[str, ...], bool, bool]] = {
    "AC_agent_runtime_stop": (api.stop_agent_runtime, {}, (), False, True),
    "AC_agent_runtime_start": (api.start_agent_runtime, {"directory": {"type": "string", "format": "path"}},
                               (), False, True),
    "AC_agent_runtime_status": (api.agent_runtime_status, {}, (), True, False),
    "AC_agent_task_submit": (api.submit_agent_task, {"spec": {"type": "object"}}, ("spec",), False, False),
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
