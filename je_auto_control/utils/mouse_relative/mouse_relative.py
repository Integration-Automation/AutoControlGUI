"""Relative mouse movement — move by a delta from the current position.

The mouse wrapper exposes only absolute ``set_mouse_position``; there is no
"nudge the pointer by (dx, dy)" (pynput / PyAutoGUI ``moveRel`` staple), which is
what relative-pointer / canvas / FPS-style apps and incremental drags need.

:func:`relative_target` is the pure arithmetic (current + delta) and is
unit-testable; :func:`move_mouse_relative` reads the live position and sets the
new one, with both the getter and setter injectable so it is tested without a
real pointer. Imports no ``PySide6``.
"""
from typing import Any, Callable, Dict, Optional, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlMouseException

PositionGetter = Callable[[], Optional[Tuple[int, int]]]
PositionSetter = Callable[[int, int], Any]


def relative_target(current: Tuple[int, int], dx: int, dy: int) -> Tuple[int, int]:
    """Return ``current`` offset by ``(dx, dy)`` as an integer ``(x, y)``."""
    return int(current[0]) + int(dx), int(current[1]) + int(dy)


def move_mouse_relative(dx: int, dy: int, *,
                        get_position: Optional[PositionGetter] = None,
                        set_position: Optional[PositionSetter] = None,
                        ) -> Dict[str, Any]:
    """Move the pointer by ``(dx, dy)`` relative to where it is now.

    ``get_position`` / ``set_position`` default to the real mouse wrapper but are
    injectable for headless tests. Raises :class:`AutoControlMouseException` if
    the current position cannot be read.
    """
    getter = get_position or _default_get_position
    setter = set_position or _default_set_position
    current = getter()
    if current is None:
        raise AutoControlMouseException("could not read the current mouse position")
    target = relative_target((int(current[0]), int(current[1])), dx, dy)
    setter(target[0], target[1])
    return {"from": [int(current[0]), int(current[1])],
            "to": [target[0], target[1]], "delta": [int(dx), int(dy)]}


def _default_get_position() -> Optional[Tuple[int, int]]:
    from je_auto_control.wrapper.auto_control_mouse import get_mouse_position
    return get_mouse_position()


def _default_set_position(x: int, y: int) -> Any:
    from je_auto_control.wrapper.auto_control_mouse import set_mouse_position
    return set_mouse_position(x, y)
