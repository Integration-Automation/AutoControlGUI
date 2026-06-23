"""1-D barcode decoding — EAN / UPC, with an injectable decoder seam.

The ``qr`` module decodes QR codes only (``cv2.QRCodeDetector``); there is no 1-D /
linear barcode (EAN-8/13, UPC-A/E, Code-128) decode. This mirrors ``qr``'s injectable-
decoder pattern so it is testable without a real barcode and future-proof against
backend availability: the default decoder uses ``cv2.barcode.BarcodeDetector`` (base
OpenCV since 4.8) and degrades to an empty result when that module is absent.

Runs on an injectable image (ndarray / path / PIL, default: grab the screen / region),
so it is headless-testable on synthetic arrays with an injected decoder. OpenCV +
NumPy come in via ``je_open_cv``. Imports no ``PySide6``.
"""
from typing import Any, Callable, Dict, List, Optional, Sequence

from je_auto_control.utils.visual_match.visual_match import _haystack_gray

ImageSource = Any
Decoder = Callable[[Any], List[Dict[str, Any]]]


def _default_decoder(image) -> List[Dict[str, Any]]:
    """Decode 1-D barcodes with ``cv2.barcode`` (empty if the module is absent)."""
    import cv2
    if not hasattr(cv2, "barcode"):
        return []
    retval, infos, types, points = cv2.barcode.BarcodeDetector(
    ).detectAndDecodeWithType(image)
    if not retval:
        return []
    results: List[Dict[str, Any]] = []
    for text, kind, corners in zip(infos, types, points):
        if not text:
            continue
        results.append({"text": text, "type": str(kind),
                        "points": [[int(x), int(y)] for x, y in corners]})
    return results


def read_barcodes(source: Optional[ImageSource] = None, *,
                  region: Optional[Sequence[int]] = None,
                  decoder: Optional[Decoder] = None) -> List[Dict[str, Any]]:
    """Return the 1-D barcodes found in ``source`` (or the screen / ``region``).

    Each result is ``{text, type, points}``. ``decoder`` is injectable (it receives the
    loaded image and returns the result list); the default uses ``cv2.barcode`` and
    returns ``[]`` when that backend is unavailable.
    """
    image = _haystack_gray(source, region)
    return (decoder or _default_decoder)(image)
