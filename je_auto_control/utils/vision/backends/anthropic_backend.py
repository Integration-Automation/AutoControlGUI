"""Anthropic (Claude) VLM backend."""
import base64
import os
from typing import Optional, Tuple

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.vision.backends._parse import (
    LOCATE_PROMPT, parse_coords,
)
from je_auto_control.utils.vision.backends.base import VLMBackend, VLMRequestError

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
        # Fitted to what the model sees (1568 px on the long edge, 2576 on
        # the high-resolution tier): sent whole, the reply was in the pixels of
        # the downscaled image and read as screen pixels -- (1436, 799) for
        # an element near (1894, 1054) on a 1920x1080 screen.
        from je_auto_control.utils.agent.backends._computer_toolset import (
            fit_screenshot, image_tier,
        )
        scale = (1.0, 1.0)
        if image_mime == "image/png":
            image_bytes, scale = fit_screenshot(image_bytes, image_tier(chosen_model))
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
            raise VLMRequestError(f"Anthropic VLM request failed: {error!r}") from error
        coords = parse_coords(_first_text_block(response))
        if coords is None:
            return None
        # Back to the pixels of the image given: the model answers in the
        # pixels of the image it saw, which was fitted to its limits.
        return (int(round(coords[0] / scale[0])), int(round(coords[1] / scale[1])))


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
