"""Connected-component bounding boxes from a binary mask.

Shared by the colour-region locator and the SSIM change detector: both threshold
an image into a binary mask and then need the bounding boxes of the connected
blobs. OpenCV + NumPy come in via ``je_open_cv`` and are imported lazily. Imports
no ``PySide6``.
"""
from typing import Any, Dict, List


def connected_boxes(mask, min_area: int = 1) -> List[Dict[str, Any]]:
    """Return ``{x, y, width, height, area, center}`` per blob, largest first.

    ``mask`` is a uint8 binary image (non-zero = foreground). Components whose
    area is below ``min_area`` are dropped; ``center`` is the component centroid
    (truncated to int). Uses 8-connectivity; the background label (0) is skipped.
    """
    import cv2
    count, _labels, stats, centroids = cv2.connectedComponentsWithStats(
        mask, connectivity=8)
    boxes: List[Dict[str, Any]] = []
    for index in range(1, count):                     # 0 is the background
        x, y, width, height, area = (int(v) for v in stats[index])
        if area >= int(min_area):
            cx, cy = centroids[index]
            boxes.append({"x": x, "y": y, "width": width, "height": height,
                          "area": area, "center": [int(cx), int(cy)]})
    boxes.sort(key=lambda item: item["area"], reverse=True)
    return boxes
