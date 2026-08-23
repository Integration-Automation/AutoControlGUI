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

**``keyboard`` and ``mouse`` take three protocols each, not one.** Their call
shape is genuinely platform-specific: macOS takes ``is_shift`` on ``press_key``
and orders its mouse calls ``(x, y, button)`` where the others take the button
alone, a Windows mouse "keycode" is a tuple of three event flags where the
others are a plain int, and only the X11 stack names a scroll axis. One
protocol cannot describe all three, which is why the pair sat at ``Any`` while
the other six exports were typed. Three protocols describe them exactly:

===============  ==================================================
``Win32*``       SendInput and the Interception driver
``Darwin*``      Quartz
``X11Unix*``     XTest, uinput, Wayland and the BSDs — one shape
===============  ==================================================

Each backend module is checked against *its own* protocol on every target, so
the macOS mouse is verified on an Ubuntu runner. ``KeyboardBackend`` and
``MouseBackend`` then alias whichever pair matches the target mypy is aimed at,
which is what makes a caller checked against the signature it will really
reach: ``mouse.press_mouse(x, y, button)`` is only type-correct on darwin, and
only there is it the branch mypy walks into.

That alias branch is spelled ``sys.platform == "..."`` because it is the only
form mypy resolves — ``sys.platform in [...]`` is not, measured — and it is the
same reason every caller above the seam spells its macOS test that way.
"""
import sys
from typing import Any, Optional, Protocol, Tuple

__all__ = ["DarwinKeyboardBackend", "DarwinMouseBackend", "KeyboardBackend",
           "KeyboardCheckBackend", "MouseBackend", "MouseKeycode",
           "RecorderBackend", "ScreenBackend", "Win32KeyboardBackend",
           "Win32MouseBackend", "X11UnixKeyboardBackend",
           "X11UnixMouseBackend"]

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


class Win32KeyboardBackend(Protocol):
    """Key injection through SendInput or the Interception driver."""

    def press_key(self, keycode: int) -> None:
        """Hold a virtual key down."""

    def release_key(self, keycode: int) -> None:
        """Let a virtual key up."""


class DarwinKeyboardBackend(Protocol):
    """Key injection through Quartz event taps.

    ``is_shift`` has no default here on purpose: the Quartz backend needs the
    modifier state to build the event, and the wrapper always passes it. The
    other two stacks carry the modifier as an ordinary key press instead.
    """

    def press_key(self, keycode: int, is_shift: bool) -> None:
        """Hold a virtual key down, with the shift flag on the event."""

    def release_key(self, keycode: int, is_shift: bool) -> None:
        """Let a virtual key up, with the shift flag on the event."""


class X11UnixKeyboardBackend(Protocol):
    """Key injection on a Unix desktop: XTest, uinput or Wayland."""

    def press_key(self, keycode: int) -> None:
        """Hold a key down."""

    def release_key(self, keycode: int) -> None:
        """Let a key up."""


class Win32MouseBackend(Protocol):
    """Pointer control through SendInput or the Interception driver.

    Every button argument is a ``(up, down, data)`` tuple of Win32 event flags,
    not a button number — the value ``mouse_keys_table`` holds on this platform.
    """

    def position(self) -> Optional[Tuple[int, int]]:
        """Current cursor position, or ``None`` if it cannot be read."""

    def set_position(self, x: int, y: int) -> None:
        """Move the cursor to a point on the virtual desktop."""

    def press_mouse(self, press_button: Tuple[int, int, int]) -> None:
        """Hold a button down at the current position."""

    def release_mouse(self, release_button: Tuple[int, int, int]) -> None:
        """Let a button up at the current position."""

    def click_mouse(self, mouse_keycode: Tuple[int, int, int],
                    x: Optional[int] = None,
                    y: Optional[int] = None) -> None:
        """Press and release a button, moving there first when given a point."""

    def scroll(self, scroll_value: int) -> None:
        """Turn the wheel; the sign is the direction, the magnitude is notches.

        There is one wheel axis here, so no direction argument — the backend
        also accepts an ``x``/``y`` pair it is never given through the seam.
        """


class DarwinMouseBackend(Protocol):
    """Pointer control through Quartz.

    Every button call takes the point first: this backend builds an event at an
    explicit location rather than moving a cursor and acting where it landed.
    """

    def position(self) -> Tuple[int, int]:
        """Current cursor position."""

    def set_position(self, x: int, y: int) -> None:
        """Move the cursor to a point on the desktop."""

    def press_mouse(self, x: int, y: int, mouse_button: int) -> None:
        """Hold a button down at a point."""

    def release_mouse(self, x: int, y: int, mouse_button: int) -> None:
        """Let a button up at a point."""

    def click_mouse(self, x: int, y: int, mouse_button: int) -> None:
        """Press and release a button at a point."""

    def scroll(self, scroll_value: int) -> None:
        """Turn the wheel; one axis, so the sign carries the direction."""


class X11UnixMouseBackend(Protocol):
    """Pointer control on a Unix desktop: XTest, uinput or Wayland.

    This is the one stack that names its scroll axis. ``scroll_direction`` is
    the backend's own axis code — the value ``special_mouse_keys_table`` maps
    ``"scroll_up"`` and friends to — which is why the seam resolves the name
    before calling and refuses one the table does not hold.
    """

    def position(self) -> Tuple[int, int]:
        """Current cursor position."""

    def set_position(self, x: int, y: int) -> None:
        """Move the cursor to a point on the desktop."""

    def press_mouse(self, mouse_keycode: int) -> None:
        """Hold a button down at the current position."""

    def release_mouse(self, mouse_keycode: int) -> None:
        """Let a button up at the current position."""

    def click_mouse(self, mouse_keycode: int, x: Optional[int] = None,
                    y: Optional[int] = None) -> None:
        """Press and release a button, moving there first when given a point."""

    def scroll(self, scroll_value: int, scroll_direction: int) -> None:
        """Turn the wheel along an axis; a negative count reverses it."""


# 別名綁在 mypy 對準的目標平台上，所以呼叫端被檢查的是它真的會走到的簽章。
# 只有 `sys.platform == "..."` 這種寫法 mypy 剪得掉，`in [...]` 不算（實測）。
#
# The aliases bind to whichever target mypy is aimed at, so a caller is checked
# against the signature it will actually reach. Only the literal comparison is
# a form mypy resolves; `sys.platform in [...]` is not.
if sys.platform == "win32":
    KeyboardBackend = Win32KeyboardBackend
    MouseBackend = Win32MouseBackend
elif sys.platform == "darwin":
    KeyboardBackend = DarwinKeyboardBackend
    MouseBackend = DarwinMouseBackend
else:
    # Linux and the BSDs, X11 and Wayland alike — `is_x11_unix()` in prose.
    KeyboardBackend = X11UnixKeyboardBackend
    MouseBackend = X11UnixMouseBackend
