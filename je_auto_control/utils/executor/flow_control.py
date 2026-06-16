"""
Flow-control block commands for the action executor.

These commands receive the owning executor and a dict of arguments;
they may execute nested action lists (``body`` / ``then`` / ``else``)
by delegating back to ``executor.execute_action``.
"""
import json
import threading
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


# Errors a protected block may raise that ``AC_try`` is willing to catch.
# ``LoopBreak`` / ``LoopContinue`` are deliberately excluded so loop
# control-flow still propagates through a try block.
_TRY_CATCHABLE = (
    AutoControlActionException, OSError, RuntimeError,
    AttributeError, TypeError, ValueError,
)


def exec_try(executor: Any, args: Mapping[str, Any]) -> Dict[str, Any]:
    """Run ``body``; on error run ``catch``; always run ``finally``.

    Unlike ``AC_retry`` (which repeats the same body), ``AC_try`` provides
    a recovery path: when ``body`` raises, the ``catch`` branch runs
    instead of aborting the script. The ``finally`` branch always runs —
    on success, on caught error, or while a re-raise / loop break/continue
    propagates. The caught error's text is exposed to ``error_var`` (when
    given) so the ``catch`` branch can inspect it. Set ``reraise`` true to
    re-raise after the ``catch`` branch (still running ``finally`` first).
    """
    body = args.get("body") or []
    caught_repr: Optional[str] = None
    try:
        try:
            _run_strict(executor, body)
        except (LoopBreak, LoopContinue):
            raise
        except _TRY_CATCHABLE as error:
            caught_repr = repr(error)
            autocontrol_logger.info("AC_try caught: %s", caught_repr)
            error_var = args.get("error_var")
            if error_var:
                executor.variables.set(str(error_var), caught_repr)
            _run_branch(executor, args.get("catch"))
            if bool(args.get("reraise", False)):
                raise
    finally:
        _run_branch(executor, args.get("finally"))
    return {"caught": caught_repr}


def exec_break(executor: Any, args: Mapping[str, Any]) -> None:
    """Signal the innermost loop to stop."""
    del executor, args
    raise LoopBreak()


def exec_continue(executor: Any, args: Mapping[str, Any]) -> None:
    """Signal the innermost loop to advance to the next iteration."""
    del executor, args
    raise LoopContinue()


def exec_set_var(executor: Any, args: Mapping[str, Any]) -> Any:
    """Store ``value`` under ``name`` in the executor's variable scope."""
    name = args["name"]
    value = args.get("value")
    executor.variables.set(name, value)
    return value


def exec_get_var(executor: Any, args: Mapping[str, Any]) -> Any:
    """Return the variable named ``name`` (or ``default`` if missing)."""
    return executor.variables.get_value(args["name"], args.get("default"))


def exec_inc_var(executor: Any, args: Mapping[str, Any]) -> Any:
    """Increment a numeric variable by ``by`` (default 1) and return new value."""
    name = args["name"]
    delta = args.get("by", 1)
    current = executor.variables.get_value(name, 0)
    try:
        new_value = current + delta
    except TypeError as error:
        raise AutoControlActionException(
            f"AC_inc_var: variable {name!r} is not numeric: {current!r}"
        ) from error
    executor.variables.set(name, new_value)
    return new_value


_COMPARATORS: Dict[str, Callable[[Any, Any], bool]] = {
    "eq": lambda a, b: a == b,
    "ne": lambda a, b: a != b,
    "lt": lambda a, b: a < b,
    "le": lambda a, b: a <= b,
    "gt": lambda a, b: a > b,
    "ge": lambda a, b: a >= b,
    "contains": lambda a, b: b in a,
    "startswith": lambda a, b: isinstance(a, str) and a.startswith(b),
    "endswith": lambda a, b: isinstance(a, str) and a.endswith(b),
}


def _compare_var(executor: Any, args: Mapping[str, Any], who: str) -> bool:
    """Evaluate ``variable op value`` against the executor's variable scope."""
    op = args.get("op", "eq")
    comparator = _COMPARATORS.get(op)
    if comparator is None:
        raise AutoControlActionException(
            f"{who}: unsupported op {op!r}; "
            f"expected one of {sorted(_COMPARATORS)}"
        )
    current = executor.variables.get_value(args["name"])
    try:
        return comparator(current, args.get("value"))
    except TypeError as error:
        raise AutoControlActionException(
            f"{who}: cannot compare {current!r} {op} {args.get('value')!r}"
        ) from error


