"""macOS keyboard/mouse capture over a Quartz event tap, on its own thread.

This module used to build an ``NSApplication`` **at import time** and stop
recording by way of ``AppHelper.runEventLoop()``, a loop that never returns to
its caller. Both sat on the path of ``import je_auto_control``, which is why
``wrapper/_platform_osx.py`` set ``recorder = None`` and macOS shipped without
a recorder at all rather than take that regression.

Neither is necessary. A ``CGEventTap`` needs a **run loop**, not an
application: create the tap on a dedicated thread, add its source to *that*
thread's run loop, and pump the loop in short ``CFRunLoopRunInMode`` slices so
the stop flag is honoured between them. Nothing touches AppKit, nothing runs
at import, and the caller is never blocked. The macOS hotkey backend in
``utils/hotkey/backends/macos_backend.py`` already drives a tap this way; this
is the same shape.

Two properties are deliberate and both are load-bearing:

* **The tap is listen-only.** A recorder that consumed events would swallow
  the very input it is recording, so the user's clicks would stop working the
  moment recording started.
* **Modifiers are reconstructed from ``flagsChanged``.** macOS sends no
  key-down/key-up for Shift, Control, Option or Command; it sends one event
  carrying the new flag set. Without decoding that, a recording could not say
  a modifier was held across the actions that followed.

Coordinates come from ``CGEventGetLocation``, whose origin is the top-left of
the display, which is the space ``osx_mouse`` posts into. The previous
listener read ``NSEvent.mouseLocation()``, a **bottom-left** origin, so every
recorded click was mirrored vertically against where a replay would put it.

Requires Accessibility permission (System Settings -> Privacy & Security ->
Accessibility). Without it ``CGEventTapCreate`` returns ``None`` and
:meth:`OSXInputTap.start` raises rather than recording silence.

**Everything typed while recording is captured, passwords included.** Callers
must treat the result as sensitive.
"""
import sys
import threading
import time
from typing import Any, Dict, List, Optional, Tuple

from je_auto_control.utils.exception.exception_tags import (
    macos_record_error_message, osx_import_error_message,
)
from je_auto_control.utils.exception.exceptions import (
    AutoControlException, AutoControlRecordException,
)
from je_auto_control.utils.input_macro.recorder_base import MAX_EVENTS
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

# === 平台檢查 Platform Check ===
# 僅允許在 macOS (Darwin) 環境執行，否則拋出例外
if sys.platform not in ["darwin"]:
    raise AutoControlException(osx_import_error_message)

import Quartz

#: How long one run-loop slice runs before the stop flag is re-checked.
POLL_SECONDS = 0.1

#: How long :meth:`OSXInputTap.start` waits for the tap to come up or fail.
START_TIMEOUT = 5.0

#: Quartz event type -> ``(op, button)``. ``otherMouse`` is the middle button
#: for every mouse this project addresses.
_MOUSE_EVENTS = {
    Quartz.kCGEventLeftMouseDown: ("mouse_down", "left"),
    Quartz.kCGEventLeftMouseUp: ("mouse_up", "left"),
    Quartz.kCGEventRightMouseDown: ("mouse_down", "right"),
    Quartz.kCGEventRightMouseUp: ("mouse_up", "right"),
    Quartz.kCGEventOtherMouseDown: ("mouse_down", "middle"),
    Quartz.kCGEventOtherMouseUp: ("mouse_up", "middle"),
}

#: Modifier keycode -> the flag bit that says it is currently held. macOS
#: reports modifiers only as a flag set, so the keycode alone cannot say
#: whether an event was a press or a release; the bit can.
_MODIFIER_FLAG = {
    54: Quartz.kCGEventFlagMaskCommand,      # right command
    55: Quartz.kCGEventFlagMaskCommand,      # command
    56: Quartz.kCGEventFlagMaskShift,        # shift
    57: Quartz.kCGEventFlagMaskAlphaShift,   # caps lock
    58: Quartz.kCGEventFlagMaskAlternate,    # option
    59: Quartz.kCGEventFlagMaskControl,      # control
    60: Quartz.kCGEventFlagMaskShift,        # right shift
    61: Quartz.kCGEventFlagMaskAlternate,    # right option
    62: Quartz.kCGEventFlagMaskControl,      # right control
    63: Quartz.kCGEventFlagMaskSecondaryFn,  # fn
}

#: ``CGEventMaskBit`` is a C macro rather than a symbol, so the shift is
#: written out — the same form the macOS hotkey backend uses.
_TAP_MASK = sum(
    1 << event for event in
    (Quartz.kCGEventKeyDown, Quartz.kCGEventKeyUp,
     Quartz.kCGEventFlagsChanged, Quartz.kCGEventScrollWheel,
     *_MOUSE_EVENTS)
)

# A tap that takes too long is disabled by the window server rather than
# allowed to slow input down; re-enabling it is the tap owner's job.
_TAP_DISABLED = (Quartz.kCGEventTapDisabledByTimeout,
                 Quartz.kCGEventTapDisabledByUserInput)


