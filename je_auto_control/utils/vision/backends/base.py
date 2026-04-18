"""Abstract VLM (vision-language model) backend."""
from typing import Optional, Tuple


class VLMNotAvailableError(RuntimeError):
    """Raised when no VLM backend can be initialised."""


class VLMBackend:
    """Each backend turns a screenshot + description into pixel coordinates."""

    name: str = "abstract"
    available: bool = False

    def locate(self, image_bytes: bytes, description: str,
               model: Optional[str] = None,
               image_mime: str = "image/png",
               ) -> Optional[Tuple[int, int]]:
        raise NotImplementedError
