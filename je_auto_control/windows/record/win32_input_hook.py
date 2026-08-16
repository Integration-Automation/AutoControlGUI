"""Low-level Windows keyboard/mouse capture that a replay can actually reproduce.

Recording only "what was pressed" is not enough to play a session back. Three
things decide whether the replay matches what the user did:

* **Releases.** Without key-up / button-up, a drag is indistinguishable from a
  click, and a modifier held across several actions cannot be reconstructed.
* **The wheel.** Scrolling is invisible to a listener that only watches buttons.
* **Timing.** With no timestamps every step replays at once, and real interfaces
  never keep up — the window that was supposed to open has not opened yet.

So the hook records press *and* release, wheel deltas, and a monotonic timestamp
per event. :func:`timeline` turns those into the ``delta_ms`` events that
:func:`je_auto_control.utils.input_macro.replay_timeline` already knows how to
play back.

The hook must be installed on a thread that pumps messages, and the callback is
invoked on that same thread, so install / pump / uninstall all live in one
thread here. Stopping posts ``WM_QUIT`` to it — the thread cannot be left
blocked in ``GetMessage``, or every record cycle leaks one.

**Everything typed while recording is captured, passwords included.** Callers
must treat the result as sensitive.
"""
import ctypes
import sys
import threading
import time
from ctypes import wintypes
from typing import Any, Dict, List, Optional

from je_auto_control.utils.exception.exception_tags import (
    windows_import_error_message,
)
from je_auto_control.utils.exception.exceptions import (
    AutoControlException, AutoControlRecordException,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

if sys.platform not in ["win32", "cygwin", "msys"]:
    raise AutoControlException(windows_import_error_message)

WH_KEYBOARD_LL = 13
WH_MOUSE_LL = 14
WM_QUIT = 0x0012

_KEY_DOWN = (0x0100, 0x0104)        # WM_KEYDOWN, WM_SYSKEYDOWN
_KEY_UP = (0x0101, 0x0105)          # WM_KEYUP, WM_SYSKEYUP
_WM_MOUSEWHEEL = 0x020A
_WHEEL_NOTCH = 120                  # one detent, per Win32

_MOUSE_BUTTONS = {
    0x0201: ("mouse_down", "left"), 0x0202: ("mouse_up", "left"),
    0x0204: ("mouse_down", "right"), 0x0205: ("mouse_up", "right"),
    0x0207: ("mouse_down", "middle"), 0x0208: ("mouse_up", "middle"),
}

# A hook that is left installed keeps growing this list forever. Recording is
# bounded so a forgotten session cannot consume the process.
MAX_EVENTS = 20000


class _KBDLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("extra", ctypes.POINTER(wintypes.ULONG))]


class _MSLLHOOKSTRUCT(ctypes.Structure):
    _fields_ = [("pt", wintypes.POINT), ("mouseData", wintypes.DWORD),
                ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("extra", ctypes.POINTER(wintypes.ULONG))]


