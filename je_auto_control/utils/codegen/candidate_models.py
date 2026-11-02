"""Reviewable generated source and provenance without automatic replay."""
import json
from dataclasses import dataclass, field
from hashlib import sha256
from typing import cast

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.logging.secret_scope import scrub_secret_data


class CandidateGenerationError(AutoControlException, ValueError):
    """A journal cannot be safely interpreted as a candidate script."""


@dataclass(frozen=True)
class CandidateScript:
    """Source, proposed actions and provenance; validation never means native execution succeeded."""

    code: str
    manifest: dict[str, object]
    warnings: tuple[str, ...]
    actions: list[list[object]] = field(repr=False)
    observed_path_only: bool = True
    _review_hash: str = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_review_hash", sha256(self._encoded()).hexdigest())

    def _payload(self) -> dict[str, object]:
        return {"code": self.code, "manifest": self.manifest, "warnings": list(self.warnings),
                "actions": self.actions, "observed_path_only": self.observed_path_only}

    def _encoded(self) -> bytes:
        try:
            return json.dumps(self._payload(), sort_keys=True, separators=(",", ":"),
                              allow_nan=False, ensure_ascii=True).encode("ascii")
        except (ValueError, TypeError, RecursionError):
            raise CandidateGenerationError("candidate review data is not finite JSON") from None

    def to_dict(self) -> dict[str, object]:
        """Return an independent JSON-safe, secret-sanitized review bundle."""
        encoded = self._encoded()
        if sha256(encoded).hexdigest() != self._review_hash:
            raise CandidateGenerationError("candidate data changed after review")
        payload = self._payload()
        if scrub_secret_data(payload) != payload:
            raise CandidateGenerationError("candidate output conflicts with the active resolved-secret mask")
        return cast(dict[str, object], json.loads(encoded))