def exec_if_var(executor: Any, args: Mapping[str, Any]) -> Any:
    """Run ``then`` when ``variable op value`` holds, else run ``else``."""
    matched = _compare_var(executor, args, "AC_if_var")
    key = "then" if matched else "else"
    return _run_branch(executor, args.get(key))


def exec_while_var(executor: Any, args: Mapping[str, Any]) -> int:
    """Execute ``body`` while ``variable op value`` holds, up to ``max_iter``.

    The condition is re-checked before every iteration against the live
    variable scope, so a body that mutates the variable (e.g.
    ``AC_inc_var``) eventually terminates the loop. ``max_iter`` (default
    1000) is a safety cap that prevents an unbounded loop when the
    condition never becomes false; ``AC_break`` / ``AC_continue`` work as
    in any other loop.
    """
    max_iter = int(args.get("max_iter", 1000))
    body = args.get("body") or []
    iterations = 0
    while iterations < max_iter and _compare_var(executor, args, "AC_while_var"):
        try:
            executor.execute_action(body, _validated=True)
        except LoopContinue:
            pass
        except LoopBreak:
            break
        iterations += 1
    return iterations


def exec_for_each(executor: Any, args: Mapping[str, Any]) -> int:
    """Bind each item in ``items`` to ``as`` and execute ``body``."""
    items = args["items"]
    if not isinstance(items, (list, tuple)):
        raise AutoControlActionException(
            f"AC_for_each: items must be a list, got {type(items).__name__}"
        )
    var_name = args.get("as", "item")
    body = args.get("body") or []
    iterations = 0
    for item in items:
        executor.variables.set(var_name, item)
        try:
            executor.execute_action(body, _validated=True)
        except LoopContinue:
            iterations += 1
            continue
        except LoopBreak:
            break
        iterations += 1
    return iterations


def exec_for_each_row(executor: Any, args: Mapping[str, Any]) -> int:
    """Load rows from a data source and run ``body`` once per row.

    ``source`` is a data-source spec dict (see
    :mod:`je_auto_control.utils.data_source`). Each row dict is bound to
    the variable named by ``as`` (default ``row``) so the body can read
    ``${row.column}``. Honours ``AC_break`` / ``AC_continue``.
    """
    from je_auto_control.utils.data_source import load_rows
    source = args.get("source")
    if not isinstance(source, dict):
        raise AutoControlActionException(
            "AC_for_each_row: 'source' must be a data-source spec dict"
        )
    rows = load_rows(source, limit=args.get("limit"))
    var_name = args.get("as", "row")
    body = args.get("body") or []
    iterations = 0
    for row in rows:
        executor.variables.set(var_name, row)
        try:
            executor.execute_action(body, _validated=True)
        except LoopContinue:
            iterations += 1
            continue
        except LoopBreak:
            break
        iterations += 1
    return iterations


def exec_shell_to_var(executor: Any, args: Mapping[str, Any]) -> Dict[str, Any]:
    """Run a shell command and store its stdout in a flow variable.

    The command is split into an argv list (never ``shell=True``) and its
    captured stdout is bound under ``var`` (default ``shell_output``) for
    later ``${var}`` use — the shell counterpart of ``AC_ocr_to_var``.
    """
    import os
    import shlex
    import subprocess  # nosec B404 — argv list only, no shell
    command = args.get("command", args.get("shell_command"))
    argv = ([str(part) for part in command] if isinstance(command, list)
            else shlex.split(str(command), posix=(os.name != "nt")))
    completed = subprocess.run(  # nosec B603 — argv list, no shell  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit
        argv, capture_output=True, check=False,
        timeout=float(args.get("timeout", 30.0)),
    )
    output = completed.stdout.decode("utf-8", errors="replace").strip()
    var_name = args.get("var", "shell_output")
    executor.variables.set(var_name, output)
    return {"var": var_name, "output": output,
            "returncode": completed.returncode}


