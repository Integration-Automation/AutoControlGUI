"""Runtime self-healing provenance without capturing frames or asserting recovery."""
from __future__ import annotations

import json
import math
from dataclasses import dataclass, field
from hashlib import sha256
from typing import Any, Optional
from uuid import uuid4

from je_auto_control.utils.cv2_utils.locator_frame import LocatorFrameOwner
from je_auto_control.utils.logging.secret_scope import scrub_secret_text


@dataclass
# pylint: disable-next=too-many-instance-attributes  # reason: one serializable attempt's evidence and independent state
class AttemptEvidence:
    """One attempt's measured strategy durations and non-owning capture provenance."""

    source: LocatorFrameOwner
    run_id: str
    step_id: str
    locator_id: str
    configuration: dict[str, object]
    strategy_times_ms: dict[str, float] = field(default_factory=dict)
    operation: str = "locate"
    operation_status: str = "not_requested"
    operation_error: Optional[str] = None
    verification_description: Optional[str] = None
    verification_frame_hash: Optional[str] = None
    verification_backend: Optional[str] = None
    verification_model: Optional[str] = None
    verified: Optional[bool] = None
    verification_error: Optional[str] = None

    def fields(self) -> dict[str, Any]:
        """Snapshot metadata; absence of a real frame/model/verification stays explicit."""
        frame = self.source.captured
        version = self._version()
        return {
            "schema_version": 2, "run_id": self.run_id, "step_id": self.step_id,
            "locator_id": self.locator_id, "locator_version": version,
            "frame_hash": sha256(frame.png).hexdigest() if frame is not None else None,
            "origin": list(frame.origin) if frame is not None else None,
            "frame_size": list(frame.size) if frame is not None else None, "scale": 1.0,
            "screen_region": self.source.region, "capture_ms": self.source.capture_ms,
            "strategy_times_ms": dict(self.strategy_times_ms),
            "backend": self.source.backend, "model": self.source.model,
            "cost_usd": None, "verified": self.verified, "operation": self.operation,
            "operation_status": self.operation_status, "operation_error": self.operation_error,
            "verification_frame_hash": self.verification_frame_hash,
            "verification_backend": self.verification_backend, "verification_model": self.verification_model,
            "verification_error": self.verification_error,
            "verification_description": self.verification_description,
        }


    def _version(self) -> Optional[str]:
        if self.source.template_hash is not None:
            payload = {**self.configuration, "template_hash": self.source.template_hash}
        elif not self.configuration["template_configured"] and self.source.model is not None:
            payload = {**self.configuration, "backend": _masked(self.source.backend),
                       "resolved_model": _masked(self.source.model)}
        else:
            return None
        return sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def attempt_evidence(source: LocatorFrameOwner, template_path: Optional[str], description: Optional[str],
                      threshold: float, model: Optional[str]) -> AttemptEvidence:
    """Reuse the active journal's run/step identity, or allocate independent local IDs."""
    # pylint: disable-next=import-outside-toplevel  # reason: journal capture imports the executor during facade setup
    from je_auto_control.utils.action_journal.capture import current_journal
    binding = current_journal()
    run_id = binding.run_id if binding is not None else uuid4().hex
    step_id = binding.parent_id if binding is not None and binding.parent_id is not None else uuid4().hex
    identity = scrub_secret_text(template_path or description or "")
    configuration: dict[str, object] = {
        "description": _masked(description), "model": _masked(model), "threshold": _threshold(threshold),
        "screen_region": source.region,
        "template_configured": bool(template_path),
    }
    return AttemptEvidence(source, run_id, step_id, sha256(identity.encode("utf-8")).hexdigest(), configuration)


def _masked(value: Optional[str]) -> Optional[str]:
    return scrub_secret_text(value) if value is not None else None


def _threshold(value: float) -> Optional[float]:
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if math.isfinite(number) else None
