"""Immutable template-candidate previews, verification and atomic transition results."""
from dataclasses import asdict, dataclass, field
from typing import Literal, Optional

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.secret_scope import scrub_secret_data
from je_auto_control.utils.self_healing.evaluation import HealingComparison


class TemplateRevisionError(AutoControlException, ValueError):
    """A template candidate or its fixed-frame verification is invalid."""


class TemplateRevisionConflict(AutoControlException, RuntimeError):
    """A reviewed revision or active template no longer matches the requested transition."""


@dataclass(frozen=True)
# pylint: disable-next=too-many-instance-attributes  # reason: immutable version and file-state values
class TemplateCandidateState:
    """Current file content relative to a saved candidate; this is not operation verification."""

    revision: str
    bundle_path: str
    template_path: str
    original_hash: str
    candidate_hash: str
    current_hash: Optional[str]
    state: Literal["original", "candidate", "conflict", "missing"]
    image_format: str
    original_size: tuple[int, int]
    candidate_size: tuple[int, int]
    threshold: float = 0.9

    def to_dict(self) -> dict[str, object]:
        """Return sanitized metadata without template pixels."""
        return _safe(asdict(self))


@dataclass(frozen=True)
class TemplateCandidatePreview:
    """Bounded PNG thumbnails of the actual original and encoded candidate pixels."""

    state: TemplateCandidateState
    original_png: bytes = field(repr=False)
    candidate_png: bytes = field(repr=False)

    def to_dict(self) -> dict[str, object]:
        """Expose version metadata; Python/MCP/GUI consumers receive thumbnails separately."""
        return self.state.to_dict()


@dataclass(frozen=True)
class TemplateCandidateVerification:
    """Fixed-frame localization evidence; eligible does not assert a native operation succeeded."""

    state: TemplateCandidateState
    comparison: HealingComparison
    eligible: bool
    reasons: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        """Return shared comparison populations and explicit eligibility reasons."""
        return {"state": self.state.to_dict(), "comparison": self.comparison.to_dict(),
                "eligible": self.eligible, "reasons": list(self.reasons)}


@dataclass(frozen=True)
class TemplateCandidateTransition:
    """An explicit atomic file transition; repeating the same resulting content is unchanged."""

    state: TemplateCandidateState
    changed: bool
    verification: Optional[TemplateCandidateVerification] = None

    def to_dict(self) -> dict[str, object]:
        """Return the current version and any fixed-frame acceptance evidence."""
        return {"state": self.state.to_dict(), "changed": self.changed,
                "verification": self.verification.to_dict() if self.verification is not None else None}


def _safe(value: dict[str, object]) -> dict[str, object]:
    data = scrub_secret_data(value)
    if not isinstance(data, dict):
        raise TemplateRevisionError("template candidate metadata must be an object")
    return data
