# Managed agent tasks

The experimental managed-task core gives external clients, deterministic skills and a configured
local Ollama model the same observe/act/finish lifecycle. A task's own scope never grants operating
system permissions. Native target acceptance remains unverified; see `Progress.md`.

## Start and stop

```powershell
je_auto_control agent-task start
je_auto_control agent-task status
je_auto_control agent-task list
je_auto_control agent-task stop
```

Importing the package does not start a service or operate a target. Explicit startup launches a
hidden local process and publishes its ephemeral loopback address and bearer credential to the
per-user `agent_runtime.json`. Status never returns that credential. Stop requests cancel owned
input first; active dispatch or cleanup prevents premature service retirement.

## Task contract

Submit a JSON file with `je_auto_control agent-task submit task.json`, or call
`submit_agent_task(spec)` from Python. `AgentTaskSpec.from_dict` validates and freezes caller data.
Required fields are `goal`, nonempty `allowed_tools` and nonempty `success_criteria`.
Optional fields are `target`, `mode`, `roots`, `apps`, `inputs`, `actions`, `options` and `budget`.

- `mode`: `external` (default), `skill` or `ollama`. Internal modes are delivered through WorkQueue.
- `target`: a host-configured adapter identity; the default is `local-desktop`.
- `apps`: explicit application names, checked against the foreground process's accessibility nodes.
- `roots`: canonical allowed data roots; file operations and file completion evidence require them.
- `actions`: skill proposals with `tool` and optional `arguments`; every proposal still goes through observation.
- `budget`: max_steps=25, wall_seconds=300, retries=2, action_seconds=30 and model_seconds=120.

Criteria are `result_equals` (key/value in the last confirmed result), `file_exists` (path/min_bytes),
`file_sha256` (path/value), `file_text` (path/value), and `screen` (nonempty existing postcondition spec).
Unknown evidence never proves success. Empty postconditions and unknown criterion kinds are refused.

The reviewed default desktop tool set is intentionally limited. A custom adapter is a trusted Python
extension, not a model-supplied plugin. Native desktop calls run in a hidden, owned helper with bounded JSON IPC and action deadlines.
Cancellation retires the owned process tree; a host ledger releases only announced keys/buttons before
control transfers. Independent databases share a per-session input lock. Window/control scope is checked
again at input dispatch; pointer geometry and redacted window vision currently require Windows.
Reliable physical activity monitoring, richer adapters and complete workflow templates remain in Progress.

## External agent lifecycle

1. `submit_agent_task(spec)` returns task_id without taking input control.
2. `observe_agent_task(task_id)` acquires the target and returns a fresh observation_id.
3. `act_agent_task(task_id, {"tool": name, "arguments": args, "observation_id": id})` applies one proposal.
4. Observe again before another action. Old, expired or changed observations are rejected.
5. `finish_agent_task(task_id)` checks completion independently; model text is not proof.

Pause/resume/cancel and get/list functions use the same service. Pause retires input before releasing
control; resume requires new observation. An uncertain action prevents blind replay after restart.
New control generations reject old workers. A model cannot set task state or private executor fields.

The executor exposes `AC_agent_task_*` plus `AC_agent_runtime_start/status/stop`.
MCP exposes their lowercase names. The visual Builder derives fields from the same catalogue.
REST provides authenticated GET `/agent/tasks`, GET `/agent/task?task_id=...` and POST
`/agent/submit|observe|act|finish|pause|resume|cancel|shutdown`. Submit body is `{"spec": ...}`;
task operations use `{"task_id": ...}` and act also takes `action`. Shutdown needs host management.

Original principal metadata is authenticated across the local service bridge and store-backed users
are refreshed. MCP clients without RBAC use their live session identity for task ownership.
Task data reads require drive_input, even though get/list have a read-only hint. MCP path roots
are checked on submission and action parameters; further origin-policy lifecycle work is tracked
in Progress. Captured scope cannot widen an enclosing task's command guard.

## Local inference

Choose an already installed tool-capable Ollama model with `options.model`; optional `options.vision`
requires a vision-capable model. Endpoint defaults to `http://127.0.0.1:11434` and must be loopback.
The adapter checks `/api/show`, supplies only offered tools to `/api/chat`, disables redirects,
bounds HTTP concurrency and discards cancelled replies before execution. It never pulls a model
or chooses an external inference service. Configure Ollama with `OLLAMA_NO_CLOUD=1`.

## GUI and persistence

Open Agent Tasks from the workspace. Review the goal, target, execution mode, scope and completion
conditions before submitting. Start, stop, submit, refresh, observe, verify, pause, resume and cancel
are Actions-menu operations. Network work runs through TaskController. Closing the view detaches it;
the service owns submitted tasks.

The dedicated SQLite store records specs, owner references (never bearer tokens), task states,
action receipts and control generations. Prepared/dispatched/confirmed/uncertain receipts distinguish
dispatch from evidence. WorkQueue claim numbers fence stale delivery settlements; busy targets may
defer delivery without spending application retries. Retention, history/journal links, screenshots
and complete artifact lifecycle remain tracked rather than implicitly implemented.
