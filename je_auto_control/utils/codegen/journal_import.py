"""Generate review-only code and provenance from one selected structured-journal run."""
import json
from hashlib import sha256
from pathlib import Path
from typing import Callable, Optional, cast

from je_auto_control.utils.codegen.candidate_models import CandidateGenerationError, CandidateScript
from je_auto_control.utils.codegen.candidate_validation import (
    dry_run_candidate, validate_candidate_actions, validate_generated_code,
)
from je_auto_control.utils.codegen.codegen import generate_code
from je_auto_control.utils.codegen.journal_selection import JournalSelection
from je_auto_control.utils.codegen.journal_source import check_source_path, load_source
from je_auto_control.utils.codegen.journal_steps import reconcile
from je_auto_control.utils.logging.secret_scope import scrub_secret_data
from je_auto_control.utils.path_guard.policy import PathPolicy


def generate_candidate_from_log(path: str | Path, *, run_id: str, target: str = "pytest", style: str = "actions",
                                  observer: Optional[Callable[[int], None]] = None,
                                  path_policy: Optional[PathPolicy] = None) -> CandidateScript:
    """Validate a bounded journal and render a selected run, without dispatch or secret resolution.

    Reconcile durable start/completion pairs and parent edges. Only successful
    completed roots are proposed; failed, cancelled, skipped, dry-run and incomplete
    roots exclude their descendants. Valid recorded blocks retain their exact source
    and cover observed children, avoiding duplicate iterations/retries. If source is
    insufficient, successful sequential children form an explicitly observed path.
    Parallel fallback is excluded because append order is not a replay schedule.

    Every candidate remains observed-path-only: a journal does not prove the whole
    original workflow or its external dependencies. Evidence records every selected
    step, including exclusions and retry attempts where boundaries are provable.
    Unknown/redacted inputs are never substituted with successful-looking actions.
    AST/signature/dry-run checks do not claim device effects or native success.
    """
    if target not in ("pytest", "python", "robot") or style not in ("actions", "calls"):
        raise CandidateGenerationError("unknown candidate target or style")
    source = load_source(path, run_id, observer, path_policy)
    count = source.record_count

    def checkpoint() -> None:
        nonlocal count
        count += 1
        check_source_path(source.path, path_policy)
        if observer is not None:
            observer(count)
        check_source_path(source.path, path_policy)

    steps = reconcile(source)
    selected = JournalSelection(steps, checkpoint).select()
    checkpoint()
    validate_candidate_actions(selected.actions)
    code = (generate_code(selected.actions, target=target, style=style, name="journal_candidate")
            if selected.actions else _empty_code(target))
    validate_generated_code(code, target)
    dry_run_candidate(selected.actions)
    checkpoint()
    warnings = ["Observed journal run only; external inputs and native results are not verified."] + selected.warnings
    if source.torn_tail:
        warnings.append("Uncommitted final journal fragment ignored; no completion inferred.")
    if not selected.actions:
        warnings.append("No replayable completed actions; generated code fails explicitly when invoked.")
    manifest = {"schema_version": 1, "journal_schema_version": 1, "run_id": run_id,
                "source_path": str(source.path), "source_sha256": source.sha256,
                "source_records": source.record_count, "selected_snapshots": len(source.rows),
                "ignored_torn_tail": source.torn_tail, "target": target, "style": style,
                "observed_path_only": True, "selection_policy": "successful_completed_roots_with_recorded_sources",
                "steps": list(selected.evidence.values()), "code_sha256": sha256(code.encode("utf-8")).hexdigest(),
                "actions_sha256": _action_hash(selected.actions),
                "validation": {"command": "passed", "static": "passed", "dry_run": "passed", "dispatches": 0,
                               "static_scope": "python_ast" if target != "robot" else "robot_renderer_embedded_ast",
                               "dynamic_dependencies": "unverified"}}
    data = _bounded_result({"code": code, "manifest": manifest, "actions": selected.actions, "warnings": warnings})
    checkpoint()
    return CandidateScript(cast(str, data["code"]), cast(dict[str, object], data["manifest"]),
                           tuple(cast(list[str], data["warnings"])), cast(list[list[object]], data["actions"]))


def _action_hash(actions: list[list[object]]) -> str:
    data = json.dumps(actions, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    return sha256(data).hexdigest()


def _bounded_result(payload: dict[str, object]) -> dict[str, object]:
    if scrub_secret_data(payload) != payload:
        raise CandidateGenerationError("candidate output conflicts with the active resolved-secret mask")
    rendered = json.dumps(payload, allow_nan=False, ensure_ascii=True)
    if len(rendered.encode("ascii")) > 16 * 1024 * 1024:
        raise CandidateGenerationError("candidate review bundle exceeds 16 MiB")
    return cast(dict[str, object], json.loads(rendered))


def _empty_code(target: str) -> str:
    message = "No replayable completed actions in the selected journal run"
    if target == "robot":
        return f"*** Test Cases ***\nJournal Candidate\n    Fail    {message}\n"
    name = "test_journal_candidate" if target == "pytest" else "journal_candidate"
    code = f"def {name}():\n    raise RuntimeError({message!r})\n"
    return code if target == "pytest" else code + f'\nif __name__ == "__main__":\n    {name}()\n'
