"""Image pre-processing for OCR / template matching — grayscale, binarize, deskew, upscale.

``locate_text`` / ``ocr_read_structure`` and ``match_template`` feed the *raw* capture
to the OCR engine / matcher; small UI text, dark themes and low contrast wreck both.
This is the standard pre-step pipeline — grayscale → upscale → binarize → deskew →
denoise → CLAHE contrast — that multiplies their accuracy, with no preprocessing seam
anywhere in the framework today.

Every function runs on an injectable ``haystack`` image (ndarray / path / PIL, default:
grab the screen / ``region``) and returns a NumPy ndarray you can pass straight to an
OCR / match call or save. Colour arrays are in OpenCV's BGR order: files are read that
way, and PIL images and screen grabs (RGB) are converted, so grayscale weights red and
blue correctly; an ndarray you pass in is taken to be BGR already. OpenCV + NumPy
come in via the project's ``je_open_cv`` dependency and are imported lazily.
Imports no ``PySide6``.
"""
import math
from typing import Any, Callable, Dict, Optional, Sequence

from je_auto_control.utils.visual_match.visual_match import _contain_cv2_error

ImageSource = Any
_INTERP = ("nearest", "linear", "cubic", "lanczos")


def _pil_to_bgr(image: Any):
    """A PIL image as an OpenCV array: ``L`` stays single-channel, colour becomes BGR(A).

    ``np.asarray`` on a palette image gives palette *indices*, and RGB order
    made every grayscale step swap the red and blue weights.
    """
    import cv2
    import numpy as np
    if image.mode == "L":
        return np.asarray(image)
    has_alpha = "A" in image.mode or "transparency" in image.info
    if has_alpha:
        return cv2.cvtColor(np.asarray(image.convert("RGBA")), cv2.COLOR_RGBA2BGRA)
    return cv2.cvtColor(np.asarray(image.convert("RGB")), cv2.COLOR_RGB2BGR)


def _to_array(source: ImageSource):
    """Load a path / ndarray / PIL image as a uint8 ndarray in OpenCV's BGR order."""
    import cv2
    import numpy as np
    if hasattr(source, "shape"):
        return np.asarray(source)
    if isinstance(source, (str, bytes)) or hasattr(source, "__fspath__"):
        from je_auto_control.utils.cv2_utils.image_file import read_image
        return read_image(source, cv2.IMREAD_UNCHANGED)
    return _pil_to_bgr(source)


def _resolve(haystack: Optional[ImageSource], region: Optional[Sequence[int]]):
    if haystack is not None:
        return _as_uint8(_to_array(haystack))
    from je_auto_control.utils.cv2_utils.screenshot import pil_screenshot
    return _pil_to_bgr(pil_screenshot(screen_region=list(region) if region else None))


def _as_uint8(array):
    """``array`` as uint8, which every step assumes.

    A 16-bit PNG stayed 16-bit: Otsu then wrote 0 and 255 into a uint16 image,
    which is black, and adaptive thresholding raised. Floats are taken as 0..1
    when they fit there, else as 0..255.
    """
    import numpy as np
    if array.dtype == np.uint8:
        return array
    if array.dtype == np.uint16:
        return (array >> 8).astype(np.uint8)
    values = np.nan_to_num(np.asarray(array, dtype="float64"))
    if np.issubdtype(array.dtype, np.floating) and values.size and values.max() <= 1.0:
        values = values * 255.0
    return np.clip(np.rint(values), 0, 255).astype(np.uint8)


def _gray(array):
    import cv2
    if array.ndim == 3 and array.shape[2] == 1:
        array = array[:, :, 0]
    if array.ndim == 2:
        return array
    code = cv2.COLOR_BGRA2GRAY if array.shape[2] == 4 else cv2.COLOR_BGR2GRAY
    return cv2.cvtColor(array, code)


@_contain_cv2_error
def to_grayscale(haystack: Optional[ImageSource] = None, *,
                 region: Optional[Sequence[int]] = None):
    """Return the image as a single-channel grayscale ndarray."""
    return _gray(_resolve(haystack, region))


@_contain_cv2_error
def upscale(haystack: Optional[ImageSource] = None, *,
            region: Optional[Sequence[int]] = None, scale: float = 2.0,
            interp: str = "cubic"):
    """Return the image resized by ``scale`` — enlarge small UI text before OCR."""
    import cv2
    if interp not in _INTERP:
        raise ValueError(f"unknown interp: {interp!r}")
    table = {"nearest": cv2.INTER_NEAREST, "linear": cv2.INTER_LINEAR,
             "cubic": cv2.INTER_CUBIC, "lanczos": cv2.INTER_LANCZOS4}
    factor = float(scale)
    if not math.isfinite(factor) or factor <= 0:
        # 0 or a negative scale silently produced a 1x1 image.
        raise ValueError(f"scale must be a positive number, got {scale!r}")
    array = _resolve(haystack, region)
    height, width = array.shape[:2]
    size = (max(1, round(width * factor)), max(1, round(height * factor)))
    return cv2.resize(array, size, interpolation=table[interp])