class Win32InputHook:
    """Captures keyboard and mouse events, with releases, wheel and timing."""

    def __init__(self, max_events: int = MAX_EVENTS) -> None:
        self.events: List[Dict[str, Any]] = []
        self.started = time.monotonic()
        self.error: Optional[str] = None
        self.max_events = int(max_events)
        self._thread_id = 0
        self._ready = threading.Event()
        self._hooks: List[Any] = []
        # WINFUNCTYPE callbacks must stay referenced: once collected, the OS
        # still calls that address and the process dies.
        self._procs: List[Any] = []

    # -- public ------------------------------------------------------------
    def start(self) -> None:
        """Install the hooks and begin recording. Raises if they cannot be set."""
        threading.Thread(target=self._run, daemon=True).start()
        self._ready.wait(timeout=5.0)
        if self.error:
            raise AutoControlRecordException(self.error)

    def stop(self) -> List[Dict[str, Any]]:
        """Stop recording and return the raw events."""
        if self._thread_id:
            try:
                ctypes.windll.user32.PostThreadMessageW(
                    self._thread_id, WM_QUIT, 0, 0)
            except OSError as error:
                autocontrol_logger.error("recorder stop failed: %r", error)
        return self.events

    # -- hook thread -------------------------------------------------------
    def _run(self) -> None:
        user32 = ctypes.windll.user32
        try:
            self._install(user32)
        except OSError as error:
            autocontrol_logger.error("recorder start failed: %r", error)
            self.error = "could not install the keyboard/mouse hook"
            self._unhook(user32)
            self._ready.set()
            return
        self._ready.set()
        try:
            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            self._unhook(user32)

    def _install(self, user32) -> None:
        self._thread_id = ctypes.windll.kernel32.GetCurrentThreadId()
        proto = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        # Declare the signatures: a hook handle is 64-bit and the default
        # c_int return would truncate it.
        user32.SetWindowsHookExW.argtypes = [
            ctypes.c_int, proto, wintypes.HINSTANCE, wintypes.DWORD]
        user32.SetWindowsHookExW.restype = ctypes.c_void_p
        user32.CallNextHookEx.argtypes = [
            ctypes.c_void_p, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
        user32.CallNextHookEx.restype = ctypes.c_ssize_t
        user32.UnhookWindowsHookEx.argtypes = [ctypes.c_void_p]

        self._procs = [proto(self._keyboard_proc(user32)),
                       proto(self._mouse_proc(user32))]
        for hook_id, proc in zip((WH_KEYBOARD_LL, WH_MOUSE_LL), self._procs):
            handle = user32.SetWindowsHookExW(hook_id, proc, None, 0)
            if not handle:
                raise OSError(f"SetWindowsHookExW failed for {hook_id}")
            self._hooks.append(handle)

    def _unhook(self, user32) -> None:
        for handle in self._hooks:
            try:
                user32.UnhookWindowsHookEx(handle)
            except OSError as error:
                autocontrol_logger.info("unhook failed: %r", error)
        self._hooks = []

    def _put(self, event: Dict[str, Any]) -> None:
        """Record one event, stopping the hook once the cap is reached."""
        if len(self.events) >= self.max_events:
            self.stop()
            return
        event["time"] = time.monotonic()
        self.events.append(event)

    def _keyboard_proc(self, user32):
        def _proc(code, w_param, l_param):
            # Called by the OS on this thread: an exception must not escape,
            # and it must not be slow — all desktop input queues behind it.
            try:
                if code >= 0:
                    data = ctypes.cast(
                        l_param, ctypes.POINTER(_KBDLLHOOKSTRUCT)).contents
                    if w_param in _KEY_DOWN:
                        self._put({"op": "key_down", "vk": int(data.vkCode)})
                    elif w_param in _KEY_UP:
                        self._put({"op": "key_up", "vk": int(data.vkCode)})
            except (OSError, ValueError, AttributeError):
                pass
            return user32.CallNextHookEx(None, code, w_param, l_param)

        return _proc

    def _mouse_proc(self, user32):
        def _proc(code, w_param, l_param):
            try:
                if code >= 0:
                    self._mouse_event(l_param, int(w_param))
            except (OSError, ValueError, AttributeError):
                pass
            return user32.CallNextHookEx(None, code, w_param, l_param)

        return _proc

    def _mouse_event(self, l_param, message: int) -> None:
        data = ctypes.cast(l_param, ctypes.POINTER(_MSLLHOOKSTRUCT)).contents
        button = _MOUSE_BUTTONS.get(message)
        if button is not None:
            self._put({"op": button[0], "button": button[1],
                       "x": int(data.pt.x), "y": int(data.pt.y)})
        elif message == _WM_MOUSEWHEEL:
            # The high word of mouseData is a signed notch count times 120.
            raw = ctypes.c_short((int(data.mouseData) >> 16) & 0xFFFF).value
            self._put({"op": "scroll", "delta": raw // _WHEEL_NOTCH,
                       "x": int(data.pt.x), "y": int(data.pt.y)})


def timeline(events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Convert raw events to ``delta_ms`` form for ``replay_timeline``.

    The first event has no gap before it; every later one carries the real pause
    that preceded it, which is what makes a replay track the original pace.
    """
    out: List[Dict[str, Any]] = []
    previous: Optional[float] = None
    for event in events:
        moment = float(event.get("time", 0.0))
        item = {key: value for key, value in event.items() if key != "time"}
        item["delta_ms"] = 0 if previous is None else max(
            0, int((moment - previous) * 1000))
        out.append(item)
        previous = moment
    return out
