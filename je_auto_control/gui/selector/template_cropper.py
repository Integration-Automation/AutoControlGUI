"""Crop a selected screen region and save it as a template image."""
import os
from typing import Optional, Tuple

import cv2
import numpy as np
from PIL import ImageGrab
from PySide6.QtWidgets import QWidget

from je_auto_control.gui.selector.region_selector import open_region_selector
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


def _capture_region(region: Tuple[int, int, int, int]) -> np.ndarray:
    """Grab the given (x, y, w, h) region as a BGR numpy array."""
    x, y, w, h = region
    pil_image = ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    return cv2.cvtColor(np.array(pil_image), cv2.COLOR_RGB2BGR)


def _validate_output_path(raw_path: str) -> str:
    """Reject empty paths and ensure the target directory exists."""
    if not raw_path:
        raise ValueError("Output path is empty")
    resolved = os.path.realpath(raw_path)
    parent_dir = os.path.dirname(resolved)
    if not parent_dir or not os.path.isdir(parent_dir):
        raise ValueError(f"Target directory does not exist: {parent_dir}")
    return resolved


def crop_template_to_file(save_path: str,
                          parent: Optional[QWidget] = None
                          ) -> Optional[Tuple[int, int, int, int]]:
    """
    Prompt the user to drag-select a region and save it as a template PNG.

    :param save_path: absolute or relative path for the output PNG
    :param parent: optional parent widget passed to the overlay
    :return: selected (x, y, w, h) or None if cancelled
    """
    region = open_region_selector(parent)
    if region is None:
        return None
    resolved = _validate_output_path(save_path)
    frame = _capture_region(region)
    if not cv2.imwrite(resolved, frame):
        raise OSError(f"cv2.imwrite failed: {resolved}")
    autocontrol_logger.info("template cropped: region=%s path=%s", region, resolved)
    return region
