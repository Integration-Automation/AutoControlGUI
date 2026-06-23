"""Per-step critic feature bundle + a rule-based step scorer.

Scoring an agent's step needs the evidence in one place — what the action was, what changed,
whether it landed on target, whether the declared postcondition held. ``trajectory_eval``
scores a *finished whole trajectory* against a static rubric and has no per-step evidence;
``agent_trace`` emits OTel spans (tokens / latency), not decision quality; ``agent_replay``
persists ``{obs, action, result}`` but does no scoring. ``critic_features`` is the missing
per-step layer: it composes ``action_effect`` (did it do anything, where), ``observation_delta``
(how much changed) and ``postcondition`` (did the expected outcome hold) into one compact
record, and ships a deterministic rule-based scorer so the feature works fully headless —
leaving the optional LLM-as-judge to the integrator (``to_judge_prompt``).

Pure-stdlib; composes existing pure modules; deterministic and unit-testable with no device.
Imports no ``PySide6``.
"""
from typing import Any, Dict, Optional, Sequence

Element = Dict[str, Any]

_EFFECT_SCORE = {"changed_near_target": 1.0, "changed": 0.6,
                 "changed_elsewhere": 0.3, "no_op": 0.0}


def build_critic_record(action: Any, before: Sequence[Element],
                        after: Sequence[Element], *,
                        postcondition: Optional[Dict[str, Any]] = None,
                        radius: int = 64) -> Dict[str, Any]:
    """Compose a per-step critic record from the before/after observation + action.

    Returns ``{action, effect, delta_counts}`` and, when a ``postcondition`` spec is
    given, the ``postcondition`` report — the evidence bundle a step critic scores.
    """
    from je_auto_control.utils.action_effect import classify_effect
    from je_auto_control.utils.observation_delta import delta_index
    verdict = classify_effect(before, after, action, radius=int(radius)).to_dict()
    delta = delta_index(before, after)
    record: Dict[str, Any] = {
        "action": action, "effect": verdict,
        "delta_counts": {"added": len(delta["added"]),
                         "removed": len(delta["removed"]),
                         "changed": len(delta["changed"]),
                         "stable": len(delta["stable"])}}
    if postcondition is not None:
        from je_auto_control.utils.postcondition import check_postcondition
        record["postcondition"] = check_postcondition(
            after, postcondition, before=before).to_dict()
    return record


def score_step_rule_based(record: Dict[str, Any]) -> Dict[str, Any]:
    """Score a critic record deterministically → ``{outcome, process_score, reasons}``.

    ``outcome`` is a binary success (the action did something *and* any postcondition held);
    ``process_score`` is a 0..1 quality from the effect class, halved if the postcondition
    failed.
    """
    effect = record["effect"]["effect"]
    process = _EFFECT_SCORE.get(effect, 0.0)
    report = record.get("postcondition")
    postcondition_ok = report["ok"] if report else True
    reasons = [f"effect={effect}"]
    if report is not None:
        reasons.append(f"postcondition={'ok' if postcondition_ok else 'failed'}")
    return {"outcome": effect != "no_op" and postcondition_ok,
            "process_score": round(process * (1.0 if postcondition_ok else 0.5), 4),
            "reasons": reasons}


def to_judge_prompt(record: Dict[str, Any]) -> str:
    """Render a critic record as a compact text block for an LLM-as-judge."""
    counts = record["delta_counts"]
    lines = [f"Action: {record['action']}",
             f"Effect: {record['effect']['effect']} ({record['effect']['reason']})",
             f"Changed: +{counts['added']} -{counts['removed']} ~{counts['changed']}"]
    report = record.get("postcondition")
    if report is not None:
        lines.append(f"Postcondition ok: {report['ok']} "
                     f"(failed: {report['failed']})")
    return "\n".join(lines)