@_contain_cv2_error
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
    if block < 3:
        raise ValueError(f"block_size must be at least 3, got {block_size!r}")
    return cv2.adaptiveThreshold(gray, 255, table[method], cv2.THRESH_BINARY,
                                 block, int(c))


@_contain_cv2_error
def denoise(haystack: Optional[ImageSource] = None, *,
            region: Optional[Sequence[int]] = None, strength: int = 7):
    """Return a denoised grayscale image (non-local means)."""
    import cv2
    return cv2.fastNlMeansDenoising(_gray(_resolve(haystack, region)), None,
                                    float(strength), 7, 21)


@_contain_cv2_error
def enhance_contrast(haystack: Optional[ImageSource] = None, *,
                     region: Optional[Sequence[int]] = None, clip: float = 2.0,
                     grid: int = 8):
    """Return a CLAHE contrast-enhanced grayscale image (rescues dark/low-contrast UI)."""
    import cv2
    if int(grid) < 1:
        raise ValueError(f"grid must be at least 1, got {grid!r}")
    clahe = cv2.createCLAHE(clipLimit=float(clip),
                            tileGridSize=(int(grid), int(grid)))
    return clahe.apply(_gray(_resolve(haystack, region)))


@_contain_cv2_error
def detect_skew_angle(haystack: Optional[ImageSource] = None, *,
                      region: Optional[Sequence[int]] = None,
                      max_angle: float = 15.0) -> float:
    """Return the text skew angle in degrees within ``[-max_angle, max_angle]`` (else 0)."""
    import cv2
    gray = _gray(_resolve(haystack, region))
    _, mask = cv2.threshold(gray, 0, 255,
                            cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    if cv2.countNonZero(mask) * 2 > mask.size:
        # Light text on a dark theme: the inverted mask is the background,
        # and the whole frame's rectangle has no skew.
        mask = cv2.bitwise_not(mask)
    coords = cv2.findNonZero(mask)
    if coords is None:
        return 0.0
    angle = cv2.minAreaRect(coords)[-1] % 90         # version-robust normalisation
    if angle > 45:
        angle -= 90
    return round(float(angle), 3) if abs(angle) <= float(max_angle) else 0.0


@_contain_cv2_error
def deskew(haystack: Optional[ImageSource] = None, *,
           region: Optional[Sequence[int]] = None, max_angle: float = 15.0):
    """Return the image rotated to remove text skew (no-op when none is detected)."""
    import cv2
    array = _resolve(haystack, region)
    angle = detect_skew_angle(array, max_angle=max_angle)
    if abs(angle) < 1e-9:
        return array
    height, width = array.shape[:2]
    matrix = cv2.getRotationMatrix2D((width / 2.0, height / 2.0), angle, 1.0)
    return cv2.warpAffine(array, matrix, (width, height),
                          flags=cv2.INTER_CUBIC, borderMode=cv2.BORDER_REPLICATE)


def _step_grayscale(array, **_kwargs):
    return to_grayscale(array)


def _step_upscale(array, *, scale: float, **_kwargs):
    return upscale(array, scale=scale)


def _step_binarize(array, **_kwargs):
    return binarize(array)


def _step_adaptive(method: str) -> Callable[..., Any]:
    def _step(array, *, block_size: int, c: int, **_kwargs):
        return binarize(array, method=method, block_size=block_size, c=c)
    return _step


_STEPS: Dict[str, Callable[..., Any]] = {
    "grayscale": _step_grayscale,
    "upscale": _step_upscale,
    "binarize": _step_binarize,
    # block_size / c reach these two; plain "binarize" is Otsu and has none.
    "adaptive_mean": _step_adaptive("adaptive_mean"),
    "adaptive_gaussian": _step_adaptive("adaptive_gaussian"),
    "denoise": lambda array, **_kwargs: denoise(array),
    "deskew": lambda array, **_kwargs: deskew(array),
    "contrast": lambda array, **_kwargs: enhance_contrast(array),
}


@_contain_cv2_error
def preprocess_image(haystack: Optional[ImageSource] = None, *,
                     region: Optional[Sequence[int]] = None,
                     steps: Sequence[str] = ("grayscale", "upscale", "binarize"),
                     scale: float = 2.0, block_size: int = 31, c: int = 11):
    """Apply a pipeline of named preprocessing ``steps`` in order, returning the result.

    Steps: ``grayscale``, ``upscale`` (by ``scale``), ``binarize`` (Otsu),
    ``adaptive_mean`` / ``adaptive_gaussian`` (adaptive binarisation tuned by
    ``block_size`` / ``c``), ``denoise``, ``deskew``, ``contrast`` (CLAHE).
    Unknown step names raise ``ValueError``.
    """
    array = _resolve(haystack, region)
    if isinstance(steps, str):
        # "deskew" was walked letter by letter: unknown step 'd'.
        steps = [step.strip() for step in steps.split(",") if step.strip()]
    for step in steps:
        if step not in _STEPS:
            raise ValueError(f"unknown step: {step!r}")
        array = _STEPS[step](array, scale=scale, block_size=block_size, c=c)
    return array
