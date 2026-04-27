"""In-memory fake backend for CI / headless tool tests.

Drop-in replacement for the wrapper layer's mouse / keyboard / screen
calls that records every invocation rather than touching the real OS.
Activate via :func:`install_fake_backend` (or set
``JE_AUTOCONTROL_FAKE_BACKEND=1`` before starting the MCP server) so
test agents can drive the full tool registry on a CI runner without a
display server.
"""
import os
import threading
from dataclasses import dataclass, field
from typing import Any, Dict, List, Tuple


@dataclass
class FakeState:
    """Records what the model would have done if the OS were real."""

    cursor: Tuple[int, int] = (0, 0)
    screen_size: Tuple[int, int] = (1920, 1080)
    clipboard_text: str = ""
    typed_text: List[str] = field(default_factory=list)
    keys_pressed: List[Any] = field(default_factory=list)
    mouse_actions: List[Tuple[Any, ...]] = field(default_factory=list)


def fake_state() -> FakeState:
    """Return the process-wide fake state."""
    return _STATE


_STATE = FakeState()
_STATE_LOCK = threading.Lock()


def reset_fake_state() -> None:
    """Reset every recorded interaction. Useful between tests."""
    global _STATE
    with _STATE_LOCK:
        _STATE = FakeState()


# === Patched callables ======================================================

def _fake_get_mouse_position() -> Tuple[int, int]:
    return _STATE.cursor


def _fake_set_mouse_position(x: int, y: int) -> Tuple[int, int]:
    with _STATE_LOCK:
        _STATE.cursor = (int(x), int(y))
        _STATE.mouse_actions.append(("set_position", int(x), int(y)))
    return _STATE.cursor


def _fake_click_mouse(mouse_keycode: Any, x: Any = None,
                      y: Any = None) -> Tuple[Any, int, int]:
    cx, cy = _STATE.cursor if x is None or y is None else (int(x), int(y))
    with _STATE_LOCK:
        _STATE.cursor = (cx, cy)
        _STATE.mouse_actions.append(("click", mouse_keycode, cx, cy))
    return mouse_keycode, cx, cy


def _fake_press_mouse(mouse_keycode: Any, x: Any = None,
                      y: Any = None) -> Tuple[Any, int, int]:
    cx, cy = _STATE.cursor if x is None or y is None else (int(x), int(y))
    with _STATE_LOCK:
        _STATE.mouse_actions.append(("press", mouse_keycode, cx, cy))
    return mouse_keycode, cx, cy


def _fake_release_mouse(mouse_keycode: Any, x: Any = None,
                        y: Any = None) -> Tuple[Any, int, int]:
    cx, cy = _STATE.cursor if x is None or y is None else (int(x), int(y))
    with _STATE_LOCK:
        _STATE.mouse_actions.append(("release", mouse_keycode, cx, cy))
    return mouse_keycode, cx, cy


def _fake_mouse_scroll(scroll_value: int, x: Any = None, y: Any = None,
                        scroll_direction: str = "scroll_down"
                        ) -> Tuple[int, str]:
    with _STATE_LOCK:
        _STATE.mouse_actions.append(
            ("scroll", int(scroll_value), scroll_direction),
        )
    return int(scroll_value), scroll_direction


def _fake_screen_size() -> Tuple[int, int]:
    return _STATE.screen_size


def _fake_write(text: str, *_args, **_kwargs) -> str:
    with _STATE_LOCK:
        _STATE.typed_text.append(text)
    return text


def _fake_type_keyboard(keycode: Any, *_args, **_kwargs) -> str:
    with _STATE_LOCK:
        _STATE.keys_pressed.append(keycode)
    return str(keycode)


def _fake_hotkey(keys: List[Any], *_args, **_kwargs) -> Tuple[str, str]:
    joined = ",".join(str(k) for k in keys)
    with _STATE_LOCK:
        _STATE.keys_pressed.append(("hotkey", joined))
    return joined, joined


def _fake_get_clipboard() -> str:
    return _STATE.clipboard_text


def _fake_set_clipboard(text: str) -> None:
    with _STATE_LOCK:
        _STATE.clipboard_text = str(text)


# === Install / uninstall ====================================================

_INSTALLED: Dict[str, Any] = {}


def install_fake_backend() -> None:
    """Replace the headless API entry points with the fake recorders."""
    if _INSTALLED:
        return
    from je_auto_control.utils.clipboard import clipboard as clipboard_module
    from je_auto_control.wrapper import auto_control_keyboard as kbd_module
    from je_auto_control.wrapper import auto_control_mouse as mouse_module
    from je_auto_control.wrapper import auto_control_screen as screen_module
    targets: Dict[Any, Dict[str, Any]] = {
        mouse_module: {
            "get_mouse_position": _fake_get_mouse_position,
            "set_mouse_position": _fake_set_mouse_position,
            "click_mouse": _fake_click_mouse,
            "press_mouse": _fake_press_mouse,
            "release_mouse": _fake_release_mouse,
            "mouse_scroll": _fake_mouse_scroll,
        },
        screen_module: {"screen_size": _fake_screen_size},
        kbd_module: {
            "write": _fake_write,
            "type_keyboard": _fake_type_keyboard,
            "hotkey": _fake_hotkey,
        },
        clipboard_module: {
            "get_clipboard": _fake_get_clipboard,
            "set_clipboard": _fake_set_clipboard,
        },
    }
    for module, replacements in targets.items():
        for name, replacement in replacements.items():
            key = f"{module.__name__}.{name}"
            _INSTALLED[key] = (module, name, getattr(module, name))
            setattr(module, name, replacement)


def uninstall_fake_backend() -> None:
    """Restore the real backend functions previously replaced."""
    while _INSTALLED:
        _key, value = _INSTALLED.popitem()
        module, name, original = value
        setattr(module, name, original)


def maybe_install_from_env() -> bool:
    """Install the fake backend when ``JE_AUTOCONTROL_FAKE_BACKEND`` is truthy."""
    raw = os.environ.get("JE_AUTOCONTROL_FAKE_BACKEND", "").strip().lower()
    if raw in {"1", "true", "yes", "on"}:
        install_fake_backend()
        return True
    return False


__all__ = [
    "FakeState", "fake_state", "install_fake_backend",
    "maybe_install_from_env", "reset_fake_state", "uninstall_fake_backend",
]
