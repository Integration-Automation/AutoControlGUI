"""Candidate template revisions: propose, preview, accept, revert.

A locator that "healed" hands back a point, and the tempting next step is to
crop the screen there and overwrite the template. That turns one unverified
answer into every later answer. Here a new template image is only ever a
**candidate**:

1. :meth:`TemplateRevisionStore.propose` copies the candidate into the store.
   The live template is not touched.
2. :meth:`~TemplateRevisionStore.preview` shows both files side by side and,
   given a labelled dataset, runs the current and the candidate template over
   the *same* frames with :func:`evaluation.evaluate_locators`. A candidate
   that hits at least one target correctly, raises no false positive and is
   correct at least as often as the current template is marked ``validated``.
3. :meth:`~TemplateRevisionStore.accept` replaces the live template — after
   backing it up — and refuses an unvalidated candidate unless the caller
   says ``allow_unvalidated=True``.
4. :meth:`~TemplateRevisionStore.revert` puts the backup back.

Accept and revert both check the live file's hash first: a template that
changed underneath a revision is reported, never silently overwritten.
"""
from __future__ import annotations

import hashlib
import os
import re
import threading
import uuid
from dataclasses import asdict, dataclass, fields, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Union

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.json_store.json_store import (
    atomic_write_bytes, read_json_dict, write_json_dict,
)
from je_auto_control.utils.self_healing.evaluation import (
    EvaluationSample, VersionReport, evaluate_locators,
)

STATUS_PENDING = "pending"
STATUS_ACCEPTED = "accepted"
STATUS_REVERTED = "reverted"

VERSION_CURRENT = "current"
VERSION_CANDIDATE = "candidate"

_ID_PATTERN = re.compile(r"^[0-9a-f]{12}$")
_INDEX_NAME = "index.json"

PathLike = Union[str, "os.PathLike[str]"]


class TemplateRevisionError(AutoControlException, RuntimeError):
    """A template revision could not be proposed, accepted or reverted."""


@dataclass(frozen=True)
class TemplateRevision:
    """One candidate replacement for a template image."""

    revision_id: str
    template_path: str
    candidate_file: str
    status: str
    created_at: str
    #: Hash of the live template when the candidate was proposed.
    previous_sha256: str
    candidate_sha256: str
    source: str = "manual"
    note: Optional[str] = None
    validated: bool = False
    #: Counts from the last preview that ran a dataset, or ``None``.
    validation: Optional[Dict[str, Any]] = None
    backup_file: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """JSON-safe snapshot."""
        return asdict(self)


def default_revision_root() -> Path:
    """``~/.je_auto_control/template_revisions``, resolved at call time."""
    return Path.home() / ".je_auto_control" / "template_revisions"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _existing_file(path: PathLike, what: str) -> Path:
    resolved = Path(os.path.realpath(os.fspath(path)))
    if not resolved.is_file():
        raise TemplateRevisionError(f"{what} is not a file: {path!r}")
    return resolved


def _file_facts(path: Path) -> Dict[str, Any]:
    """Size, hash and — when the file decodes as an image — pixel dimensions."""
    facts: Dict[str, Any] = {"path": str(path), "bytes": path.stat().st_size,
                             "sha256": _sha256(path), "width": None, "height": None}
    try:
        import cv2
        from je_auto_control.utils.cv2_utils.image_file import read_image
        image = read_image(str(path), cv2.IMREAD_UNCHANGED)
    except (ImportError, ValueError):
        return facts
    facts["height"], facts["width"] = int(image.shape[0]), int(image.shape[1])
    return facts


def _is_validated(current: VersionReport, candidate: VersionReport) -> bool:
    return (candidate.correct >= 1 and candidate.false_positive == 0
            and candidate.error == 0 and candidate.correct >= current.correct)


