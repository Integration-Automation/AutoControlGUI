"""Pure-Python helpers for editing recorded action lists.

All functions return new lists rather than mutating the input so callers can
preserve the original recording.
"""
from typing import Callable, List


def trim_actions(actions: List[list], start: int = 0, end: int = None
                 ) -> List[list]:
    """Return a slice ``actions[start:end]`` (end=None means to the end)."""
    return list(actions[start:end])


def insert_action(actions: List[list], index: int, new_action: list
                  ) -> List[list]:
    """Return a new list with ``new_action`` inserted at ``index``."""
    result = list(actions)
    if index < 0 or index > len(result):
        raise IndexError(f"insert_action: index {index} out of range")
    result.insert(index, new_action)
    return result


def remove_action(actions: List[list], index: int) -> List[list]:
    """Return a new list with the entry at ``index`` removed."""
    if index < 0 or index >= len(actions):
        raise IndexError(f"remove_action: index {index} out of range")
    return actions[:index] + actions[index + 1:]


def filter_actions(actions: List[list],
                   predicate: Callable[[list], bool]) -> List[list]:
    """Return only actions for which ``predicate(action)`` is true."""
    return [action for action in actions if predicate(action)]


def adjust_delays(actions: List[list], factor: float = 1.0,
                  clamp_ms: int = 0) -> List[list]:
    """Scale every ``AC_sleep`` delay by ``factor`` (and clamp to ``clamp_ms``).

    :param factor: multiplier for ``seconds`` values (<1 speeds up).
    :param clamp_ms: floor for each resulting delay, in milliseconds.
    """
    floor_seconds = max(0.0, float(clamp_ms) / 1000.0)
    adjusted: List[list] = []
    for action in actions:
        if _is_sleep(action):
            original = float(action[1].get("seconds", 0.0))
            new_seconds = max(floor_seconds, original * float(factor))
            params = dict(action[1])
            params["seconds"] = new_seconds
            adjusted.append([action[0], params])
        else:
            adjusted.append(action)
    return adjusted


def scale_coordinates(actions: List[list],
                      x_factor: float, y_factor: float) -> List[list]:
    """Multiply every ``x`` / ``y`` parameter; useful when replaying on a new resolution."""
    scaled: List[list] = []
    for action in actions:
        if len(action) < 2 or not isinstance(action[1], dict):
            scaled.append(action)
            continue
        params = dict(action[1])
        if "x" in params and isinstance(params["x"], (int, float)):
            params["x"] = int(round(params["x"] * x_factor))
        if "y" in params and isinstance(params["y"], (int, float)):
            params["y"] = int(round(params["y"] * y_factor))
        scaled.append([action[0], params])
    return scaled


def _is_sleep(action: list) -> bool:
    return (
        isinstance(action, list)
        and len(action) == 2
        and action[0] == "AC_sleep"
        and isinstance(action[1], dict)
    )
