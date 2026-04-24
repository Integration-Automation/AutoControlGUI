"""Windows hotkey backend: ``RegisterHotKey`` + a message-pump thread."""
from typing import Dict, List, Optional, Tuple

from je_auto_control.utils.hotkey.backends.base import HotkeyBackend
from je_auto_control.utils.hotkey.hotkey_daemon import (
    BackendContext, HotkeyBinding, parse_combo,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


class WindowsHotkeyBackend(HotkeyBackend):
    """Win32 backend using user32's ``RegisterHotKey``."""

    name = "windows"

    def __init__(self) -> None:
        self._id_counter = 100
        # binding_id -> (os_registration_id, combo)
        self._registered: Dict[str, Tuple[int, str]] = {}

    def run_forever(self, context: BackendContext) -> None:
        import ctypes
        from ctypes import wintypes

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.RegisterHotKey.argtypes = [
            wintypes.HWND, ctypes.c_int, wintypes.UINT, wintypes.UINT,
        ]
        user32.RegisterHotKey.restype = wintypes.BOOL
        user32.UnregisterHotKey.argtypes = [wintypes.HWND, ctypes.c_int]
        user32.PeekMessageW.argtypes = [
            ctypes.POINTER(wintypes.MSG), wintypes.HWND,
            wintypes.UINT, wintypes.UINT, wintypes.UINT,
        ]
        user32.PeekMessageW.restype = wintypes.BOOL

        msg = wintypes.MSG()
        wm_hotkey = 0x0312
        pm_remove = 0x0001
        try:
            while not context.stop_event.is_set():
                self._sync(user32, context.get_bindings())
                while user32.PeekMessageW(
                    ctypes.byref(msg), None, 0, 0, pm_remove,
                ):
                    if msg.message == wm_hotkey:
                        self._dispatch(msg.wParam, context.fire)
                context.stop_event.wait(0.05)
        finally:
            for reg_id, _ in self._registered.values():
                user32.UnregisterHotKey(None, reg_id)
            self._registered.clear()

    def _sync(self, user32, bindings: List[HotkeyBinding]) -> None:
        """Add new bindings + drop removed ones vs. ``self._registered``."""
        current_ids = {b.binding_id for b in bindings}
        for stale_id in [bid for bid in self._registered if bid not in current_ids]:
            reg_id, _combo = self._registered.pop(stale_id)
            user32.UnregisterHotKey(None, reg_id)
        for binding in bindings:
            existing = self._registered.get(binding.binding_id)
            if existing is not None and existing[1] == binding.combo:
                continue
            if existing is not None:
                user32.UnregisterHotKey(None, existing[0])
                self._registered.pop(binding.binding_id, None)
            self._try_register(user32, binding)

    def _try_register(self, user32, binding: HotkeyBinding) -> None:
        try:
            modifiers, vk = parse_combo(binding.combo)
        except ValueError as error:
            autocontrol_logger.error(
                "hotkey parse failed for %s: %r", binding.combo, error,
            )
            return
        self._id_counter += 1
        reg_id = self._id_counter
        if user32.RegisterHotKey(None, reg_id, modifiers, vk):
            self._registered[binding.binding_id] = (reg_id, binding.combo)
        else:
            autocontrol_logger.error(
                "RegisterHotKey failed for %s (%s)",
                binding.combo, binding.binding_id,
            )

    def _dispatch(self, registered_id: int,
                  fire: "callable") -> None:
        match: Optional[str] = None
        for bid, (reg_id, _combo) in self._registered.items():
            if reg_id == registered_id:
                match = bid
                break
        if match is not None:
            fire(match)
