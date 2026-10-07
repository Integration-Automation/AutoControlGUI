"""Read and write image bytes with the selected backend at non-ASCII paths.

``cv2.imread`` and ``cv2.imwrite`` go through the C locale on Windows: a path
with non-ASCII characters (a Chinese user name, a folder like ``測試``) makes
``imread`` return ``None`` -- indistinguishable from a corrupt file -- and
``imwrite`` write to a mangled name while reporting success. Encoding and
decoding the bytes ourselves sidesteps the file name entirely.
"""
from typing import Any

from je_auto_control.utils.cv2_utils.optional import require_image_backend


def read_image(path: Any, flags: int) -> Any:
    """Decode the image file at ``path`` with ``cv2.imdecode`` ``flags``.

    Raises ``ValueError`` when the file cannot be read or decoded.
    """
    cv2 = require_image_backend()
    import numpy as np
    try:
        with open(str(path), "rb") as handle:
            buffer = np.frombuffer(handle.read(), dtype=np.uint8)
    except OSError as error:
        raise ValueError(f"could not read image: {path!r}") from error
    try:
        image = cv2.imdecode(buffer, flags)
    except cv2.error as error:
        raise ValueError(f"could not decode image: {path!r}") from error
    if image is None:
        raise ValueError(f"could not read image: {path!r}")
    return image


def write_image(path: Any, image: Any) -> None:
    """Encode ``image`` in the format ``path``'s extension names and write it.

    Raises ``ValueError`` for an extension OpenCV cannot encode and
    ``OSError`` when the file cannot be written.
    """
    import os

    cv2 = require_image_backend()
    extension = os.path.splitext(str(path))[1] or ".png"
    ok, encoded = cv2.imencode(extension, image)
    if not ok:
        raise ValueError(f"could not encode image as {extension!r}: {path!r}")
    with open(str(path), "wb") as handle:
        handle.write(encoded.tobytes())


__all__ = ["read_image", "write_image"]
