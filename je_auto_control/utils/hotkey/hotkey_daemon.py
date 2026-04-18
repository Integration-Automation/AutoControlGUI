"""Global hotkey daemon.

Windows implementation uses ``RegisterHotKey`` + a dedicated message pump
thread. macOS / Linux raise ``NotImplementedError`` for now — the Strategy
pattern keeps the public API stable so backends can be added later.

Usage::

    from je_auto_control import default_hotkey_daemon
    default_hotkey_daemon.bind("ctrl+alt+1", "scripts/greet.json")
    default_hotkey_daemon.start()
"""
import sys
import threading
import uuid
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from je_auto_control.utils.json.json_file import read_action_json
from je_auto_control.utils.logging.logging_instance import autocontrol_logger


MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_SHIFT = 0x0004
MOD_WIN = 0x0008
MOD_NOREPEAT = 0x4000

_MODIFIER_MAP = {
    "ctrl": MOD_CONTROL, "control": MOD_CONTROL,
    "alt": MOD_ALT,
    "shift": MOD_SHIFT,
    "win": MOD_WIN, "super": MOD_WIN, "meta": MOD_WIN,
}


@dataclass
class HotkeyBinding:
    """One registered hotkey → script binding."""
    binding_id: str
    combo: str
    script_path: str
    enabled: bool = True
    fired: int = 0


def parse_combo(combo: str) -> Tuple[int, int]:
    """Parse ``"ctrl+alt+1"`` into ``(modifiers, virtual_key_code)``."""
    if not combo or not combo.strip():
        raise ValueError("hotkey combo is empty")
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        raise ValueError(f"invalid hotkey combo: {combo!r}")
    modifiers = 0
    key_part: Optional[str] = None
    for part in parts:
        if part in _MODIFIER_MAP:
            modifiers |= _MODIFIER_MAP[part]
        else:
            if key_part is not None:
                raise ValueError(f"hotkey {combo!r} has multiple non-modifier keys")
            key_part = part
    if key_part is None:
        raise ValueError(f"hotkey {combo!r} is missing a primary key")
    return modifiers | MOD_NOREPEAT, _key_to_vk(key_part)


def _key_to_vk(key: str) -> int:
    if len(key) == 1:
        return ord(key.upper())
    table = {
        "f1": 0x70, "f2": 0x71, "f3": 0x72, "f4": 0x73, "f5": 0x74,
        "f6": 0x75, "f7": 0x76, "f8": 0x77, "f9": 0x78, "f10": 0x79,
        "f11": 0x7A, "f12": 0x7B,
        "space": 0x20, "enter": 0x0D, "return": 0x0D,
        "tab": 0x09, "escape": 0x1B, "esc": 0x1B,
        "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28,
        "home": 0x24, "end": 0x23, "insert": 0x2D, "delete": 0x2E,
        "pageup": 0x21, "pagedown": 0x22,
    }
    lowered = key.lower()
    if lowered in table:
        return table[lowered]
    raise ValueError(f"unsupported hotkey key: {key!r}")


class HotkeyDaemon:
    """Register OS-level hotkeys and run their action JSON on trigger."""

    def __init__(self,
                 executor: Optional[Callable[[list], object]] = None) -> None:
        from je_auto_control.utils.executor.action_executor import execute_action
        self._execute = executor or execute_action
        self._bindings: Dict[str, HotkeyBinding] = {}
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._pending_register: List[HotkeyBinding] = []
        self._id_counter = 100
        self._registered_ids: Dict[str, int] = {}

    def bind(self, combo: str, script_path: str,
             binding_id: Optional[str] = None) -> HotkeyBinding:
        """Register a hotkey → script binding. Safe to call before/after start."""
        parse_combo(combo)
        bid = binding_id or uuid.uuid4().hex[:8]
        binding = HotkeyBinding(
            binding_id=bid, combo=combo, script_path=script_path,
        )
        with self._lock:
            self._bindings[bid] = binding
            self._pending_register.append(binding)
        return binding

    def unbind(self, binding_id: str) -> bool:
        with self._lock:
            return self._bindings.pop(binding_id, None) is not None

    def list_bindings(self) -> List[HotkeyBinding]:
        with self._lock:
            return list(self._bindings.values())

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        if not sys.platform.startswith("win"):
            raise NotImplementedError(
                "HotkeyDaemon currently supports Windows only"
            )
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run_win, daemon=True, name="AutoControlHotkey",
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    # --- Windows backend -----------------------------------------------------

    def _run_win(self) -> None:
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

        self._drain_pending(user32)
        while not self._stop.is_set():
            self._drain_pending(user32)
            while user32.PeekMessageW(ctypes.byref(msg), None, 0, 0, pm_remove):
                if msg.message == wm_hotkey:
                    self._handle_win_hotkey(msg.wParam)
            self._stop.wait(0.05)

        # cleanup registrations
        for registered_id in list(self._registered_ids.values()):
            user32.UnregisterHotKey(None, registered_id)
        self._registered_ids.clear()

    def _drain_pending(self, user32) -> None:
        with self._lock:
            pending = list(self._pending_register)
            self._pending_register.clear()
        for binding in pending:
            modifiers, vk = parse_combo(binding.combo)
            self._id_counter += 1
            reg_id = self._id_counter
            if user32.RegisterHotKey(None, reg_id, modifiers, vk):
                self._registered_ids[binding.binding_id] = reg_id
            else:
                autocontrol_logger.error(
                    "RegisterHotKey failed for %s (%s)",
                    binding.combo, binding.binding_id,
                )

    def _handle_win_hotkey(self, registered_id: int) -> None:
        match: Optional[HotkeyBinding] = None
        with self._lock:
            for bid, reg_id in self._registered_ids.items():
                if reg_id == registered_id:
                    match = self._bindings.get(bid)
                    break
        if match is None or not match.enabled:
            return
        try:
            actions = read_action_json(match.script_path)
            self._execute(actions)
        except (OSError, ValueError, RuntimeError) as error:
            autocontrol_logger.error("hotkey %s failed: %r",
                                     match.combo, error)
        match.fired += 1


default_hotkey_daemon = HotkeyDaemon()
