"""Anthropic (Claude) VLM backend."""
import base64
import os
from typing import Optional, Tuple

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.vision.backends._parse import (
    LOCATE_PROMPT, parse_coords,
)
from je_auto_control.utils.vision.backends.base import VLMBackend

_DEFAULT_MODEL = "claude-opus-4-7"
_REQUEST_TIMEOUT_S = 30.0
_MAX_TOKENS = 64


class AnthropicVLMBackend(VLMBackend):
    """Call ``claude-*`` models via the ``anthropic`` Python SDK."""

    name = "anthropic"

    def __init__(self) -> None:
        self._client = None
        try:
            import anthropic  # noqa: F401
        except ImportError:
            self.available = False
            return
        if not os.environ.get("ANTHROPIC_API_KEY"):
            self.available = False
            return
        try:
            from anthropic import Anthropic
            self._client = Anthropic()
            self.available = True
        except (ImportError, ValueError, RuntimeError) as error:
            autocontrol_logger.warning(
                "Anthropic client init failed: %r", error,
            )
            self.available = False

    def locate(self, image_bytes: bytes, description: str,
               model: Optional[str] = None,
               image_mime: str = "image/png",
               ) -> Optional[Tuple[int, int]]:
        if not self.available or self._client is None:
            return None
        chosen_model = (model
                        or os.environ.get("AUTOCONTROL_VLM_MODEL")
                        or _DEFAULT_MODEL)
        b64 = base64.standard_b64encode(image_bytes).decode("ascii")
        prompt = LOCATE_PROMPT.format(description=description)
        try:
            response = self._client.messages.create(
                model=chosen_model,
                max_tokens=_MAX_TOKENS,
                timeout=_REQUEST_TIMEOUT_S,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "image", "source": {
                            "type": "base64",
                            "media_type": image_mime,
                            "data": b64,
                        }},
                        {"type": "text", "text": prompt},
                    ],
                }],
            )
        # The SDK's errors (rate limit, timeout, 5xx) derive from
        # anthropic.AnthropicError, a bare Exception, so they escaped here while
        # the LLM backend already caught them.
        except (*_sdk_errors(), OSError, ValueError, RuntimeError) as error:
            autocontrol_logger.warning(
                "Anthropic VLM request failed: %r", error,
            )
            return None
        text = _first_text_block(response)
        return parse_coords(text)


def _first_text_block(response) -> str:
    for block in getattr(response, "content", []) or []:
        if getattr(block, "type", None) == "text":
            return getattr(block, "text", "") or ""
    return ""


def _sdk_errors() -> tuple:
    """``(anthropic.AnthropicError,)``, the base of every error the SDK raises.

    Evaluated while an exception is being matched, so it must not raise:
    with an injected client and no SDK installed there is nothing of the
    SDK's to catch.
    """
    try:
        import anthropic
    except ImportError:
        return ()
    return (anthropic.AnthropicError,)
