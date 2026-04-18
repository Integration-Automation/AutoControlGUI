"""Fallback backend when no VLM SDK / API key is available."""
from typing import Optional, Tuple

from je_auto_control.utils.vision.backends.base import (
    VLMBackend, VLMNotAvailableError,
)


class NullVLMBackend(VLMBackend):
    """Backend that always raises an informative error."""

    name = "null"
    available = False

    def __init__(self, reason: str = "no VLM backend available"):
        self._reason = reason

    def locate(self, image_bytes: bytes, description: str,
               model: Optional[str] = None,
               image_mime: str = "image/png",
               ) -> Optional[Tuple[int, int]]:
        raise VLMNotAvailableError(self._reason)
