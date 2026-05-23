"""Phase 7.10: self-healing replay.

``relocate_recording`` (Phase 6.7) already swaps absolute coordinates
for anchored ones at replay time. ``SelfHealingReplayer`` adds the
next layer: when a step actually *fails* (e.g. the post-click
verification didn't fire), it asks the VLM to re-locate the element
from the natural-language description in the anchor and retries up
to ``max_retries`` times before propagating the failure.

The replayer is pluggable end-to-end:
  * ``execute_step``  — runs one action, returns truthy on success.
  * ``vlm_locate``    — natural-language description → ``(x, y)`` or None.
  * ``verify_step``   — optional post-step assertion; default ``True``.

Failure is detected the moment ``execute_step`` raises or
``verify_step`` returns falsy. The replayer rewrites the action's
``x`` / ``y`` with the VLM's new coordinates and re-runs.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Mapping, Optional, Sequence, Tuple


_CLICK_ACTIONS = frozenset({
    "mouse_press", "mouse_release", "mouse_click",
})

ExecuteFn = Callable[[Mapping[str, Any]], Any]
VerifyFn = Callable[[Mapping[str, Any], Any], bool]
VlmLocateFn = Callable[[str], Optional[Tuple[int, int]]]


@dataclass
class StepResult:
    """Per-step outcome — useful for failure reports."""
    index: int
    action: Dict[str, Any]
    success: bool
    attempts: int
    last_error: Optional[str] = None
    healed: bool = False


@dataclass
class ReplayResult:
    """Aggregated result of a self-healing replay."""
    steps: List[StepResult] = field(default_factory=list)
    succeeded: bool = True
    healed_count: int = 0

    def __bool__(self) -> bool:
        return self.succeeded


class SelfHealingReplayer:
    """Run a recording with VLM-driven re-location on step failure.

    The replayer is intentionally minimal: it doesn't know how to
    take screenshots or call models — those are injected via the
    constructor. That keeps the engine deterministic in tests and
    avoids pulling the heavy vision stack into the import graph.
    """

    def __init__(self,
                 execute_step: ExecuteFn,
                 *, verify_step: Optional[VerifyFn] = None,
                 vlm_locate: Optional[VlmLocateFn] = None,
                 max_retries: int = 2) -> None:
        self._execute = execute_step
        self._verify = verify_step or (lambda _action, _result: True)
        self._vlm_locate = vlm_locate
        self._max_retries = max(0, int(max_retries))

    def replay(self,
               actions: Sequence[Mapping[str, Any]]) -> ReplayResult:
        out = ReplayResult()
        for idx, action in enumerate(actions):
            step = self._run_step(idx, action)
            out.steps.append(step)
            if step.healed:
                out.healed_count += 1
            if not step.success:
                out.succeeded = False
                return out
        return out

    def _run_step(self, idx: int,
                  action: Mapping[str, Any]) -> StepResult:
        current = dict(action)
        attempts = 0
        last_error: Optional[str] = None
        healed = False
        while attempts <= self._max_retries:
            attempts += 1
            try:
                result = self._execute(current)
                if self._verify(current, result):
                    return StepResult(
                        index=idx, action=current, success=True,
                        attempts=attempts, healed=healed,
                    )
                last_error = "verify_step returned False"
            except (RuntimeError, OSError, ValueError) as error:
                last_error = f"{type(error).__name__}: {error}"
            if attempts > self._max_retries:
                break
            healed_action = self._heal(current)
            if healed_action is None:
                break
            current = healed_action
            healed = True
        return StepResult(
            index=idx, action=current, success=False,
            attempts=attempts, last_error=last_error, healed=healed,
        )

    def _heal(self,
              action: Mapping[str, Any]) -> Optional[Dict[str, Any]]:
        """Ask the VLM where to click instead. Returns a new action or None."""
        if self._vlm_locate is None:
            return None
        if action.get("action") not in _CLICK_ACTIONS:
            return None
        description = self._description_from_anchor(action)
        if not description:
            return None
        position = self._vlm_locate(description)
        if position is None:
            return None
        healed = dict(action)
        healed["x"] = int(position[0])
        healed["y"] = int(position[1])
        healed["healed"] = True
        return healed

    @staticmethod
    def _description_from_anchor(action: Mapping[str, Any]) -> str:
        """Build a natural-language hint from the anchor's a11y metadata."""
        anchor = action.get("anchor")
        if not isinstance(anchor, Mapping):
            return ""
        role = anchor.get("role") or ""
        name = anchor.get("name") or ""
        app = anchor.get("app_name") or ""
        parts = [p for p in (role, name) if p]
        text = " ".join(parts).strip()
        if app:
            text = f"{text} in {app}".strip()
        return text


def self_healing_replay(actions: Sequence[Mapping[str, Any]],
                        **kwargs) -> ReplayResult:
    """Convenience wrapper: ``SelfHealingReplayer(...).replay(actions)``."""
    return SelfHealingReplayer(**kwargs).replay(actions)


__all__ = [
    "SelfHealingReplayer", "ReplayResult", "StepResult",
    "self_healing_replay",
]
