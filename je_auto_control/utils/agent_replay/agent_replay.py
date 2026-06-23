"""Portable agent-trajectory trace — record observation→action steps, replay them.

``agent_trace`` records OpenTelemetry GenAI *spans* (tokens / latency / cost) — that is
observability, not a replayable observation→action transcript; ``trajectory_eval``
*scores* a trajectory but defines no persisted on-disk format and cannot replay it; and
``semantic_recording`` replays recorded *human input macros*, not *agent* decisions.
This is the OmniTool-style "log the trajectory to build a replay / training dataset"
format: ``{step, observation, action, result}`` JSONL with a deterministic replay
driver.

Pure-stdlib JSONL; the replay driver takes an injectable ``runner`` (no live model), so
it is fully unit-testable. Imports no ``PySide6``.
"""
import json
from typing import Any, Callable, Dict, List, Mapping, Sequence

Step = Dict[str, Any]


def record_step(trace: List[Step], observation: Any, action: Any,
                result: Any = None) -> Step:
    """Append an ``{step, observation, action[, result]}`` entry to ``trace``.

    Mutates and returns the new step; ``step`` is the running index.
    """
    step: Step = {"step": len(trace), "observation": observation,
                  "action": action}
    if result is not None:
        step["result"] = result
    trace.append(step)
    return step


def to_jsonl(trace: Sequence[Mapping[str, Any]]) -> str:
    """Serialize a trace to newline-delimited JSON (one step per line)."""
    return "\n".join(json.dumps(step, ensure_ascii=False, sort_keys=True)
                     for step in trace)


def from_jsonl(text: str) -> List[Step]:
    """Parse a JSONL trace back into a list of step dicts."""
    return [json.loads(line) for line in text.splitlines() if line.strip()]


def replay_trace(trace: Sequence[Mapping[str, Any]],
                 runner: Callable[[Any], Any]) -> List[Step]:
    """Replay each step's ``action`` through ``runner``; return the replay results.

    ``runner(action)`` performs the action and returns its result. The output is a list
    of ``{step, action, result}`` in order — the basis for agent regression testing.
    """
    results: List[Step] = []
    for index, step in enumerate(trace):
        action = step.get("action")
        results.append({"step": step.get("step", index), "action": action,
                        "result": runner(action)})
    return results
