"""Own the lazily acquired shared X11 operation display."""
import os
from threading import Lock
from typing import Any

from Xlib.display import Display

from je_auto_control.utils.exception.exception_tags import linux_import_error_message
from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.platform_id import is_x11_unix

if not is_x11_unix():
    raise AutoControlException(linux_import_error_message)

_DISPLAY: Any = None
_lock = Lock()


def get_display() -> Any:
    """Acquire once, publishing only a completed connection; failures may retry."""
    global _DISPLAY  # pylint: disable=global-statement  # reason: one module owns this lazy cache
    with _lock:
        if _DISPLAY is None:
            try:
                _DISPLAY = Display(os.environ.get("DISPLAY", ":0"))
            except Exception as error:
                raise AutoControlException(f"Cannot open X11 display: {error}") from error
        return _DISPLAY
