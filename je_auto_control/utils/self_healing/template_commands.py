"""JSON-safe template-candidate adapters with bounded input PNG files."""
from typing import Callable, Optional

from je_auto_control.utils.path_guard.policy import PathPolicy
from je_auto_control.utils.self_healing.evaluation_io import _bounded_path, _read
from je_auto_control.utils.self_healing.template_candidates import (
    accept_template_candidate, create_template_candidate, preview_template_candidate,
    revert_template_candidate, verify_template_candidate,
)
from je_auto_control.utils.self_healing.template_images import MAX_IMAGE_BYTES
from je_auto_control.utils.self_healing.template_models import TemplateCandidateState


def _create_from_file(template_path: str, candidate_path: str, bundle_path: str, threshold: float = 0.9, *,
                        observer: Optional[Callable[[int], None]] = None,
                        path_policy: Optional[PathPolicy] = None) -> TemplateCandidateState:
    """Read one explicit PNG file while retaining its roots through the final creation checkpoint."""
    source = _bounded_path(candidate_path, path_policy)

    def checkpoint(count: int) -> None:
        _bounded_path(source, path_policy)
        if observer is not None:
            observer(count)
        _bounded_path(source, path_policy)

    checkpoint(0)
    payload = _read(source, MAX_IMAGE_BYTES)
    return create_template_candidate(template_path, payload, bundle_path, threshold=threshold,
                                       observer=checkpoint, path_policy=path_policy)


def _create_candidate_command(template_path: str, candidate_path: str, bundle_path: str,
                                 threshold: float = 0.9) -> dict[str, object]:
    """Create an immutable candidate bundle from an explicit PNG file."""
    return _create_from_file(template_path, candidate_path, bundle_path, threshold).to_dict()


def _preview_candidate_command(bundle_path: str) -> dict[str, object]:
    """Return preview metadata; Python/MCP/GUI can obtain the actual thumbnails."""
    return preview_template_candidate(bundle_path).to_dict()


def _verify_candidate_command(bundle_path: str, dataset_path: str) -> dict[str, object]:
    """Return fixed-frame quality populations and candidate eligibility."""
    return verify_template_candidate(bundle_path, dataset_path).to_dict()


def _accept_candidate_command(bundle_path: str, dataset_path: str, expected_revision: str) -> dict[str, object]:
    """Reverify and activate one explicitly reviewed candidate revision."""
    return accept_template_candidate(bundle_path, dataset_path, expected_revision).to_dict()


def _revert_candidate_command(bundle_path: str, expected_revision: str) -> dict[str, object]:
    """Restore original bytes without overwriting a later edit."""
    return revert_template_candidate(bundle_path, expected_revision).to_dict()
