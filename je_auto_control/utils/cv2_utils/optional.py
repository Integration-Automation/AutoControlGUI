"""Resolve image capabilities lazily, with a typed NumPy/Pillow fallback.

Template matching and BGR conversion prefer OpenCV and work without it through
the bounded NumPy/Pillow backend. Advanced OpenCV/video operations remain
separate capabilities, and strict require_cv2/require_je_open_cv calls do not
silently substitute an incomplete OpenCV implementation.
"""
from importlib import import_module
from typing import Any

from je_auto_control.utils.exception.exceptions import AutoControlException


class ImageBackendError(AutoControlException, ValueError):
    """The selected image backend cannot perform the requested operation."""

    capability = "image_matching"


class ImageDependencyRequired(AutoControlException, RuntimeError):
    """An image capability lacks its required optional backend."""

    state = "needs_dependency"

    def __init__(self, capability: str, message: str) -> None:
        self.capability = capability
        super().__init__(message)

_CV2_HINT = (
    "Advanced OpenCV/video processing requires opencv-python, which publishes no Windows arm64 "
    "wheel; use the NumPy/Pillow template and screenshot backend, or install opencv-python on supported platforms"
)


def require_cv2() -> Any:
    """Return the ``cv2`` module, or explain why the image stack is absent."""
    try:
        # pylint: disable-next=import-outside-toplevel  # reason: optional backend stays off the facade import path
        import cv2
    except ImportError as error:
        raise ImageDependencyRequired("opencv", _CV2_HINT) from error
    return cv2


def require_je_open_cv() -> Any:
    """Return ``je_open_cv.template_detection``, or explain why it is absent."""
    try:
        # pylint: disable-next=import-outside-toplevel  # reason: je_open_cv is unavailable on win_arm64
        from je_open_cv import template_detection
    except ImportError as error:
        raise ImageDependencyRequired("opencv",
            "je_open_cv operations require je_open_cv and opencv-python, which "
            "publish no Windows arm64 wheel: pip install je_open_cv"
        ) from error
    return template_detection


def require_image_backend() -> Any:
    """Prefer OpenCV; use NumPy/Pillow for template matching and image conversion."""
    try:
        # pylint: disable-next=import-outside-toplevel  # reason: optional backend stays off the facade import path
        import cv2
        return cv2
    except ImportError:
        try:
            return import_module("je_auto_control.utils.cv2_utils.numpy_backend")
        except ImportError as error:
            raise ImageDependencyRequired(
                "image_matching", "Image matching/conversion requires OpenCV or NumPy and Pillow; "
                "install the Windows arm64 base dependencies or pip install numpy pillow",
            ) from error
