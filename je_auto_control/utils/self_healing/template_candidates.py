"""Explicit template-candidate preview, fixed-frame verification, acceptance and byte-exact rollback."""
from pathlib import Path
from dataclasses import replace
from typing import Callable, Literal, Optional

from je_auto_control.utils.json_store.json_store import _file_lock, atomic_write_bytes
from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.self_healing.evaluation import evaluate_locators
from je_auto_control.utils.self_healing.evaluation_io import _AssetReader, _bounded_path, _load_samples_manifest
from je_auto_control.utils.self_healing.frame_locators import TemplateFrameLocator
from je_auto_control.utils.self_healing.template_bundle import TemplateBundle, create_bundle, read_bundle
from je_auto_control.utils.self_healing.template_images import normalized_png
from je_auto_control.utils.self_healing.template_models import (
    TemplateCandidatePreview, TemplateCandidateState, TemplateCandidateTransition, TemplateCandidateVerification,
    TemplateRevisionConflict, TemplateRevisionError,
)


def create_template_candidate(template_path: str | Path, candidate_png: bytes, bundle_path: str | Path, *,
                                threshold: float = 0.9,
                                observer: Optional[Callable[[int], None]] = None,
                                path_policy: Optional[PathPolicy] = None) -> TemplateCandidateState:
    """Save original/candidate bytes in a new version bundle, leaving the active file untouched.

    Static PNG/JPEG/BMP targets are supported. Supplied PNG candidate pixels are
    encoded in the target format; verification and preview use that exact result.
    Existing bundles are never replaced. This operation performs no device capture.
    """
    return create_bundle(template_path, candidate_png, bundle_path, threshold, path_policy, observer).state(path_policy)


def preview_template_candidate(bundle_path: str | Path, *,
                                 observer: Optional[Callable[[int], None]] = None,
                                 path_policy: Optional[PathPolicy] = None) -> TemplateCandidatePreview:
    """Return current version metadata and two bounded PNG thumbnails without writing a file."""
    if observer is not None:
        observer(0)
    bundle = read_bundle(bundle_path, path_policy)
    original, _, _ = normalized_png(bundle.original, thumbnail=True)
    candidate, _, _ = normalized_png(bundle.candidate, thumbnail=True)
    if observer is not None:
        observer(1)
    return TemplateCandidatePreview(bundle.state(path_policy), original, candidate)


def verify_template_candidate(bundle_path: str | Path, dataset_path: str | Path, *,
                                observer: Optional[Callable[[int], None]] = None,
                                path_policy: Optional[PathPolicy] = None) -> TemplateCandidateVerification:
    """Compare frozen original/candidate pixels on bounded labelled samples, without device effects.

    Eligibility requires at least one labelled target and one expected miss, and
    all labelled cases correct. Unknowns remain unknown. Dataset versions, if
    present, are not used: this bundle supplies both exact image versions.
    Localization eligibility is separate from native operation verification.
    """
    if observer is not None:
        observer(0)
    verified, _ = _verify(read_bundle(bundle_path, path_policy), dataset_path, observer, path_policy)
    return verified


def _verify(bundle: TemplateBundle, dataset: str | Path, observer: Optional[Callable[[int], None]],
               policy: Optional[PathPolicy]) -> tuple[TemplateCandidateVerification, Callable[[], None]]:
    dataset = _bounded_path(dataset, policy)
    reader: Optional[_AssetReader] = None
    last_count = 0
    def check_paths() -> None:
        bundle.checked_target(policy)
        _bounded_path(dataset, policy)
        if reader is not None:
            reader.check_paths()

    def checkpoint(count: int) -> None:
        nonlocal last_count
        last_count = count
        check_paths()
        if observer is not None:
            observer(count)
        check_paths()

    samples, _, reader = _load_samples_manifest(dataset, policy, checkpoint)
    versions = {"original": TemplateFrameLocator(normalized_png(bundle.original)[0], bundle.threshold),
                "candidate": TemplateFrameLocator(normalized_png(bundle.candidate)[0], bundle.threshold)}
    comparison = evaluate_locators(samples, versions, observer=checkpoint)
    _, measured = tuple(comparison.versions.values())
    reasons = []
    if not any(sample.expected_box is not None for sample in samples):
        reasons.append("no_positive_ground_truth")
    if not any(sample.expected_miss for sample in samples):
        reasons.append("no_expected_miss")
    if measured.accuracy.numerator != measured.accuracy.denominator:
        reasons.append("incorrect_labelled_cases")
    state = bundle.state(policy)
    if state.state in ("conflict", "missing"):
        reasons.append("active_template_changed")
    return TemplateCandidateVerification(state, comparison, not reasons, tuple(reasons)), lambda: checkpoint(last_count)


