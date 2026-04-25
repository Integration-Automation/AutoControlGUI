"""Single-button mouse-click aliases shared by the action and callback executors.

Each ``AC_mouse_<button>`` command name needs a callable whose signature is
``(x=None, y=None)`` so the button itself is implied by the command name and
not threaded through ``mouse_keycode``. Generating the three callables from
one factory keeps the registration sites identical across executors.
"""
from typing import Callable, Optional, Tuple

from je_auto_control.wrapper.auto_control_mouse import click_mouse

ClickFn = Callable[[Optional[int], Optional[int]], Tuple[int, int, int]]


def _make_button_click(button: str) -> ClickFn:
    def click(x: Optional[int] = None,
              y: Optional[int] = None) -> Tuple[int, int, int]:
        return click_mouse(button, x, y)

    click.__name__ = f"click_{button}"
    click.__qualname__ = click.__name__
    click.__doc__ = f"Click the {button.replace('_', ' ')} mouse button at (x, y)."
    return click


click_mouse_left: ClickFn = _make_button_click("mouse_left")
click_mouse_right: ClickFn = _make_button_click("mouse_right")
click_mouse_middle: ClickFn = _make_button_click("mouse_middle")

__all__ = ["click_mouse_left", "click_mouse_right", "click_mouse_middle"]
