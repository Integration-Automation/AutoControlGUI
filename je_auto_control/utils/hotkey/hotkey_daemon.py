"""Global hotkey daemon with pluggable platform backends.

Public API (``bind``, ``unbind``, ``start``, ``stop``, ``list_bindings``) is
unchanged. Backends register their OS listener in ``backends/`` and the
daemon picks one via ``get_backend()``. Windows uses ``RegisterHotKey``,
Linux uses X11 ``XGrabKey``, macOS uses ``CGEventTap``.

Usage::

    from je_auto_control import default_hotkey_daemon
    default_hotkey_daemon.bind("ctrl+alt+1", "scripts/greet.json")
    default_hotkey_daemon.start()
"""
import sys
import threading
import uuid
from dataclasses import dataclass
from typing import Callable, Dict, FrozenSet, List, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException
from je_auto_control.utils.json.json_file import read_executable_action_json
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.utils.run_history.artifact_manager import (
    capture_error_snapshot,
)
from je_auto_control.utils.run_history.history_store import (
    SOURCE_HOTKEY, STATUS_ERROR, STATUS_OK, default_history_store,
)

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

_MODIFIER_NAMES = frozenset(_MODIFIER_MAP.keys())


@dataclass
class HotkeyBinding:
    """One registered hotkey → script binding."""
    binding_id: str
    combo: str
    script_path: str
    enabled: bool = True
    fired: int = 0


def split_combo(combo: str) -> Tuple[FrozenSet[str], str]:
    """Return ``(canonical modifier names, primary key name)``.

    Modifier names are canonical (``ctrl``/``alt``/``shift``/``win``) —
    aliases like ``control``/``super``/``meta`` are normalised.
    """
    if not combo or not combo.strip():
        raise ValueError("hotkey combo is empty")
    parts = [p.strip().lower() for p in combo.split("+") if p.strip()]
    if not parts:
        raise ValueError(f"invalid hotkey combo: {combo!r}")
    mods: set = set()
    key_part: Optional[str] = None
    for part in parts:
        if part in _MODIFIER_NAMES:
            mods.add(_canonical_mod(part))
            continue
        if key_part is not None:
            raise ValueError(f"hotkey {combo!r} has multiple non-modifier keys")
        key_part = part
    if key_part is None:
        raise ValueError(f"hotkey {combo!r} is missing a primary key")
    return frozenset(mods), key_part


def _canonical_mod(name: str) -> str:
    return {"control": "ctrl", "super": "win", "meta": "win"}.get(name, name)


def parse_combo(combo: str) -> Tuple[int, int]:
    """Windows-flavoured parser: ``(modifiers_bitmask, virtual_key)``."""
    mods, key = split_combo(combo)
    modifiers = MOD_NOREPEAT
    for mod in mods:
        modifiers |= _MODIFIER_MAP[mod]
    return modifiers, _key_to_vk(key)


# The US-layout punctuation keys. A virtual-key code equals the character's
# code point only for A-Z and 0-9: ord('.') is VK_DELETE, ord('[') VK_LWIN.
_OEM_KEYS = {
    ";": 0xBA, "=": 0xBB, ",": 0xBC, "-": 0xBD, ".": 0xBE, "/": 0xBF,
    "`": 0xC0, "[": 0xDB, "\\": 0xDC, "]": 0xDD, "'": 0xDE,
}


def _key_to_vk(key: str) -> int:
    if len(key) == 1 and key.isascii() and key.isalnum():
        return ord(key.upper())
    if key in _OEM_KEYS:
        return _OEM_KEYS[key]
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


@dataclass
class BackendContext:
    """Data the daemon hands to a backend thread."""
    stop_event: threading.Event
    get_bindings: Callable[[], List[HotkeyBinding]]
    fire: Callable[[str], None]


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

    def bind(self, combo: str, script_path: str,
             binding_id: Optional[str] = None) -> HotkeyBinding:
        """Register a hotkey → script binding. Safe to call before/after start."""
        split_combo(combo)
        if sys.platform == "win32":
            parse_combo(combo)  # a key RegisterHotKey cannot take fails here, not later
        bid = binding_id or uuid.uuid4().hex[:8]
        binding = HotkeyBinding(
            binding_id=bid, combo=combo, script_path=script_path,
        )
        with self._lock:
            self._bindings[bid] = binding
        return binding

    def unbind(self, binding_id: str) -> bool:
        with self._lock:
            return self._bindings.pop(binding_id, None) is not None

    def list_bindings(self) -> List[HotkeyBinding]:
        with self._lock:
            return list(self._bindings.values())

    _snapshot = list_bindings

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        from je_auto_control.utils.hotkey.backends import get_backend
        backend = get_backend()
        # A fresh event per run, never clear() on the old one: a backend loop
        # that outlived stop()'s join would see it cleared, keep its hotkeys
        # registered, and fire every binding twice beside the new one.
        self._stop = threading.Event()
        context = BackendContext(
            stop_event=self._stop,
            get_bindings=self._snapshot,
            fire=self._fire_binding,
        )
        self._thread = threading.Thread(
            target=backend.run_forever, args=(context,),
            daemon=True, name=f"AutoControlHotkey-{backend.name}",
        )
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=timeout)
            self._thread = None

    def _fire_binding(self, binding_id: str) -> None:
        with self._lock:
            match = self._bindings.get(binding_id)
        if match is None or not match.enabled:
            return
        run_id = _start_history(match)
        status = STATUS_OK
        error_text: Optional[str] = None
        try:
            actions = read_executable_action_json(match.script_path)
            self._execute(actions)
        except Exception as error:  # noqa: BLE001  # reason: this runs on the backend's listener thread; any escape ends every hotkey
            # AutoControlException covers the common cases — a missing/renamed
            # script (AutoControlJsonActionException) or an action that raises
            # (image/window not found). Without it the exception escaped the
            # backend run-loop and silently killed the whole hotkey daemon.
            status = STATUS_ERROR
            error_text = repr(error)
            autocontrol_logger.error("hotkey %s failed: %r",
                                     match.combo, error)
        finally:
            _finish_history(run_id, status, error_text)
        with self._lock:
            match.fired += 1


def _start_history(match: HotkeyBinding) -> Optional[int]:
    """Record the run's start; a history failure must not stop the hotkey."""
    try:
        return default_history_store.start_run(
            SOURCE_HOTKEY, match.binding_id, match.script_path)
    except AutoControlException as error:
        autocontrol_logger.error("hotkey %s: run history unavailable: %r", match.combo, error)
        return None


def _finish_history(run_id: Optional[int], status: str,
                    error_text: Optional[str]) -> None:
    if run_id is None:
        return
    try:
        artifact = (capture_error_snapshot(run_id)
                    if status == STATUS_ERROR else None)
        default_history_store.finish_run(
            run_id, status, error_text, artifact_path=artifact)
    except AutoControlException as error:
        autocontrol_logger.error("hotkey run %s: history not updated: %r", run_id, error)


default_hotkey_daemon = HotkeyDaemon()
