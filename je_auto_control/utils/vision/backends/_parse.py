"""Shared parsing helpers for VLM backend responses."""
import re
from typing import Optional, Tuple

_COORDS_RE = re.compile(r"(-?\d{1,5})\s*[,\s]\s*(-?\d{1,5})")


def parse_coords(text: str) -> Optional[Tuple[int, int]]:
    """Extract the first ``x, y`` integer pair from a VLM reply.

    Returns ``None`` if the reply says ``none`` / ``not found`` or if no
    two-integer pair can be located. Accepts minor formatting noise
    (whitespace, punctuation, surrounding prose) so backends don't need
    to be pedantic about prompt responses.
    """
    if not text:
        return None
    cleaned = text.strip().lower()
    if cleaned in {"none", "not found", "n/a", ""}:
        return None
    match = _COORDS_RE.search(text)
    if match is None:
        return None
    try:
        return int(match.group(1)), int(match.group(2))
    except ValueError:
        return None


LOCATE_PROMPT = (
    'Find the UI element described as: "{description}".\n'
    'Look at the screenshot and return ONLY the pixel coordinates of the '
    'element center in the form "x,y" (two integers separated by a comma). '
    'If the element is not visible, reply exactly "none".'
)
