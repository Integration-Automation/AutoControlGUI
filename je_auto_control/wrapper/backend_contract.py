"""What the platform seam promises about whichever backend it selected.

``platform_wrapper`` imports exactly one backend and re-exports its names, so
every module above it is written against *those names* rather than against a
platform. Until now nothing said what they were: mypy bound each name to
whichever branch it read first — always the Windows one, on every target — so
the layer above was silently checked against Win32 signatures even when the
target was Linux or macOS, and a new backend could omit a function entirely
without a word from the type checker.

These protocols are that missing statement. ``platform_wrapper`` declares its
exports with them and each ``_platform_*`` module annotates what it assigns, so
a backend that does not answer the seam's questions fails where the omission is
— in the backend's own assembly module, naming the missing member — instead of
at some call site three layers up.

**Why ``keyboard`` and ``mouse`` are not here.** Their call shape is genuinely
platform-specific, which is why every caller branches on ``sys.platform`` before
touching them: macOS takes ``is_shift`` on ``press_key`` and orders its mouse
calls ``(x, y, button)`` where Windows and X11 take the button alone, and a
Windows mouse "keycode" is a tuple of three event flags where the others are a
plain int. One protocol cannot describe both, and the pair is left as ``Any``
(which is what mypy already inferred for them) until the seam grows a
per-platform protocol for each. See ``Progress.md``.
"""
from typing import Any, Protocol, Tuple

__all__ = ["KeyboardCheckBackend", "MouseKeycode", "RecorderBackend",
           "ScreenBackend"]

#: 一顆滑鼠鍵在**當前平台**的代碼。X11／Wayland／macOS 是 int，Windows 是
#: 三個 Win32 事件旗標組成的 tuple——這是 `mouse_keys_table` 的值型別，也是
#: `press_mouse` 之類的函式收下與回傳的東西。
#:
#: One mouse button as *this* platform spells it: an int on X11, Wayland and
#: macOS, a tuple of three Win32 event flags on Windows. Named rather than
#: written as a bare ``Any`` so a signature says which kind of unknown it is.
MouseKeycode = Any


class ScreenBackend(Protocol):
    """Screen geometry and pixel colour, in physical screen coordinates."""

    def size(self) -> Tuple[int, int]:
        """``(width, height)`` of the primary screen."""

    def get_pixel(self, x: int, y: int) -> Tuple[int, int, int]:
        """``(R, G, B)`` at one point of the desktop.

        A backend may accept more than this — the Windows one also takes an
        ``hwnd`` — but the seam only promises the two coordinates, so a caller
        that wants the extra argument names that backend directly.
        """


class KeyboardCheckBackend(Protocol):
    """Whether a key is held down right now."""

    # pylint: disable=too-few-public-methods  # reason: one question is the
    # whole contract — this backend answers "is that key down?" and nothing else

    def check_key_is_press(self, keycode: int) -> bool:
        """``True`` while the key is physically down."""


class RecorderBackend(Protocol):
    """Capture of real input events until it is asked to stop.

    ``stop_record`` returns ``Any`` because what it hands back differs by
    backend — a ``Queue`` from the shared ``InputRecorder``, a plain list from
    the Wayland one — and ``auto_control_record`` already normalises both.
    """

    def record(self) -> None:
        """Start capturing keyboard and mouse events."""

    def stop_record(self) -> Any:
        """Stop capturing and return what was captured."""
