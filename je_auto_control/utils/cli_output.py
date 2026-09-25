"""Standard streams for this package's command-line tools and stdio server: UTF-8, whatever the code page.

Redirected or piped, Python gives the standard streams the locale's encoding
before 3.15 -- cp950 on a Traditional Chinese Windows. ``je_auto_control
codegen flow.json > test_flow.py`` then wrote Big5 bytes into a Python file
that ``py_compile`` rejects, text outside the code page (an emoji, ``é``)
ended a command with ``UnicodeEncodeError`` after part of its output, and
the MCP stdio server -- started by its client with pipes -- sent and read
cp950 where the transport requires UTF-8.
"""
import sys
from typing import Any

from je_auto_control.utils.logging.logging_instance import autocontrol_logger


def utf8_stream(stream: Any, *, reading: bool) -> Any:
    """``stream`` switched to UTF-8; output also keeps ``\n`` line ends on Windows.

    Input decodes leniently (``errors="replace"``); a stream that cannot be
    switched (already read from, or not a text stream) is left as it is.
    """
    reconfigure = getattr(stream, "reconfigure", None)
    if reconfigure is None:
        return stream
    try:
        if reading:
            reconfigure(encoding="utf-8", errors="replace")
        else:
            reconfigure(encoding="utf-8", newline="\n")
    except (ValueError, OSError) as error:
        autocontrol_logger.warning("stream left in %s: %r", getattr(stream, "encoding", "?"), error)
    return stream


def utf8_stdout() -> None:
    """Switch ``sys.stdout`` to UTF-8 (a console already is); leave anything else as it is."""
    reconfigure = getattr(sys.stdout, "reconfigure", None)
    if reconfigure is None or str(getattr(sys.stdout, "encoding", "")).lower() in ("utf-8", "utf8"):
        return
    try:
        reconfigure(encoding="utf-8")
    except (ValueError, OSError) as error:
        autocontrol_logger.warning("stdout left in %s: %r", sys.stdout.encoding, error)