class OSXInputTap:
    """Captures keyboard and mouse events, with releases, wheel and timing."""

    def __init__(self, max_events: int = MAX_EVENTS) -> None:
        self.events: List[Dict[str, Any]] = []
        self.started = time.monotonic()
        self.error: Optional[str] = None
        self.max_events = int(max_events)
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._thread: Optional[threading.Thread] = None

    # -- public ------------------------------------------------------------
    def start(self) -> None:
        """Create the tap and record. Raises if the tap cannot be created."""
        self._stop.clear()
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._ready.wait(timeout=START_TIMEOUT)
        if self.error:
            raise AutoControlRecordException(self.error)

    def stop(self) -> List[Dict[str, Any]]:
        """Stop recording and return the raw events."""
        self._stop.set()
        thread, self._thread = self._thread, None
        if thread is not None:
            # A run-loop slice cannot be interrupted part-way, so allow for
            # several: a thread left running keeps a live tap on the session.
            thread.join(timeout=POLL_SECONDS * 10)
            if thread.is_alive():
                autocontrol_logger.error(
                    "recorder thread did not stop within %.1fs",
                    POLL_SECONDS * 10)
        return self.events

    # -- tap thread --------------------------------------------------------
    def _run(self) -> None:
        from CoreFoundation import CFRunLoopRunInMode, kCFRunLoopDefaultMode

        tap = source = run_loop = None
        try:
            tap = Quartz.CGEventTapCreate(
                Quartz.kCGSessionEventTap, Quartz.kCGHeadInsertEventTap,
                # Listen-only: a recorder that consumed events would swallow
                # the input it is recording.
                Quartz.kCGEventTapOptionListenOnly, _TAP_MASK,
                self._callback, None,
            )
            if tap is None:
                autocontrol_logger.error(
                    "CGEventTapCreate returned None - Accessibility not granted")
                self.error = macos_record_error_message
                return
            source = Quartz.CFMachPortCreateRunLoopSource(None, tap, 0)
            run_loop = Quartz.CFRunLoopGetCurrent()
            Quartz.CFRunLoopAddSource(run_loop, source, kCFRunLoopDefaultMode)
            Quartz.CGEventTapEnable(tap, True)
        except Exception as error:  # noqa: BLE001  # reason: see below
            # Anything at all here has to reach start(), which is blocked on
            # _ready: a thread that dies quietly leaves the caller believing
            # it is recording, and the session comes back empty with no
            # explanation of why.
            autocontrol_logger.error("recorder start failed: %r", error)
            self.error = f"could not create the macOS event tap: {error!r}"
            return
        finally:
            self._ready.set()
        try:
            while not self._stop.is_set():
                CFRunLoopRunInMode(kCFRunLoopDefaultMode, POLL_SECONDS, False)
        finally:
            # Both, and in this order: an enabled tap whose source is already
            # gone is what leaks one live tap per record cycle.
            Quartz.CGEventTapEnable(tap, False)
            if source is not None and run_loop is not None:
                Quartz.CFRunLoopRemoveSource(
                    run_loop, source, kCFRunLoopDefaultMode)

    def _callback(self, proxy, event_type, event, _refcon):
        """Called by the window server on the tap thread, for every event."""
        # Anything escaping here tears down the run loop, and the recording
        # then stops without saying so — one unexpected event shape would end
        # the session. The catch is broad on purpose, and it is bounded: the
        # error is logged and the next event is still decoded.
        try:
            if event_type in _TAP_DISABLED:
                # Re-arm, rather than record silence for the rest of the run.
                autocontrol_logger.info(
                    "event tap disabled (%s), re-enabling", event_type)
                Quartz.CGEventTapEnable(proxy, True)
            else:
                self.decode(int(event_type), event)
        except Exception as error:  # noqa: BLE001  # reason: an OS callback; see above
            autocontrol_logger.error("recorder decode failed: %r", error)
        return event

    # -- decoding ----------------------------------------------------------
    def decode(self, event_type: int, event: Any) -> None:
        """Record one Quartz event. Split out so it is testable off the tap."""
        if event_type == Quartz.kCGEventKeyDown:
            self._put({"op": "key_down", "vk": self._keycode(event)})
        elif event_type == Quartz.kCGEventKeyUp:
            self._put({"op": "key_up", "vk": self._keycode(event)})
        elif event_type == Quartz.kCGEventFlagsChanged:
            self._modifier(event)
        elif event_type == Quartz.kCGEventScrollWheel:
            self._scroll(event)
        elif event_type in _MOUSE_EVENTS:
            operation, button = _MOUSE_EVENTS[event_type]
            x, y = self._location(event)
            self._put({"op": operation, "button": button, "x": x, "y": y})

    @staticmethod
    def _keycode(event: Any) -> int:
        return int(Quartz.CGEventGetIntegerValueField(
            event, Quartz.kCGKeyboardEventKeycode))

    @staticmethod
    def _location(event: Any) -> Tuple[int, int]:
        point = Quartz.CGEventGetLocation(event)
        return int(point.x), int(point.y)

    def _modifier(self, event: Any) -> None:
        """Turn a flag set into the press or release of one modifier key."""
        keycode = self._keycode(event)
        mask = _MODIFIER_FLAG.get(keycode)
        if mask is None:
            return
        held = bool(int(Quartz.CGEventGetFlags(event)) & mask)
        self._put({"op": "key_down" if held else "key_up", "vk": keycode})

    def _scroll(self, event: Any) -> None:
        delta = int(Quartz.CGEventGetIntegerValueField(
            event, Quartz.kCGScrollWheelEventDeltaAxis1))
        x, y = self._location(event)
        self._put({"op": "scroll", "delta": delta, "x": x, "y": y})

    def _put(self, event: Dict[str, Any]) -> None:
        """Record one event, stopping the tap once the cap is reached."""
        if len(self.events) >= self.max_events:
            self._stop.set()
            return
        event["time"] = time.monotonic()
        self.events.append(event)
