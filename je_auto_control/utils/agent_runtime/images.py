"""Bounded redacted JPEG validation is shared by point grounding, previews and persistence."""
from __future__ import annotations

import base64
import binascii
import io
from typing import Any, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError


def verify_jpeg(data: bytes) -> tuple[int, int]:
    """Validate an at-most-one-megabyte JPEG without allocating an unbounded decoded image."""
    if len(data) > 1_000_000:
        raise AgentTaskError("task image exceeds one megabyte")
    from PIL import Image
    try:
        with Image.open(io.BytesIO(data)) as image:
            if image.format != "JPEG" or max(image.size) > 1280:
                raise AgentTaskError("task image requires a bounded JPEG")
            dimensions = image.size
            image.verify()
            return dimensions
    except (OSError, ValueError, Image.DecompressionBombError) as error:
        raise AgentTaskError("task image validation failed") from error


def observation_image_bytes(image: Mapping[str, Any]) -> bytes:
    """Require strict masking and real pixel dimensions matching the observation's geometry."""
    if image.get("redacted_by") != "strict" or image.get("format") != "jpeg":
        raise AgentTaskError("observation image requires a strictly redacted JPEG")
    encoded = image.get("data")
    if not isinstance(encoded, str) or len(encoded) > 1_340_000:
        raise AgentTaskError("observation image exceeds its bounded encoding")
    try:
        data = base64.b64decode(encoded, validate=True)
    except (ValueError, binascii.Error) as error:
        raise AgentTaskError("observation image encoding is invalid") from error
    dimensions = verify_jpeg(data)
    expected = image.get("image_size")
    if not isinstance(expected, (list, tuple)) or list(expected) != list(dimensions):
        raise AgentTaskError("observation image geometry does not match its actual pixels")
    return data
