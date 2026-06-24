"""Find the visually salient regions of a frame (spectral-residual saliency).

When there is no template, no known colour and no text to OCR, an agent still
needs a cue for *where to look* — the region that stands out from its
surroundings (a popup, a badge, a highlighted row). ``saliency`` computes the
spectral-residual saliency map (Hou & Zhang 2007) — ``log`` amplitude minus its
local average, reconstructed through the phase — and turns it into ranked salient
boxes.

The transform is a pure ``numpy`` FFT (``cv2.saliency`` lives in the forbidden
opencv-contrib package, so it is re-implemented here over base opencv only). It
reuses ``visual_match``'s grayscale loader for the source (any ndarray / path /
PIL image, or the live screen) and ``cv2_utils.blobs.connected_boxes`` for the
region extraction. cv2 / numpy are lazily imported. Imports no ``PySide6``.
"""
from typing import Any, Dict, List, Optional, Sequence, Tuple

ImageSource = Any


def _gray(source: Optional[ImageSource], region: Optional[Sequence[int]]):
    from je_auto_control.utils.visual_match.visual_match import _haystack_gray
    return _haystack_gray(source, region)


def _saliency_from_gray(gray, size: int):
    import cv2
    import numpy as np
    small = cv2.resize(gray, (size, size),
                       interpolation=cv2.INTER_AREA).astype(np.float32)
    fft = np.fft.fft2(small)
    log_amplitude = np.log(np.abs(fft) + 1e-8)
    residual = log_amplitude - cv2.blur(log_amplitude, (3, 3))
    recon = np.fft.ifft2(np.exp(residual + 1j * np.angle(fft)))
    smoothed = cv2.GaussianBlur(np.abs(recon) ** 2, (0, 0), sigmaX=3.0)
    peak = float(smoothed.max())
    if peak > 0:
        smoothed = smoothed / peak
    return smoothed.astype(np.float32)


def saliency_map(source: Optional[ImageSource] = None, *,
                 region: Optional[Sequence[int]] = None, size: int = 64):
    """Return the normalised (0–1) spectral-residual saliency map as an ndarray.

    The map is computed at ``size`` x ``size`` (the algorithm's native low
    resolution); higher = more salient.
    """
    return _saliency_from_gray(_gray(source, region), int(size))


def _regions_from_saliency(saliency, orig_shape: Tuple[int, int],
                           threshold: Optional[float], min_area: int,
                           size: int) -> List[Dict[str, Any]]:
    from je_auto_control.utils.cv2_utils.blobs import connected_boxes
    if threshold is not None:
        cut = float(threshold)
    else:  # scale-invariant: regions standing 2 std above the mean saliency
        cut = float(saliency.mean()) + 2.0 * float(saliency.std())
    mask = (saliency >= cut).astype("uint8") * 255
    orig_height, orig_width = int(orig_shape[0]), int(orig_shape[1])
    scale_x, scale_y = orig_width / float(size), orig_height / float(size)
    regions: List[Dict[str, Any]] = []
    for box in connected_boxes(mask, min_area=min_area):
        x, y = int(box["x"] * scale_x), int(box["y"] * scale_y)
        width = max(1, int(box["width"] * scale_x))
        height = max(1, int(box["height"] * scale_y))
        patch = saliency[box["y"]:box["y"] + box["height"],
                         box["x"]:box["x"] + box["width"]]
        score = float(patch.mean()) if patch.size else 0.0
        regions.append({"x": x, "y": y, "width": width, "height": height,
                        "center": [x + width // 2, y + height // 2],
                        "score": score})
    regions.sort(key=lambda region: region["score"], reverse=True)
    return regions


def salient_regions(source: Optional[ImageSource] = None, *,
                    region: Optional[Sequence[int]] = None, size: int = 64,
                    threshold: Optional[float] = None,
                    min_area: int = 4) -> List[Dict[str, Any]]:
    """Return salient regions as ``[{x, y, width, height, center, score}]``.

    Boxes are thresholded from the saliency map (default cut = 3x the mean,
    per Hou & Zhang), extracted with ``connected_boxes`` and scaled back to the
    source's pixel coordinates, ranked most-salient first.
    """
    gray = _gray(source, region)
    saliency = _saliency_from_gray(gray, int(size))
    return _regions_from_saliency(saliency, gray.shape[:2], threshold,
                                  int(min_area), int(size))


def most_salient(source: Optional[ImageSource] = None, *,
                 region: Optional[Sequence[int]] = None, size: int = 64,
                 threshold: Optional[float] = None,
                 min_area: int = 4) -> Optional[Dict[str, Any]]:
    """Return the single most salient region, or ``None`` if none stand out."""
    regions = salient_regions(source, region=region, size=size,
                              threshold=threshold, min_area=min_area)
    return regions[0] if regions else None
