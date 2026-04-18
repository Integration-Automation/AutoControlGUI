"""
Flow-control block commands for the action executor.

These commands receive the owning executor and a dict of arguments;
they may execute nested action lists (``body`` / ``then`` / ``else``)
by delegating back to ``executor.execute_action``.
"""
import time
from typing import Any, Callable, Dict, Mapping, Optional, Sequence

from je_auto_control.utils.exception.exceptions import (
    AutoControlActionException, ImageNotFoundException,
)
from je_auto_control.utils.logging.logging_instance import autocontrol_logger
from je_auto_control.wrapper.auto_control_image import locate_image_center
from je_auto_control.wrapper.auto_control_screen import get_pixel


class LoopBreak(Exception):
    """Internal signal raised by AC_break; caught only by loop handlers."""


class LoopContinue(Exception):
    """Internal signal raised by AC_continue; caught only by loop handlers."""


def _image_present(image: str, threshold: float) -> bool:
    """Return True when the template image is detected on screen."""
    try:
        locate_image_center(image, threshold)
        return True
    except (ImageNotFoundException, OSError, RuntimeError, ValueError, TypeError):
        return False


def _pixel_matches(x: int, y: int, rgb: Sequence[int], tolerance: int) -> bool:
    """Return True when the pixel at (x, y) matches rgb within tolerance."""
    color = get_pixel(x, y)
    if color is None or len(color) < 3 or len(rgb) < 3:
        return False
    return all(abs(int(color[i]) - int(rgb[i])) <= tolerance for i in range(3))


def _run_branch(executor: Any, body: Optional[list]) -> Any:
    """Execute a nested branch only when it is a non-empty list."""
    if not body:
        return None
    return executor.execute_action(body, _validated=True)


def _run_strict(executor: Any, body: list) -> Any:
    """Execute a nested body, re-raising the first error."""
    return executor.execute_action(body, raise_on_error=True, _validated=True)


def exec_if_image_found(executor: Any, args: Mapping[str, Any]) -> Any:
    """Run ``then`` when the image is present, else run ``else``."""
    image = args["image"]
    threshold = float(args.get("threshold", 0.8))
    key = "then" if _image_present(image, threshold) else "else"
    return _run_branch(executor, args.get(key))


def exec_if_pixel(executor: Any, args: Mapping[str, Any]) -> Any:
    """Run ``then`` when pixel matches, else run ``else``."""
    matched = _pixel_matches(
        int(args["x"]), int(args["y"]),
        list(args["rgb"]), int(args.get("tolerance", 0)),
    )
    key = "then" if matched else "else"
    return _run_branch(executor, args.get(key))


def exec_wait_image(executor: Any, args: Mapping[str, Any]) -> bool:
    """Poll for the image until timeout; raise on timeout."""
    del executor
    image = args["image"]
    threshold = float(args.get("threshold", 0.8))
    timeout = float(args.get("timeout", 10.0))
    poll = max(float(args.get("poll", 0.2)), 0.01)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _image_present(image, threshold):
            return True
        time.sleep(poll)
    raise AutoControlActionException(f"AC_wait_image timeout: {image}")


def exec_wait_pixel(executor: Any, args: Mapping[str, Any]) -> bool:
    """Poll for a matching pixel until timeout; raise on timeout."""
    del executor
    x, y = int(args["x"]), int(args["y"])
    rgb = list(args["rgb"])
    tolerance = int(args.get("tolerance", 0))
    timeout = float(args.get("timeout", 10.0))
    poll = max(float(args.get("poll", 0.2)), 0.01)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if _pixel_matches(x, y, rgb, tolerance):
            return True
        time.sleep(poll)
    raise AutoControlActionException(f"AC_wait_pixel timeout at ({x},{y})")


def exec_sleep(executor: Any, args: Mapping[str, Any]) -> None:
    """Sleep for ``seconds``."""
    del executor
    time.sleep(float(args["seconds"]))


def exec_loop(executor: Any, args: Mapping[str, Any]) -> int:
    """Execute ``body`` a fixed number of times; honour break/continue."""
    times = int(args["times"])
    body = args.get("body") or []
    completed = 0
    for _ in range(times):
        try:
            executor.execute_action(body, _validated=True)
        except LoopContinue:
            completed += 1
            continue
        except LoopBreak:
            break
        completed += 1
    return completed


def exec_while_image(executor: Any, args: Mapping[str, Any]) -> int:
    """Execute ``body`` while the image is present, up to ``max_iter``."""
    image = args["image"]
    threshold = float(args.get("threshold", 0.8))
    max_iter = int(args.get("max_iter", 100))
    body = args.get("body") or []
    iterations = 0
    while iterations < max_iter and _image_present(image, threshold):
        try:
            executor.execute_action(body, _validated=True)
        except LoopContinue:
            pass
        except LoopBreak:
            break
        iterations += 1
    return iterations


def exec_retry(executor: Any, args: Mapping[str, Any]) -> Any:
    """Execute ``body`` with retries; raise after exhausting attempts."""
    max_attempts = max(int(args.get("max_attempts", 3)), 1)
    backoff = float(args.get("backoff", 0.5))
    body = args.get("body") or []
    last_error: Optional[BaseException] = None
    for attempt in range(max_attempts):
        try:
            return _run_strict(executor, body)
        except (AutoControlActionException, OSError, RuntimeError,
                AttributeError, TypeError, ValueError) as error:
            last_error = error
            autocontrol_logger.info(
                "AC_retry attempt %d/%d failed: %s",
                attempt + 1, max_attempts, repr(error)
            )
            if attempt + 1 < max_attempts:
                time.sleep(backoff * (2 ** attempt))
    raise AutoControlActionException(
        f"AC_retry exhausted after {max_attempts} attempts"
    ) from last_error


def exec_break(executor: Any, args: Mapping[str, Any]) -> None:
    """Signal the innermost loop to stop."""
    del executor, args
    raise LoopBreak()


def exec_continue(executor: Any, args: Mapping[str, Any]) -> None:
    """Signal the innermost loop to advance to the next iteration."""
    del executor, args
    raise LoopContinue()


BLOCK_COMMANDS: Dict[str, Callable[[Any, Mapping[str, Any]], Any]] = {
    "AC_if_image_found": exec_if_image_found,
    "AC_if_pixel": exec_if_pixel,
    "AC_wait_image": exec_wait_image,
    "AC_wait_pixel": exec_wait_pixel,
    "AC_sleep": exec_sleep,
    "AC_loop": exec_loop,
    "AC_while_image": exec_while_image,
    "AC_retry": exec_retry,
    "AC_break": exec_break,
    "AC_continue": exec_continue,
}