class TemplateRevisionStore:
    """Thread-safe store of candidate template revisions under one directory."""

    def __init__(self, root: Optional[PathLike] = None) -> None:
        # As HealEventLog: only an explicit root is kept, the default follows HOME.
        self._explicit_root: Optional[Path] = None if root is None else Path(root)
        self._lock = threading.Lock()

    @property
    def root(self) -> Path:
        """Directory holding the index, the candidates and the backups."""
        return self._explicit_root or default_revision_root()

    # --- index -----------------------------------------------------------

    def _load(self) -> Dict[str, TemplateRevision]:
        known = {spec.name for spec in fields(TemplateRevision)}
        revisions: Dict[str, TemplateRevision] = {}
        for raw in read_json_dict(self.root / _INDEX_NAME).get("revisions", []):
            if not isinstance(raw, dict):
                continue
            try:
                revision = TemplateRevision(**{k: v for k, v in raw.items() if k in known})
            except TypeError:
                continue
            revisions[revision.revision_id] = revision
        return revisions

    def _save(self, revisions: Mapping[str, TemplateRevision]) -> None:
        write_json_dict(self.root / _INDEX_NAME,
                        {"revisions": [item.to_dict() for item in revisions.values()]})

    def _require(self, revisions: Mapping[str, TemplateRevision],
                 revision_id: str) -> TemplateRevision:
        if not isinstance(revision_id, str) or not _ID_PATTERN.match(revision_id):
            raise TemplateRevisionError(f"not a revision id: {revision_id!r}")
        revision = revisions.get(revision_id)
        if revision is None:
            raise TemplateRevisionError(f"no such template revision: {revision_id}")
        return revision

    def _put(self, revision: TemplateRevision) -> TemplateRevision:
        """Write ``revision`` into the index under the lock the caller holds."""
        revisions = self._load()
        revisions[revision.revision_id] = revision
        self._save(revisions)
        return revision

    # --- public API ------------------------------------------------------

    def list_revisions(self) -> List[TemplateRevision]:
        """Every revision, oldest first."""
        with self._lock:
            return list(self._load().values())

    def get(self, revision_id: str) -> TemplateRevision:
        """The revision ``revision_id`` names; unknown ids raise."""
        with self._lock:
            return self._require(self._load(), revision_id)

    def propose(self, template_path: PathLike, candidate_path: PathLike, *,
                source: str = "manual", note: Optional[str] = None) -> TemplateRevision:
        """Store ``candidate_path`` as a pending replacement for ``template_path``.

        The live template is left exactly as it is.
        """
        template = _existing_file(template_path, "template")
        candidate = _existing_file(candidate_path, "candidate")
        previous, proposed = _sha256(template), _sha256(candidate)
        if previous == proposed:
            raise TemplateRevisionError("the candidate is identical to the current template")
        revision_id = uuid.uuid4().hex[:12]
        stored = self.root / revision_id / f"candidate{candidate.suffix.lower()}"
        with self._lock:
            stored.parent.mkdir(parents=True, exist_ok=True)
            atomic_write_bytes(stored, candidate.read_bytes())
            return self._put(TemplateRevision(
                revision_id=revision_id, template_path=str(template),
                candidate_file=str(stored), status=STATUS_PENDING,
                created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
                previous_sha256=previous, candidate_sha256=proposed,
                source=str(source), note=note))

    def preview(self, revision_id: str, *,
                samples: Optional[Sequence[EvaluationSample]] = None,
                dataset_path: Optional[PathLike] = None,
                detect_threshold: float = 0.9) -> Dict[str, Any]:
        """Describe what accepting would change; validate it when given frames.

        With ``samples`` or ``dataset_path`` the current and the candidate
        template are run over the same frames and the result decides the
        revision's ``validated`` flag. Without either, nothing is validated
        and the flag keeps its value. Nothing is written to the template.
        """
        revision = self.get(revision_id)
        payload: Dict[str, Any] = {
            "revision": revision.to_dict(),
            "current": _file_facts(_existing_file(revision.template_path, "template")),
            "candidate": _file_facts(_existing_file(revision.candidate_file, "candidate")),
            "comparison": None,
        }
        frames = _preview_samples(samples, dataset_path)
        if frames is None:
            return payload
        from je_auto_control.utils.self_healing.eval_strategies import (
            template_match_strategy,
        )
        comparison = evaluate_locators(frames, {
            VERSION_CURRENT: template_match_strategy(
                detect_threshold, template=revision.template_path),
            VERSION_CANDIDATE: template_match_strategy(
                detect_threshold, template=revision.candidate_file),
        })
        current, candidate = (comparison.report(VERSION_CURRENT),
                              comparison.report(VERSION_CANDIDATE))
        validated = _is_validated(current, candidate)
        with self._lock:
            latest = self._require(self._load(), revision_id)
            revised = replace(latest, validated=validated, validation={
                "detect_threshold": float(detect_threshold),
                VERSION_CURRENT: current.to_dict(),
                VERSION_CANDIDATE: candidate.to_dict(),
            })
            updated = self._put(revised)  # NOSONAR python:S5655  # reason: replace() returns its argument's type
        payload["revision"] = updated.to_dict()
        payload["comparison"] = comparison.to_dict()
        return payload

    def accept(self, revision_id: str, *,
               allow_unvalidated: bool = False) -> TemplateRevision:
        """Replace the live template with the candidate, keeping a backup."""
        with self._lock:
            revision = self._require(self._load(), revision_id)
            if revision.status == STATUS_ACCEPTED:
                raise TemplateRevisionError(f"revision {revision_id} is already accepted")
            if not revision.validated and not allow_unvalidated:
                raise TemplateRevisionError(
                    f"revision {revision_id} has not been validated; preview it against "
                    "labelled frames, or pass allow_unvalidated=True to accept it anyway")
            template = _existing_file(revision.template_path, "template")
            candidate = _existing_file(revision.candidate_file, "candidate")
            if _sha256(template) != revision.previous_sha256:
                raise TemplateRevisionError(
                    f"{template} changed since revision {revision_id} was proposed; "
                    "propose a new revision against the current file")
            backup = candidate.parent / f"backup{template.suffix.lower()}"
            atomic_write_bytes(backup, template.read_bytes())
            atomic_write_bytes(template, candidate.read_bytes())
            accepted = replace(revision, status=STATUS_ACCEPTED, backup_file=str(backup))
            return self._put(accepted)  # NOSONAR python:S5655  # reason: replace() returns its argument's type

    def revert(self, revision_id: str) -> TemplateRevision:
        """Restore the template an accepted revision replaced."""
        with self._lock:
            revision = self._require(self._load(), revision_id)
            if revision.status != STATUS_ACCEPTED or revision.backup_file is None:
                raise TemplateRevisionError(
                    f"revision {revision_id} is {revision.status}, not accepted")
            template = _existing_file(revision.template_path, "template")
            backup = _existing_file(revision.backup_file, "backup")
            if _sha256(template) != revision.candidate_sha256:
                raise TemplateRevisionError(
                    f"{template} changed since revision {revision_id} was accepted; "
                    "reverting would discard that change")
            atomic_write_bytes(template, backup.read_bytes())
            reverted = replace(revision, status=STATUS_REVERTED)
            return self._put(reverted)  # NOSONAR python:S5655  # reason: replace() returns its argument's type