def exec_read_file_to_var(executor: Any,
                          args: Mapping[str, Any]) -> Dict[str, Any]:
    """Read a file's text content into a flow variable."""
    from pathlib import Path
    text = Path(args["path"]).read_text(encoding=args.get("encoding", "utf-8"))
    var_name = args.get("var", "file_content")
    executor.variables.set(var_name, text)
    return {"var": var_name, "length": len(text)}


def _http_get(url: str, method: str, timeout: float) -> tuple:
    """Issue an HTTP(S) GET, returning ``(status, body)``. http/https only."""
    import urllib.request
    scheme = url.split("://", 1)[0].lower() if "://" in url else ""
    if scheme not in ("http", "https"):
        raise AutoControlActionException(
            f"AC_http_to_var: only http/https URLs allowed, got {url!r}"
        )
    request = urllib.request.Request(url, method=method.upper())
    with urllib.request.urlopen(  # nosec B310 — scheme allow-listed above
            request, timeout=timeout) as response:
        return int(response.status), response.read().decode(
            "utf-8", errors="replace")


def _dig_json(body: str, path: str) -> Any:
    """Navigate a dotted JSON path, e.g. ``data.0.name``."""
    data = json.loads(body)
    for part in str(path).split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def exec_http_to_var(executor: Any, args: Mapping[str, Any]) -> Dict[str, Any]:
    """GET a URL and store the body (or a JSON field) in a flow variable."""
    status, body = _http_get(
        args["url"], str(args.get("method", "GET")),
        float(args.get("timeout", 30.0)),
    )
    json_path = args.get("json_path")
    value = _dig_json(body, json_path) if json_path else body
    var_name = args.get("var", "http_response")
    executor.variables.set(var_name, value)
    return {"var": var_name, "status": status}


_SIMPLE_TRANSFORMS: Dict[str, Callable[[str], str]] = {
    "upper": str.upper, "lower": str.lower, "strip": str.strip,
    "title": str.title, "lstrip": str.lstrip, "rstrip": str.rstrip,
}


def _regex_extract(text: str, args: Mapping[str, Any]) -> str:
    import re
    match = re.search(str(args.get("pattern", "")), text)
    return match.group(int(args.get("group", 0))) if match else ""


def _slice_text(text: str, args: Mapping[str, Any]) -> str:
    start = args.get("start")
    end = args.get("end")
    return text[(int(start) if start is not None else None):
                (int(end) if end is not None else None)]


def _transform_string(text: str, op: str, args: Mapping[str, Any]) -> str:
    simple = _SIMPLE_TRANSFORMS.get(op)
    if simple is not None:
        return simple(text)
    if op == "replace":
        return text.replace(str(args.get("find", "")),
                            str(args.get("replace_with", "")))
    if op == "regex":
        return _regex_extract(text, args)
    if op == "slice":
        return _slice_text(text, args)
    raise AutoControlActionException(f"AC_transform_var: unknown op {op!r}")


def exec_transform_var(executor: Any,
                       args: Mapping[str, Any]) -> Dict[str, Any]:
    """Apply a string transform to a variable (in place or into ``into``)."""
    name = args["name"]
    value = str(executor.variables.get_value(name, ""))
    result = _transform_string(value, str(args.get("op", "strip")), args)
    target = args.get("into", name)
    executor.variables.set(target, result)
    return {"var": target, "value": result}


def exec_ocr_to_var(executor: Any, args: Mapping[str, Any]) -> Dict[str, Any]:
    """Read OCR text from a screen region into a flow variable.

    Binds the recognised text under ``var`` (default ``ocr_text``) so later
    steps can read it as ``${var}`` — the bridge between OCR and the
    variable scope for data-driven flows.
    """
    from je_auto_control.utils.ocr.ocr_engine import read_text_in_region
    region = args.get("region")
    if isinstance(region, str):
        region = json.loads(region) if region.strip() else None
    matches = read_text_in_region(
        region=region, lang=args.get("lang", "eng"),
        min_confidence=float(args.get("min_confidence", 60.0)),
    )
    text = " ".join(match.text for match in matches).strip()
    var_name = args.get("var", "ocr_text")
    executor.variables.set(var_name, text)
    return {"var": var_name, "text": text}


