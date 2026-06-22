"""Emit CI workflow annotations from run results (GitHub Actions format).

A JUnit file needs a third-party reporter action to surface failures in a
PR. Emitting GitHub Actions *workflow commands* (``::error file=...,line=...,
title=...::message``) prints failures as inline annotations with zero extra
config. This converts a list of result dicts into those lines.

Pure standard library; imports no ``PySide6``.
"""
import sys
from typing import Any, Dict, List, Optional, TextIO

_LEVELS = {"error", "warning", "notice"}


def _escape(value: str) -> str:
    """Escape a workflow-command property value per GitHub's rules."""
    return (str(value).replace("%", "%25").replace("\r", "%0D")
            .replace("\n", "%0A").replace(":", "%3A").replace(",", "%2C"))


def _escape_message(value: str) -> str:
    return str(value).replace("%", "%25").replace("\r", "%0D").replace(
        "\n", "%0A")


def format_annotation(annotation: Dict[str, Any]) -> str:
    """Format one annotation as a GitHub Actions workflow command.

    ``{level, message, file?, line?, col?, title?}``; ``level`` is
    ``error`` / ``warning`` / ``notice`` (defaults to ``error``).
    """
    level = str(annotation.get("level", "error")).lower()
    if level not in _LEVELS:
        level = "error"
    props = []
    for key, prop in (("file", "file"), ("line", "line"), ("col", "col"),
                      ("title", "title")):
        value = annotation.get(key)
        if value not in (None, ""):
            props.append(f"{prop}={_escape(value)}")
    prefix = f"::{level} " + ",".join(props) if props else f"::{level}"
    return f"{prefix}::{_escape_message(annotation.get('message', ''))}"


def emit_annotations(annotations: List[Dict[str, Any]], *,
                     stream: Optional[TextIO] = None) -> List[str]:
    """Format each annotation and write the lines to ``stream`` (stdout).

    Returns the formatted lines (also useful for tests / piping).
    """
    out = stream if stream is not None else sys.stdout
    lines = [format_annotation(item) for item in annotations]
    for line in lines:
        out.write(line + "\n")
    return lines
