"""Top-level redaction orchestrator.

The engine runs the detector chain against a PIL ``Image`` (or raw
PNG bytes), merges the bounding boxes, and applies one Gaussian blur
pass per merged region. It returns the modified image so callers can
chain it into screenshot pipelines without saving to disk.
"""
from __future__ import annotations

import io
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Tuple

from je_auto_control.utils.redaction.policies import (
    POLICY_OFF, RedactionPolicy,
)
from je_auto_control.utils.redaction.rules import (
    BoundingBox, build_detector_chain, merge_boxes,
)


@dataclass(frozen=True)
class RedactionResult:
    """What was changed in a redact() call (for audit + tests)."""

    boxes: Tuple[BoundingBox, ...]
    detectors_used: Tuple[str, ...]

    def to_dict(self) -> Dict[str, Any]:
        return {
            "boxes": [list(b) for b in self.boxes],
            "detectors_used": list(self.detectors_used),
        }


class RedactionEngine:
    """Apply a :class:`RedactionPolicy` to PIL images / PNG bytes."""

    def __init__(self, policy: Optional[RedactionPolicy] = None) -> None:
        self._policy = policy or POLICY_OFF

    @property
    def policy(self) -> RedactionPolicy:
        return self._policy

    def redact_image(self, image: Any,
                     context: Optional[Dict[str, Any]] = None,
                     ) -> Tuple[Any, RedactionResult]:
        """Return ``(redacted_image, result)`` for ``image``.

        ``context`` is forwarded to the detector chain — it carries
        OCR tokens (``context["ocr"]``) and accessibility nodes
        (``context["accessibility"]``). Hosts that omit the context
        still get the static-region pass.
        """
        ctx = context or {}
        chain = build_detector_chain(self._policy.detectors,
                                      self._policy.regions)
        raw_boxes: List[BoundingBox] = []
        for detector in chain:
            raw_boxes.extend(detector(image, ctx))
        if not raw_boxes:
            return image, RedactionResult(
                boxes=(), detectors_used=tuple(self._policy.detectors),
            )
        merged = merge_boxes(raw_boxes)
        out_image = _apply_blur(image, merged,
                                self._policy.blur_radius,
                                self._policy.overlay_color)
        return out_image, RedactionResult(
            boxes=tuple(merged),
            detectors_used=tuple(self._policy.detectors),
        )

    def redact_bytes(self, png_bytes: bytes,
                     context: Optional[Dict[str, Any]] = None,
                     ) -> Tuple[bytes, RedactionResult]:
        """Round-trip through PNG bytes — handy for VLM upload paths."""
        from PIL import Image
        with Image.open(io.BytesIO(png_bytes)) as raw:
            raw.load()
            image = raw.copy()
        redacted, result = self.redact_image(image, context)
        buffer = io.BytesIO()
        redacted.save(buffer, format="PNG")
        return buffer.getvalue(), result


def _apply_blur(image: Any, boxes: List[BoundingBox], radius: int,
                overlay_color: Optional[Tuple[int, int, int]]) -> Any:
    """Blur (or solid-overlay) each box; return a new image."""
    from PIL import Image, ImageFilter
    base = image.copy()
    for x1, y1, x2, y2 in boxes:
        region = (max(0, x1), max(0, y1),
                  max(0, x2), max(0, y2))
        if region[2] <= region[0] or region[3] <= region[1]:
            continue
        crop = base.crop(region)
        if overlay_color is not None:
            filled = Image.new(
                crop.mode, crop.size, tuple(int(c) for c in overlay_color),
            )
            base.paste(filled, region)
        else:
            blurred = crop.filter(ImageFilter.GaussianBlur(radius=int(radius)))
            base.paste(blurred, region)
    return base


__all__ = ["RedactionEngine", "RedactionResult"]
