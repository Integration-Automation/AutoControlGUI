"""Decode QR codes from an image or screen region using OpenCV.

OpenCV's ``QRCodeDetector`` ships with ``je_open_cv`` (already a
dependency), so no extra package is needed. The decoder is injectable so
the wrapper is unit-testable without a real QR image. GUI-free.
"""
from __future__ import annotations

import io
from pathlib import Path
from typing import (
    TYPE_CHECKING, Any, Callable, List, Optional, Sequence, Union,
)

if TYPE_CHECKING:  # pragma: no cover - annotations only
    from PIL import Image

ImageSource = Union[str, Path, bytes, "Image.Image"]
QRDecoder = Callable[[Any], List[str]]


def _load_np(source: ImageSource, region: Optional[Sequence[int]]):
    import numpy as np
    from PIL import Image
    if isinstance(source, Image.Image):
        image = source
    elif isinstance(source, bytes):
        image = Image.open(io.BytesIO(source))
    else:
        image = Image.open(str(source))
    image = image.convert("RGB")
    if region is not None:
        image = image.crop(tuple(int(v) for v in region))
    return np.array(image)


def _default_decoder(image_np: Any) -> List[str]:
    import cv2
    detector = cv2.QRCodeDetector()
    ok, decoded, _points, _straight = detector.detectAndDecodeMulti(image_np)
    if not ok or decoded is None:
        return []
    return [text for text in decoded if text]


def read_qr_codes(source: ImageSource,
                  region: Optional[Sequence[int]] = None, *,
                  decoder: Optional[QRDecoder] = None) -> List[str]:
    """Decode every QR code in ``source`` (or a sub-region); return the texts.

    ``source`` is a path, PNG bytes, or a PIL image. ``decoder`` is
    injectable for tests; the default uses OpenCV's ``QRCodeDetector``.
    """
    image_np = _load_np(source, region)
    return (decoder or _default_decoder)(image_np)
