"""Linux X11 hotkey backend using python-Xlib's ``XGrabKey``.

Requires an X11 display — Wayland is not supported. The grab consumes the
key, matching Windows ``RegisterHotKey`` semantics. NumLock / CapsLock are
masked so the hotkey still fires with those toggles active.
"""
from typing import Dict, List, Optional, Tuple

from je_auto_control.utils.hotkey.backends.base import HotkeyBackend
from je_auto_control.utils.hotkey.hotkey_daemon import (
    BackendContext, HotkeyBinding, split_combo,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger

_LINUX_POLL_SECONDS = 0.1

_KEY_NAME_TO_KEYSYM = {
    "space": "space", "enter": "Return", "return": "Return",
    "tab": "Tab", "escape": "Escape", "esc": "Escape",
    "left": "Left", "right": "Right", "up": "Up", "down": "Down",
    "home": "Home", "end": "End", "pageup": "Page_Up",
    "pagedown": "Page_Down", "insert": "Insert", "delete": "Delete",
    "f1": "F1", "f2": "F2", "f3": "F3", "f4": "F4", "f5": "F5",
    "f6": "F6", "f7": "F7", "f8": "F8", "f9": "F9", "f10": "F10",
    "f11": "F11", "f12": "F12",
}


def _combo_to_x11(combo: str) -> Tuple[int, int]:
    """Return ``(x11_modifier_mask, keycode)`` for ``combo`` on this display."""
    from Xlib import X, XK
    from Xlib import display as xdisplay

    mods, primary = split_combo(combo)
    mask = 0
    if "ctrl" in mods:
        mask |= X.ControlMask
    if "shift" in mods:
        mask |= X.ShiftMask
    if "alt" in mods:
        mask |= X.Mod1Mask
    if "win" in mods:
        mask |= X.Mod4Mask

    keysym_name = _KEY_NAME_TO_KEYSYM.get(primary.lower())
    if keysym_name is None:
        if len(primary) == 1:
            keysym_name = primary.lower()
        else:
            raise ValueError(f"unsupported hotkey key: {primary!r}")
    keysym = XK.string_to_keysym(keysym_name)
    if keysym == 0:
        raise ValueError(f"unknown X keysym for key: {primary!r}")
    disp = xdisplay.Display()
    try:
        return mask, disp.keysym_to_keycode(keysym)
    finally:
        disp.close()


class LinuxHotkeyBackend(HotkeyBackend):
    """Grab keys via X11 and dispatch KeyPress events."""

    name = "linux-x11"

    def __init__(self) -> None:
        # binding_id -> (combo, modifier_mask, keycode)
        self._registered: Dict[str, Tuple[str, int, int]] = {}

    def run_forever(self, context: BackendContext) -> None:
        from Xlib import X
        from Xlib import display as xdisplay

        try:
            disp = xdisplay.Display()
        except Exception as error:
            autocontrol_logger.error("open X display failed: %r", error)
            return

        root = disp.screen().root
        root.change_attributes(event_mask=X.KeyPressMask)
        try:
            while not context.stop_event.is_set():
                self._sync(disp, root, context.get_bindings())
                self._drain(disp, context.fire)
                context.stop_event.wait(_LINUX_POLL_SECONDS)
        finally:
            self._ungrab_all(disp, root)
            disp.close()

    def _sync(self, disp, root, bindings: List[HotkeyBinding]) -> None:
        current_ids = {b.binding_id for b in bindings}
        self._ungrab_stale(root, current_ids)
        for binding in bindings:
            self._sync_one(root, binding)
        disp.sync()

    def _ungrab_stale(self, root, current_ids: set) -> None:
        stale_ids = [bid for bid in self._registered if bid not in current_ids]
        for stale in stale_ids:
            _combo, mask, keycode = self._registered.pop(stale)
            self._ungrab_masked(root, keycode, mask)

    def _sync_one(self, root, binding: HotkeyBinding) -> None:
        prior = self._registered.get(binding.binding_id)
        if prior is not None and prior[0] == binding.combo:
            return
        if prior is not None:
            self._registered.pop(binding.binding_id, None)
        try:
            mask, keycode = _combo_to_x11(binding.combo)
        except ValueError as error:
            autocontrol_logger.error(
                "hotkey parse failed for %s: %r", binding.combo, error,
            )
            return
        if self._grab_masked(root, binding, mask, keycode):
            self._registered[binding.binding_id] = (
                binding.combo, mask, keycode,
            )

    @staticmethod
    def _ungrab_masked(root, keycode: int, mask: int) -> None:
        for extra_mask in _lock_mask_variants():
            try:
                root.ungrab_key(keycode, mask | extra_mask)
            except Exception:  # nosec B110  # noqa: BLE001  # reason: X11 ungrab races are non-fatal
                pass

    @staticmethod
    def _grab_masked(root, binding: HotkeyBinding,
                     mask: int, keycode: int) -> bool:
        from Xlib import X

        for extra_mask in _lock_mask_variants():
            try:
                root.grab_key(
                    keycode, mask | extra_mask, True,
                    X.GrabModeAsync, X.GrabModeAsync,
                )
            except Exception as error:  # noqa: BLE001  # reason: X errors
                autocontrol_logger.error(
                    "XGrabKey failed for %s: %r", binding.combo, error,
                )
                return False
        return True

    def _drain(self, disp, fire: "callable") -> None:
        from Xlib import X

        while disp.pending_events():
            event = disp.next_event()
            if event.type != X.KeyPress:
                continue
            match = self._find_binding(event.detail, event.state)
            if match is not None:
                fire(match)

    def _find_binding(self, keycode: int, state: int) -> Optional[str]:
        effective_state = state & ~_lock_all_mask()
        for bid, (_combo, mask, kc) in self._registered.items():
            if kc == keycode and (state & mask) == mask \
                    and effective_state == mask:
                return bid
        return None

    def _ungrab_all(self, disp, root) -> None:
        for _combo, mask, keycode in self._registered.values():
            for extra_mask in _lock_mask_variants():
                try:
                    root.ungrab_key(keycode, mask | extra_mask)
                except Exception:  # nosec B110  # noqa: BLE001  # reason: X11 ungrab races are non-fatal
                    pass
        self._registered.clear()
        disp.sync()


def _lock_mask_variants() -> List[int]:
    """Masks to re-register each hotkey with NumLock / CapsLock combos."""
    try:
        from Xlib import X
    except ImportError:
        return [0]
    num_lock = X.Mod2Mask
    caps_lock = X.LockMask
    return [0, num_lock, caps_lock, num_lock | caps_lock]


def _lock_all_mask() -> int:
    try:
        from Xlib import X
    except ImportError:
        return 0
    return X.Mod2Mask | X.LockMask