def _preview_samples(samples: Optional[Sequence[EvaluationSample]],
                     dataset_path: Optional[PathLike],
                     ) -> Optional[Sequence[EvaluationSample]]:
    if samples is not None and dataset_path is not None:
        raise TemplateRevisionError("pass samples or dataset_path, not both")
    if dataset_path is None:
        return samples
    from je_auto_control.utils.self_healing.eval_strategies import (
        load_evaluation_dataset,
    )
    return load_evaluation_dataset(dataset_path).samples


default_template_revisions = TemplateRevisionStore()


def propose_template_revision(template_path: PathLike, candidate_path: PathLike, *,
                              source: str = "manual", note: Optional[str] = None,
                              store: Optional[TemplateRevisionStore] = None,
                              ) -> TemplateRevision:
    """Store a candidate replacement for a template; the template is not changed."""
    return (store or default_template_revisions).propose(
        template_path, candidate_path, source=source, note=note)


def preview_template_revision(revision_id: str, *,
                              samples: Optional[Sequence[EvaluationSample]] = None,
                              dataset_path: Optional[PathLike] = None,
                              detect_threshold: float = 0.9,
                              store: Optional[TemplateRevisionStore] = None,
                              ) -> Dict[str, Any]:
    """Show current vs candidate and, given labelled frames, validate the candidate."""
    return (store or default_template_revisions).preview(
        revision_id, samples=samples, dataset_path=dataset_path,
        detect_threshold=detect_threshold)


def accept_template_revision(revision_id: str, *, allow_unvalidated: bool = False,
                             store: Optional[TemplateRevisionStore] = None,
                             ) -> TemplateRevision:
    """Replace the live template with a validated candidate, keeping a backup."""
    return (store or default_template_revisions).accept(
        revision_id, allow_unvalidated=allow_unvalidated)


def revert_template_revision(revision_id: str, *,
                             store: Optional[TemplateRevisionStore] = None,
                             ) -> TemplateRevision:
    """Put back the template an accepted revision replaced."""
    return (store or default_template_revisions).revert(revision_id)


def list_template_revisions(store: Optional[TemplateRevisionStore] = None,
                            ) -> List[TemplateRevision]:
    """Every stored revision, oldest first."""
    return (store or default_template_revisions).list_revisions()


__all__ = [
    "STATUS_ACCEPTED", "STATUS_PENDING", "STATUS_REVERTED",
    "TemplateRevision", "TemplateRevisionError", "TemplateRevisionStore",
    "accept_template_revision", "default_revision_root",
    "default_template_revisions", "list_template_revisions",
    "preview_template_revision", "propose_template_revision",
    "revert_template_revision",
]