def accept_template_candidate(bundle_path: str | Path, dataset_path: str | Path, expected_revision: str, *,
                                observer: Optional[Callable[[int], None]] = None,
                                path_policy: Optional[PathPolicy] = None) -> TemplateCandidateTransition:
    """Reverify the reviewed candidate and atomically activate it if the original still matches.

    Every acceptance checks the actual dataset again. After the last observer
    checkpoint, a target lock and content comparison guard the single atomic
    replace. A repeated identical result is unchanged. No callback follows commit.
    """
    if observer is not None:
        observer(0)
    bundle = _reviewed(bundle_path, expected_revision, path_policy)
    verified, check_paths = _verify(bundle, dataset_path, observer, path_policy)
    if not verified.eligible:
        if verified.state.state in ("conflict", "missing"):
            raise TemplateRevisionConflict("active template no longer matches this candidate")
        raise TemplateRevisionError("candidate is not eligible: " + ", ".join(verified.reasons))
    state, changed = _transition(bundle, True, path_policy, check_paths=check_paths)
    return TemplateCandidateTransition(state, changed, verified)


def revert_template_candidate(bundle_path: str | Path, expected_revision: str, *,
                                observer: Optional[Callable[[int], None]] = None,
                                path_policy: Optional[PathPolicy] = None) -> TemplateCandidateTransition:
    """Restore saved original bytes only when the current file is this exact candidate.

    Already-original content is unchanged. Intervening edits or missing files are
    conflicts; rollback never overwrites them. The immutable bundle needs no mutable
    active-version pointer, so interruption after replacement leaves inspectable state.
    """
    if observer is not None:
        observer(0)
    bundle = _reviewed(bundle_path, expected_revision, path_policy)
    before_commit = (lambda: observer(1)) if observer is not None else None
    state, changed = _transition(bundle, False, path_policy, check_paths=before_commit)
    return TemplateCandidateTransition(state, changed)


def _reviewed(path: str | Path, revision: str, policy: Optional[PathPolicy]) -> TemplateBundle:
    if not isinstance(revision, str) or len(revision) != 64:
        raise TemplateRevisionError("expected_revision must be the reviewed bundle SHA-256")
    bundle = read_bundle(path, policy)
    if bundle.revision != revision:
        raise TemplateRevisionConflict("candidate bundle differs from the reviewed revision")
    return bundle


def _transition(bundle: TemplateBundle, accept: bool,
                   policy: Optional[PathPolicy], *, check_paths: Optional[Callable[[], None]] = None
                   ) -> tuple[TemplateCandidateState, bool]:
    target = bundle.checked_target(policy)
    with _file_lock(target):
        if check_paths is not None:
            check_paths()
        bundle.check_revision(policy)
        state = bundle.state(policy)
        if state.state in ("conflict", "missing"):
            raise TemplateRevisionConflict("active template changed; refusing to replace it")
        desired: Literal["candidate", "original"] = "candidate" if accept else "original"
        if state.state == desired:
            return state, False
        bundle.checked_target(policy)
        atomic_write_bytes(target, bundle.candidate if accept else bundle.original)
        # Derive the committed state without another fallible read or observer.
        return replace(state, current_hash=state.candidate_hash if accept else state.original_hash,
                       state=desired), True
