"""Image pre-processing for OCR / template matching — grayscale, binarize, deskew, upscale.

``locate_text`` / ``ocr_read_structure`` and ``match_template`` feed the *raw* capture
to the OCR engine / matcher; small UI text, dark themes and low contrast wreck both.
This is the standard pre-step pipeline — grayscale → upscale → binarize → deskew →
denoise → CLAHE contrast — that multiplies their accuracy, with no preprocessing seam
anywhere in the framework today.

Every function runs on an injectable ``haystack`` image (ndarray / path / PIL, default:
grab the screen / ``region``) and returns a NumPy ndarray you can pass straight to an
OCR / match call or save. OpenCV + NumPy come in via the project's ``je_open_cv``
dependency and are imported lazily. Imports no ``PySide6``.
"""
from typing import Any, Optional, Sequence

ImageSource = Any
_INTERP = ("nearest", "linear", "cubic", "lanczos")


def _to_array(source: ImageSource):
    """Load a path / ndarray / PIL image as a uint8 ndarray (as stored)."""
    import cv2
    import numpy as np
    if hasattr(source, "shape"):
        return np.asarray(source)
    if isinstance(source, (str, bytes)) or hasattr(source, "__fspath__"):
        array = cv2.imread(str(source), cv2.IMREAD_UNCHANGED)
        if array is None:
            raise ValueError(f"could not read image: {source!r}")
        return array
    return np.asarray(source)


def _resolve(haystack: Optional[ImageSource], region: Optional[Sequence[int]]):
    import numpy as np
    if haystack is not None:
        return _to_array(haystack)
    from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
    image = pil_screenshot(screen_region=list(region) if region else None)
    return np.asarray(image.convert("RGB"))


def _gray(array):
    import cv2
    if array.ndim == 2:
        return array
    code = cv2.COLOR_BGRA2GRAY if array.shape[2] == 4 else cv2.COLOR_BGR2GRAY
    return cv2.cvtColor(array, code)


def to_grayscale(haystack: Optional[ImageSource] = None, *,
                 region: Optional[Sequence[int]] = None):
    """Return the image as a single-channel grayscale ndarray."""
    return _gray(_resolve(haystack, region))


def upscale(haystack: Optional[ImageSource] = None, *,
            region: Optional[Sequence[int]] = None, scale: float = 2.0,
            interp: str = "cubic"):
    """Return the image resized by ``scale`` — enlarge small UI text before OCR."""
    import cv2
    if interp not in _INTERP:
        raise ValueError(f"unknown interp: {interp!r}")
    table = {"nearest": cv2.INTER_NEAREST, "linear": cv2.INTER_LINEAR,
             "cubic": cv2.INTER_CUBIC, "lanczos": cv2.INTER_LANCZOS4}
    array = _resolve(haystack, region)
    height, width = array.shape[:2]
    size = (max(1, round(width * float(scale))), max(1, round(height * float(scale))))
    return cv2.resize(array, size, interpolation=table[interp])


def binarize(haystack: Optional[ImageSource] = None, *,
             region: Optional[Sequence[int]] = None, method: str = "otsu",
             block_size: int = 31, c: int = 11):
    """Return a black/white image. ``method``: otsu / adaptive_mean / adaptive_gaussian."""
    import cv2
    gray = _gray(_resolve(haystack, region))
    if method == "otsu":
        _, result = cv2.threshold(gray, 0, 255,
                                  cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return result
    table = {"adaptive_mean": cv2.ADAPTIVE_THRESH_MEAN_C,
             "adaptive_gaussian": cv2.ADAPTIVE_THRESH_GAUSSIAN_C}
    if method not in table:
        raise ValueError(f"unknown method: {method!r}")
    block = int(block_size) | 1                      # adaptiveThreshold needs odd
    return cv2.adaptiveThreshold(gray, 255, table[method], cv2.THRESH_BINARY,
                                 block, int(c))


def denoise(haystack: Optional[ImageSource] = None, *,
            region: Optional[Sequence[int]] = None, strength: int = 7):
    """Return a denoised grayscale image (non-local means)."""
    import cv2
    return cv2.fastNlMeansDenoising(_gray(_resolve(haystack, region)), None,
                                    float(strength), 7, 21)


def enhance_contrast(haystack: Optional[ImageSource] = None, *,
                     region: Optional[Sequence[int]] = None, clip: float = 2.0,
                     grid: int = 8):
    """Return a CLAHE contrast-enhanced grayscale image (rescues dark/low-contrast UI)."""
    import cv2
    clahe = cv2.createCLAHE(clipLimit=float(clip),
                            tileGridSize=(int(grid), int(grid)))
    return clahe.apply(_gray(_resolve(haystack, region)))


def detect_skew_angle(haystack: Optional[ImageSource] = None, *,
                      region: Optional[Sequence[int]] = None,
                      max_angle: float = 15.0) -> float:
    """Return the text skew angle in degrees within ``[-max_angle, max_angle]`` (else 0)."""
    import cv2
    gray = _gray(_resolve(haystack, region))
    _, mask = cv2.threshold(gray, 0, 255,
                            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    coords = cv2.findNonZero(mask)
    if coords is None:
        return 0.0
    angle = cv2.minAreaRect(coords)[-1] % 90         # version-robust normalisation
    if angle > 45:
        angle -= 90
    return round(float(angle), 3) if abs(angle) <= float(max_angle) else 0.0


def deskew(haystack: Optional[ImageSource] = None, *,
           region: Optional[Sequence[int]] = None, max_angle: float = 15.0):
    """Return the image rotated to remove text skew (no-op when none is detected)."""
    import cv2
    array = _resolve(haystack, region)
    angle = detect_skew_angle(array, max_angle=max_angle)
    if angle == 0.0:
        return array
    height, width = array.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle, 1.0)
    return cv2.warpAffine(array, matrix, (width, height),
                          flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _step_grayscale(array, **_kwargs):
    return to_grayscale(array)


def _step_upscale(array, *, scale: float, **_kwargs):
    return upscale(array, scale=scale)


def _step_binarize(array, *, block_size: int, c: int, **_kwargs):
    return binarize(array, block_size=block_size, c=c)


_STEPS = {
    "grayscale": _step_grayscale,
    "upscale": _step_upscale,
    "binarize": _step_binarize,
    "denoise": lambda array, **_kwargs: denoise(array),
    "deskew": lambda array, **_kwargs: deskew(array),
    "contrast": lambda array, **_kwargs: enhance_contrast(array),
}


def preprocess_image(haystack: Optional[ImageSource] = None, *,
                     region: Optional[Sequence[int]] = None,
                     steps: Sequence[str] = ("grayscale", "upscale", "binarize"),
                     scale: float = 2.0, block_size: int = 31, c: int = 11):
    """Apply a pipeline of named preprocessing ``steps`` in order, returning the result.

    Steps: ``grayscale``, ``upscale`` (by ``scale``), ``binarize`` (otsu, tuned by
    ``block_size`` / ``c`` only for the adaptive variants), ``denoise``, ``deskew``,
    ``contrast`` (CLAHE). Unknown step names raise ``ValueError``.
    """
    array = _resolve(haystack, region)
    for step in steps:
        if step not in _STEPS:
            raise ValueError(f"unknown step: {step!r}")
        array = _STEPS[step](array, scale=scale, block_size=block_size, c=c)
    return array
