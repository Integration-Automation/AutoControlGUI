"""Screenshot redaction layer.

PII detectors + bbox-blur for screenshots before they leave the host
(VLM upload, audit log, REST response). Pluggable policies and an
opt-in env var so existing pipelines keep their old behaviour.

Public surface::

    from je_auto_control.utils.redaction import (
        RedactionEngine, RedactionPolicy,
        POLICY_OFF, POLICY_MODERATE, POLICY_STRICT,
        policy_from_name, redact_png_bytes,
    )
"""
from __future__ import annotations

import os
from typing import Any, Dict, Optional, Tuple

from je_auto_control.utils.redaction.engine import (
    RedactionEngine, RedactionResult,
)
from je_auto_control.utils.redaction.policies import (
    DETECTOR_CREDIT_CARD, DETECTOR_EMAIL, DETECTOR_PASSWORD_FIELD,
    DETECTOR_PHONE, DETECTOR_SSN,
    POLICY_MODERATE, POLICY_OFF, POLICY_STRICT,
    RedactionPolicy, policy_from_name,
)
from je_auto_control.utils.redaction.rules import (
    BoundingBox, merge_boxes,
)


_ENV_POLICY = "JE_AUTOCONTROL_REDACTION"


def default_policy() -> RedactionPolicy:
    """Resolve the active policy from the ``JE_AUTOCONTROL_REDACTION`` env var.

    Returns :data:`POLICY_OFF` when the variable is unset / empty so
    headless tests don't see redaction kick in unexpectedly.
    """
    return policy_from_name(os.environ.get(_ENV_POLICY))


def redact_png_bytes(png_bytes: bytes,
                     policy: Optional[RedactionPolicy] = None,
                     context: Optional[Dict[str, Any]] = None,
                     ) -> Tuple[bytes, RedactionResult]:
    """Convenience wrapper: build an engine, redact, return PNG bytes."""
    engine = RedactionEngine(policy or default_policy())
    return engine.redact_bytes(png_bytes, context)


__all__ = [
    "BoundingBox",
    "DETECTOR_CREDIT_CARD", "DETECTOR_EMAIL", "DETECTOR_PASSWORD_FIELD",
    "DETECTOR_PHONE", "DETECTOR_SSN",
    "POLICY_MODERATE", "POLICY_OFF", "POLICY_STRICT",
    "RedactionEngine", "RedactionPolicy", "RedactionResult",
    "default_policy", "merge_boxes", "policy_from_name",
    "redact_png_bytes",
]