def exec_assert_duration(executor: Any, args: Mapping[str, Any]) -> Dict[str, Any]:
    """Assert ``body`` completes within ``max_ms`` (a performance budget)."""
    from je_auto_control.utils.assertion import assert_duration
    body = args.get("body") or []
    return assert_duration(
        lambda: executor.execute_action(body, _validated=True),
        max_ms=float(args.get("max_ms", 1000.0)),
        min_ms=float(args.get("min_ms", 0.0)),
        raise_on_fail=bool(args.get("raise_on_fail", True)),
    ).to_dict()


def _as_list(value: Any) -> list:
    """Accept a native list or a JSON-string list (for the visual builder)."""
    if isinstance(value, str):
        return json.loads(value) if value.strip() else []
    return list(value) if value else []


def exec_parallel(executor: Any, args: Mapping[str, Any]) -> Dict[str, Any]:
    """Run each branch action list concurrently on its own isolated executor.

    ``branches`` is a list of action lists (or a JSON string of one). Each
    branch runs on a fresh :class:`Executor` with a separate variable scope,
    so concurrent branches never race on shared state.
    """
    del executor
    from je_auto_control.utils.executor.action_executor import Executor
    branches = _as_list(args.get("branches"))
    results: list = [None] * len(branches)

    def _run(index: int, branch: Any) -> None:
        results[index] = Executor().execute_action(branch, _validated=True)

    threads = [threading.Thread(target=_run, args=(idx, branch), daemon=True)
               for idx, branch in enumerate(branches)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    return {"branches": len(branches), "results": results}


def exec_define_macro(executor: Any, args: Mapping[str, Any]) -> Dict[str, Any]:
    """Register a named, parameterised macro for later ``AC_call_macro``."""
    name = args["name"]
    raw_params = args.get("params") or []
    if isinstance(raw_params, str):
        params = [part.strip() for part in raw_params.split(",") if part.strip()]
    else:
        params = [str(part) for part in raw_params]
    executor.macros[name] = {"params": params, "body": args.get("body") or []}
    return {"defined": name, "params": params}


def exec_call_macro(executor: Any, args: Mapping[str, Any]) -> Any:
    """Invoke a macro registered by ``AC_define_macro``, binding call args.

    Each parameter is bound into the executor's variable scope before the
    macro body runs, so the body reads ``${param}`` as usual.
    """
    name = args["name"]
    macro = executor.macros.get(name)
    if macro is None:
        raise AutoControlActionException(
            f"AC_call_macro: unknown macro {name!r}"
        )
    raw_args = args.get("args") or {}
    if isinstance(raw_args, str):
        raw_args = json.loads(raw_args) if raw_args.strip() else {}
    for param in macro["params"]:
        executor.variables.set(param, raw_args.get(param))
    return executor.execute_action(macro["body"], _validated=True)


BLOCK_COMMANDS: Dict[str, Callable[[Any, Mapping[str, Any]], Any]] = {
    "AC_if_image_found": exec_if_image_found,
    "AC_if_pixel": exec_if_pixel,
    "AC_if_var": exec_if_var,
    "AC_wait_image": exec_wait_image,
    "AC_wait_pixel": exec_wait_pixel,
    "AC_sleep": exec_sleep,
    "AC_loop": exec_loop,
    "AC_while_image": exec_while_image,
    "AC_while_var": exec_while_var,
    "AC_retry": exec_retry,
    "AC_try": exec_try,
    "AC_break": exec_break,
    "AC_continue": exec_continue,
    "AC_set_var": exec_set_var,
    "AC_get_var": exec_get_var,
    "AC_inc_var": exec_inc_var,
    "AC_for_each": exec_for_each,
    "AC_for_each_row": exec_for_each_row,
    "AC_assert_duration": exec_assert_duration,
    "AC_parallel": exec_parallel,
    "AC_define_macro": exec_define_macro,
    "AC_call_macro": exec_call_macro,
    "AC_ocr_to_var": exec_ocr_to_var,
    "AC_shell_to_var": exec_shell_to_var,
    "AC_read_file_to_var": exec_read_file_to_var,
    "AC_http_to_var": exec_http_to_var,
    "AC_transform_var": exec_transform_var,
}
