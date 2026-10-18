"""Bounded template image decoding and target-format candidate encoding without capture."""
import io
from typing import Any

from je_auto_control.utils.self_healing.evaluation_models import png_size
from je_auto_control.utils.self_healing.template_models import TemplateRevisionError

MAX_IMAGE_BYTES = 16 * 1024 * 1024
_FORMATS = {"PNG", "JPEG", "BMP"}


def image_metadata(payload: bytes) -> tuple[str, tuple[int, int]]:
    """Read format and dimensions of bytes already validated by bundle creation/loading."""
    # pylint: disable-next=import-outside-toplevel  # reason: importing the facade must not initialize image codecs
    from PIL import Image
    with Image.open(io.BytesIO(payload)) as image:
        return str(image.format), image.size


def normalized_png(payload: bytes, *, thumbnail: bool = False) -> tuple[bytes, str, tuple[int, int]]:
    """Decode one static PNG/JPEG/BMP, returning normalized pixels and source dimensions."""
    if not isinstance(payload, bytes) or not payload or len(payload) > MAX_IMAGE_BYTES:
        raise TemplateRevisionError("template image must contain at most 16 MiB")
    # pylint: disable-next=import-outside-toplevel  # reason: facade imports do not initialize image codecs
    from PIL import Image
    try:
        with Image.open(io.BytesIO(payload)) as image:
            fmt, size = image.format, image.size
            if fmt not in _FORMATS or image.width * image.height > 16_000_000 or getattr(image, "is_animated", False):
                raise TemplateRevisionError("template must be a PNG/JPEG/BMP of at most 16 million pixels")
            with image.convert("RGB") as decoded:
                if thumbnail:
                    decoded.thumbnail((512, 512))
                result = _encode(decoded, "PNG")
    except (OSError, SyntaxError, Image.DecompressionBombError) as error:
        raise TemplateRevisionError("cannot decode template image") from error
    png_size(result)
    return result, str(fmt), size


def encode_candidate(original: bytes, candidate_png: bytes) -> bytes:
    """Encode candidate pixels in the active template's format, then validate those exact pixels."""
    png_size(candidate_png)
    _, fmt, _ = normalized_png(original)
    if fmt == "PNG":
        return candidate_png
    # pylint: disable-next=import-outside-toplevel  # reason: initialize codecs only for an explicit candidate image
    from PIL import Image
    with Image.open(io.BytesIO(candidate_png)) as image:
        with image.convert("RGB") as decoded:
            result = _encode(decoded, fmt)
    normalized_png(result)
    return result


def _encode(image: Any, fmt: str) -> bytes:
    output = io.BytesIO()
    image.save(output, format=fmt)
    data = output.getvalue()
    if len(data) > MAX_IMAGE_BYTES:
        raise TemplateRevisionError("encoded template image exceeds 16 MiB")
    return data
