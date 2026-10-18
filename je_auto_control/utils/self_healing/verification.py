"""Prepared post-click verification, isolated from pre-operation locator pixels."""
from dataclasses import dataclass
from typing import Callable, Optional

from je_auto_control.utils.cv2_utils.locator_frame import provided_locator_frame
from je_auto_control.utils.self_healing.requests import SelfHealRequestError, VerificationRequest
from je_auto_control.utils.vision.backends import get_backend
from je_auto_control.utils.vision.backends.base import VLMNotAvailableError
from je_auto_control.utils.vision.vlm_api import _verify_snapshot


@dataclass(frozen=True)
class VerificationProof:
    """Explicit bool evidence; a callback may have no image or model provenance."""

    verified: bool
    frame_hash: Optional[str] = None
    backend: str = "callback"
    model: Optional[str] = None


def prepare_verification(request: Optional[VerificationRequest],
                          locator_model: Optional[str]) -> Optional[Callable[[], VerificationProof]]:
    """Validate VLM availability before input, without invoking the verification itself."""
    if request is None:
        return None
    if request.verifier is not None:
        callback = request.verifier

        def verify_callback() -> VerificationProof:
            with provided_locator_frame(None):
                result = callback()
            if not isinstance(result, bool):
                raise SelfHealRequestError("verification callback must return bool")
            return VerificationProof(result)

        return verify_callback
    bound = request.backend if request.backend is not None else get_backend()
    if not bound.available:
        raise VLMNotAvailableError("post-click verification backend is unavailable; no input was issued")
    description = request.description
    if description is None:
        raise SelfHealRequestError("verification description is required")
    region = list(request.screen_region) if request.screen_region is not None else None
    model = request.model if request.model is not None else locator_model

    def verify_vlm() -> VerificationProof:
        result = _verify_snapshot(description, region, model, bound)
        return VerificationProof(result.verified, result.frame_hash, result.backend, result.model)

    return verify_vlm
