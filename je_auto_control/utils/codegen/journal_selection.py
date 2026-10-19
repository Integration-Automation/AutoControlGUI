"""Select completed recorded invocations, preserving source blocks and explicit observed-path fallbacks."""
import json
from dataclasses import dataclass, field
from typing import Callable, cast

from je_auto_control.utils.codegen.candidate_validation import (
    Action, prepare_action, source_children, validate_candidate_actions,
)
from je_auto_control.utils.codegen.journal_steps import JournalStep
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.executor.action_schema import FLOW_BODY_KEYS, FLOW_BRANCH_LIST_KEYS
from je_auto_control.utils.run_history.run_outcome import raise_if_run_interrupted


@dataclass
class Selection:
    """One traversal's proposed roots and evidence for every observed descendant."""

    actions: list[Action] = field(default_factory=list)
    evidence: dict[str, dict[str, object]] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)


# pylint: disable-next=too-few-public-methods  # reason: one traversal owns selection and source-evidence state
class JournalSelection:
    """Keep exact recorded sources where proven; never promote children of failed/incomplete roots."""

    def __init__(self, steps: dict[str, JournalStep], checkpoint: Callable[[], None]) -> None:
        self._steps = steps
        self._checkpoint = checkpoint
        self._children: dict[str, list[str]] = {}
        self._result = Selection(evidence={identity: step.evidence() for identity, step in steps.items()})
        for identity, step in steps.items():
            if step.event.parent_id in steps:
                self._children.setdefault(step.event.parent_id, []).append(identity)

    def select(self) -> Selection:
        """Traverse observed roots in append order, returning independent source-indexed evidence."""
        for identity, step in self._steps.items():
            if step.event.parent_id not in self._steps:
                if step.event.parent_id is not None:
                    self._result.warnings.append(f"{identity}: missing parent; observed path only")
                self._visit(identity)
        return self._result

    def _visit(self, identity: str) -> None:
        self._checkpoint()
        step = self._steps[identity]
        if step.event.status != "ok":
            self._mark(identity, "excluded", f"status_{step.event.status}")
            self._result.warnings.append(f"{identity}: excluded {step.event.status} invocation and descendants")
            return
        if step.started is None:
            self._result.warnings.append(f"{identity}: completion without a start snapshot; source is partial")
        action, reasons = self._action(step)
        if not reasons:
            index = len(self._result.actions)
            self._result.actions.append(action)
            evidence = self._result.evidence[identity]
            evidence.update(emission="recorded_source", action_index=index)
            if step.event.command == "AC_retry":
                evidence["retry_attempts"] = self._retry_attempts(identity, action)
            for child in self._children.get(identity, []):
                self._mark(child, "covered_by_parent", "recorded_parent_source", covered_by=identity)
            return
        self._result.evidence[identity]["reasons"] = list(reasons)
        if step.event.command == "AC_parallel":
            self._mark(identity, "excluded", "parallel_order_not_reconstructable")
            self._result.warnings.append(f"{identity}: parallel source unavailable; no sequential replay inferred")
            return
        children = self._children.get(identity, [])
        if children:
            self._result.evidence[identity]["emission"] = "observed_path"
            self._result.warnings.append(f"{identity}: recorded control source unavailable; observed path only")
            for child in children:
                self._visit(child)
        else:
            self._result.warnings.append(f"{identity}: excluded non-replayable recorded input")

    def _action(self, step: JournalStep) -> tuple[Action, tuple[str, ...]]:
        try:
            action, reasons = prepare_action(step)
            if reasons:
                return action, reasons
            validate_candidate_actions([action])
            if not self._body_matches(step.event.step_id, action):
                return action, ("missing_or_inconsistent_control_source",)
            return action, ()
        except (AutoControlException, ValueError, TypeError, RecursionError) as error:
            raise_if_run_interrupted(error)
            return [], ("invalid_command_schema",)

    def _body_matches(self, identity: str, action: Action) -> bool:
        children = self._children.get(identity, [])
        name = cast(str, action[0])
        if not children or name not in FLOW_BODY_KEYS and name not in FLOW_BRANCH_LIST_KEYS:
            return True
        sources = {_fingerprint(cast(Action, child)) for child in source_children(action)}
        for child in children:
            recorded, reasons = prepare_action(self._steps[child])
            if reasons or _fingerprint(recorded) not in sources:
                return False
        return True

    def _mark(self, identity: str, emission: str, reason: str, *, covered_by: str = "") -> None:
        self._checkpoint()
        evidence = self._result.evidence[identity]
        evidence.update(emission=emission, reasons=[reason])
        if covered_by:
            evidence["covered_by"] = covered_by
        for child in self._children.get(identity, []):
            self._mark(child, emission, reason, covered_by=covered_by)

    def _retry_attempts(self, identity: str, action: Action) -> object:
        fingerprints = _retry_source(action)
        if not fingerprints:
            return [] if not self._children.get(identity) else None
        attempts: list[list[str]] = []
        current: list[str] = []
        for child in self._children.get(identity, []):
            step = self._steps[child]
            recorded, reasons = prepare_action(step)
            if reasons or _fingerprint(recorded) != fingerprints[len(current)]:
                self._result.warnings.append(f"{identity}: retry attempt boundaries unavailable")
                return None
            current.append(child)
            if step.event.status != "ok" or len(current) == len(fingerprints):
                attempts.append(current)
                current = []
        if current:
            attempts.append(current)
        return attempts


def _fingerprint(action: Action) -> str:
    normalized = action[:1] if len(action) == 2 and action[1] == {} else action
    return json.dumps(normalized, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _retry_source(action: Action) -> list[str]:
    params = cast(dict[str, object], action[1])
    source = params.get("body", [])
    return [_fingerprint(cast(Action, item)) for item in source] if isinstance(source, list) else []
