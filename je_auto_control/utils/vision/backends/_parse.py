"""Shared parsing helpers for VLM backend responses."""
import re
from typing import Optional, Tuple

# Anchored so a pair is never cut out of a longer number: "123456, 7" read as
# (23456, 7). Decimals are read whole and rounded, and "x=", "x:", '"x":'
# labels are allowed: "x=512, y=300", '{"x": 512, "y": 300}' and
# "512.4, 300.6" all came back as "not found".
_NUMBER = r"-?\d{1,5}(?:\.\d+)?"
_LABEL = r"""(?:["']?[xy]["']?\s*[:=]\s*)?"""
_COORDS_RE = re.compile(
    rf"(?<![\d.]){_LABEL}({_NUMBER})(?:\s*,\s*|\s+){_LABEL}({_NUMBER})(?!\d)(?!\.\d)")


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
        return int(round(float(match.group(1)))), int(round(float(match.group(2))))
    except ValueError:
        return None


LOCATE_PROMPT = (
    'Find the UI element described as: "{description}".\n'
    'Look at the screenshot and return ONLY the pixel coordinates of the '
    'element center in the form "x,y" (two integers separated by a comma). '
    'If the element is not visible, reply exactly "none".'
)
