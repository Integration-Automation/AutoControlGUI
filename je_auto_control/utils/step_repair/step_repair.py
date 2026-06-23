"""Repair-tactic policy for failed / no-effect actions (self-correction loop).

When an action does nothing or lands wrong, the agent needs a *policy* for what to try next —
re-locate and retry, nudge the coordinate, scroll the target into view, wait and retry, or give
up and escalate. ``self_healing`` / ``locator_repair`` only repair a locator that *did not
resolve* (element not found); they do nothing when the element was found and clicked but had no
effect. ``loop_guard`` only *detects* a stuck loop — it has no tactic selection or backoff.
``step_repair`` is that missing controller: it consumes an effect verdict (e.g. from
``action_effect``) and drives a bounded retry loop, choosing the next untried tactic each round.

Pure-stdlib state machine; every side effect — performing the action, verifying it, applying a
tactic, sleeping — is an injected callable, so the loop is fully deterministic and
unit-testable with no device. Imports no ``PySide6``.
"""
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

_DEFAULT_TACTICS = ("wait_retry", "relocate", "nudge", "scroll_into_view", "escalate")

# which tactics make sense for a given effect verdict, best-first
_VERDICT_TACTICS: Dict[str, Tuple[str, ...]] = {
    "no_op": ("wait_retry", "relocate", "nudge", "scroll_into_view"),
    "changed_elsewhere": ("escalate",),
    "changed": ("wait_retry", "relocate"),
}


@dataclass(frozen=True)
class RepairPolicy:
    """How hard to try: a cap on attempts and the allowed tactics, in priority order."""

    max_attempts: int = 3
    tactics: Tuple[str, ...] = _DEFAULT_TACTICS


@dataclass(frozen=True)
class RepairOutcome:
    """The result of a repair loop: success, attempt count, tactics used, detail."""

    ok: bool
    attempts: int
    tactics_used: List[str] = field(default_factory=list)
    detail: str = ""

    def to_dict(self) -> Dict[str, Any]:
        """Return the outcome as a plain dict."""
        return asdict(self)


def _effect_of(verdict: Any) -> str:
    """Extract the effect string from a dict / EffectVerdict / bare string."""
    if isinstance(verdict, dict):
        return str(verdict.get("effect", "no_op"))
    return str(getattr(verdict, "effect", verdict))


def plan_repair(verdict: Any, *, policy: Optional[RepairPolicy] = None) -> List[str]:
    """Return the ordered repair tactics to try for ``verdict``, capped at ``max_attempts``."""
    policy = policy or RepairPolicy()
    preferred = _VERDICT_TACTICS.get(_effect_of(verdict), policy.tactics)
    ordered = [tactic for tactic in preferred if tactic in policy.tactics]
    return (ordered or list(policy.tactics))[:int(policy.max_attempts)]


def next_tactic(verdict: Any, used: List[str], *,
                policy: Optional[RepairPolicy] = None) -> Optional[str]:
    """Return the next untried tactic for ``verdict``, or ``None`` when exhausted."""
    for tactic in plan_repair(verdict, policy=policy):
        if tactic not in used:
            return tactic
    return None


def run_with_repair(act: Callable[[], Any], verify: Callable[[], bool], *,
                    policy: Optional[RepairPolicy] = None,
                    apply_tactic: Optional[Callable[[str], Any]] = None,
                    verdict_for: Optional[Callable[[], Any]] = None,
                    sleep: Optional[Callable[[float], Any]] = None) -> RepairOutcome:
    """Run ``act`` then ``verify``; on failure apply repair tactics until ok or exhausted.

    Every effect is injected: ``act`` performs the action, ``verify`` returns success,
    ``apply_tactic`` mutates state for a named tactic, ``verdict_for`` supplies the current
    effect verdict, ``sleep`` backs off. Returns a :class:`RepairOutcome`.
    """
    policy = policy or RepairPolicy()
    sleeper = sleep or (lambda _seconds: None)
    act()
    if verify():
        return RepairOutcome(True, 1, [], "ok on first try")
    used: List[str] = []
    while len(used) < int(policy.max_attempts):
        tactic = next_tactic(verdict_for() if verdict_for else "no_op", used,
                             policy=policy)
        if tactic is None:
            break
        used.append(tactic)
        if apply_tactic is not None:
            apply_tactic(tactic)
        act()
        if verify():
            return RepairOutcome(True, len(used) + 1, list(used),
                                 f"recovered via {tactic}")
        sleeper(0)
    return RepairOutcome(False, len(used) + 1, list(used),
                         "exhausted repair tactics")
