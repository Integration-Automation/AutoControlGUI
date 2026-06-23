Portable Agent-Trajectory Trace (Record & Replay)
=================================================

``agent_trace`` records OpenTelemetry GenAI *spans* (tokens / latency / cost) — that is
observability, not a replayable observation→action transcript; ``trajectory_eval``
*scores* a trajectory but defines no persisted format and cannot replay it; and
``semantic_recording`` replays recorded *human input macros*, not *agent* decisions.
This adds the OmniTool-style "log the trajectory to build a replay / training dataset"
format: ``{step, observation, action, result}`` JSONL with a deterministic replay
driver.

Pure-stdlib JSONL; the replay driver takes an injectable ``runner`` (no live model), so
it is fully unit-testable. Imports no ``PySide6``.

Headless API
------------

.. code-block:: python

    from je_auto_control import record_step, to_jsonl, from_jsonl, replay_trace

    trace = []
    record_step(trace, observation="login screen",
                action=["AC_click_mouse", {"x": 120, "y": 80}])
    record_step(trace, observation="typed user", action=["AC_write",
                {"write_string": "alice"}], result={"ok": True})

    open("run.jsonl", "w").write(to_jsonl(trace))     # persist a dataset

    # Later — replay every step through any runner (here a fake for tests).
    results = replay_trace(from_jsonl(open("run.jsonl").read()),
                           runner=lambda action: do(action))

``record_step`` appends an indexed ``{step, observation, action[, result]}`` entry;
``to_jsonl`` / ``from_jsonl`` round-trip the trace as newline-delimited JSON;
``replay_trace`` runs each step's ``action`` through ``runner(action)`` and returns the
``{step, action, result}`` outcomes in order.

Executor command
----------------

``AC_replay_trace`` replays a ``trace`` (JSON array or JSONL) by running each step's
``action`` (an AC action list) through the executor, returning ``{count, results}``. It
is exposed as the MCP tool ``ac_replay_trace`` (side-effecting) and as a Script Builder
command under **Flow**.
