"""OpenAI (GPT-4-vision family) VLM backend."""
import base64
import os
from typing import Optional, Tuple

from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.vision.backends._parse import (
    LOCATE_PROMPT, parse_coords,
)
from je_auto_control.utils.vision.backends.base import VLMBackend

_DEFAULT_MODEL = "gpt-4o-mini"
_REQUEST_TIMEOUT_S = 30.0
_MAX_TOKENS = 64


class OpenAIVLMBackend(VLMBackend):
    """Call OpenAI vision-capable chat models via the ``openai`` SDK."""

    name = "openai"

    def __init__(self) -> None:
        self._client = None
        try:
            import openai  # noqa: F401  # nosemgrep: codacy.python.openai.import-without-guardrails  # reason: availability probe only
        except ImportError:
            self.available = False
            return
        if not os.environ.get("OPENAI_API_KEY"):
            self.available = False
            return
        try:
            from openai import OpenAI  # nosemgrep: codacy.python.openai.import-without-guardrails  # reason: internal client init, input is user-supplied prompt only
            self._client = OpenAI(timeout=_REQUEST_TIMEOUT_S)
            self.available = True
        except (ImportError, ValueError, RuntimeError) as error:
            autocontrol_logger.warning(
                "OpenAI client init failed: %r", error,
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
        data_url = f"data:{image_mime};base64,{b64}"
        try:
            response = self._client.chat.completions.create(
                model=chosen_model,
                max_tokens=_MAX_TOKENS,
                messages=[{
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url",
                         "image_url": {"url": data_url}},
                    ],
                }],
            )
        except (OSError, ValueError, RuntimeError) as error:
            autocontrol_logger.warning(
                "OpenAI VLM request failed: %r", error,
            )
            return None
        try:
            text = response.choices[0].message.content or ""
        except (AttributeError, IndexError):
            text = ""
        return parse_coords(text)
