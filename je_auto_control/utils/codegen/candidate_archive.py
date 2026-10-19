"""Atomically export a reviewed candidate's source, actions and provenance as one ZIP artifact."""
import io
import json
from hashlib import sha256
from pathlib import Path
from typing import Callable, Optional, cast

from je_auto_control.utils.action_journal.inspection import _checked_path
from je_auto_control.utils.codegen.candidate_models import CandidateGenerationError, CandidateScript
from je_auto_control.utils.codegen.candidate_validation import validate_candidate_actions, validate_generated_code
from je_auto_control.utils.json_store.json_store import atomic_write_bytes
from je_auto_control.utils.path_guard.policy import PathPolicy


def write_candidate_archive(candidate: CandidateScript, path: str | Path, *,
                              observer: Optional[Callable[[int], None]] = None,
                              path_policy: Optional[PathPolicy] = None) -> Path:
    """Export one explicit ZIP, replacing it atomically without executing any generated code.

    The archive contains candidate.py/candidate.robot, actions.json, manifest.json
    and README.txt. Source/code/action hashes are review provenance, not a digital
    signature. Current source and destination roots are checked around checkpoints.
    A post-commit cancellation never relabels a completed export as cancelled.
    """
    if observer is not None:
        observer(0)
    destination = _checked_path(path, path_policy)
    if destination.suffix.lower() != ".zip":
        raise CandidateGenerationError("candidate archive path must end in .zip")
    payload = candidate.to_dict()
    candidate = CandidateScript(cast(str, payload["code"]), cast(dict[str, object], payload["manifest"]),
                                tuple(cast(list[str], payload["warnings"])),
                                cast(list[list[object]], payload["actions"]))
    source = _source_path(candidate, path_policy)
    if destination == source:
        raise CandidateGenerationError("candidate archive must not replace the source journal")
    _validate(candidate)
    data = _archive(candidate, payload)
    if observer is not None:
        observer(1)
    if _checked_path(destination, path_policy) != destination or _source_path(candidate, path_policy) != source:
        raise CandidateGenerationError("candidate archive binding changed")
    atomic_write_bytes(destination, data)
    return destination


def validate_candidate_review(candidate: CandidateScript, policy: Optional[PathPolicy] = None) -> None:
    """Check cached review integrity and current source roots before an explicit editor import."""
    candidate.to_dict()
    _source_path(candidate, policy)
    _validate(candidate)


def _source_path(candidate: CandidateScript, policy: Optional[PathPolicy]) -> Path:
    value = candidate.manifest.get("source_path")
    if not isinstance(value, str) or not Path(value).is_absolute():
        raise CandidateGenerationError("candidate has no canonical source path")
    source = _checked_path(value, policy)
    if str(source) != value:
        raise CandidateGenerationError("candidate source binding changed")
    return source


def _validate(candidate: CandidateScript) -> None:
    target = candidate.manifest.get("target")
    actions = json.dumps(candidate.actions, sort_keys=True, separators=(",", ":"), allow_nan=False).encode("utf-8")
    if (target not in ("pytest", "python", "robot")
            or candidate.manifest.get("code_sha256") != sha256(candidate.code.encode("utf-8")).hexdigest()
            or candidate.manifest.get("actions_sha256") != sha256(actions).hexdigest()):
        raise CandidateGenerationError("candidate source/actions changed after review")
    validate_candidate_actions(candidate.actions)
    validate_generated_code(candidate.code, str(target))


def _archive(candidate: CandidateScript, payload: dict[str, object]) -> bytes:
    # pylint: disable-next=import-outside-toplevel  # reason: ZIP tooling loads only for an explicit export
    import zipfile
    buffer = io.BytesIO()
    target = "candidate.robot" if candidate.manifest["target"] == "robot" else "candidate.py"
    manifest = dict(candidate.manifest, warnings=payload["warnings"])
    files = {target: candidate.code, "actions.json": json.dumps(payload["actions"], indent=2, ensure_ascii=True),
             "manifest.json": json.dumps(manifest, indent=2, ensure_ascii=True),
             "README.txt": "Observed journal candidate only. Review warnings and provenance before separate replay.\n"
                           "Generation, static validation and dry-run issue no device actions.\n"}
    if sum(len(value.encode("utf-8")) for value in files.values()) > 16 * 1024 * 1024:
        raise CandidateGenerationError("candidate archive content exceeds 16 MiB")
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, content in files.items():
            archive.writestr(name, content)
    return buffer.getvalue()
