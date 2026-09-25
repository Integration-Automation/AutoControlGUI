"""Data-source and transform block commands for the action executor.

These are the ``*_to_var`` steps plus their variable assertions: they read
from a shell command, a clock, a PRNG, a PDF, a TOTP secret, a database,
a file, an HTTP endpoint or OCR, and store the result in the executor's
variable scope. Unlike :mod:`flow_control` they never execute a nested
action list, so they carry no loop or branch semantics.

They are registered in ``flow_control.BLOCK_COMMANDS`` alongside the real
flow-control commands, which is the only table the executor reads.
"""
import json
from typing import Any, Callable, Dict, Mapping

from je_auto_control.utils.exception.exceptions import AutoControlActionException


def exec_shell_to_var(executor: Any, args: Mapping[str, Any]) -> Dict[str, Any]:
    """Run a shell command and store its stdout in a flow variable.

    Never ``shell=True``. A list is the argv; a string is split with POSIX
    rules, except on Windows, where it goes to ``CreateProcess`` as the
    command line it is -- ``shlex`` in non-POSIX mode keeps the quote
    characters in each token, and ``subprocess`` then quoted them again.
    Captured stdout is decoded with ``encoding`` (default: the locale's,
    which is what a console program writes on Windows) and bound under
    ``var`` (default ``shell_output``) for later ``${var}`` use.
    """
    import subprocess  # nosec B404 — argv list only, no shell
    from je_auto_control.utils.shell_process.shell_exec import (
        command_args, console_encoding, refuse_batch_metacharacters, run_captured,
    )
    command = args.get("command", args.get("shell_command"))
    if command is None or command == "" or command == []:
        # str(None) ran a program named "None".
        raise AutoControlActionException("AC_shell_to_var needs 'command'")
    argv = command_args(command if isinstance(command, list) else str(command))
    # As AC_shell_command does: cmd.exe re-parses a .bat's arguments, so a
    # ${var} holding "x&ver" ran a second command.
    refuse_batch_metacharacters(argv)
    encoding = str(args.get("encoding") or console_encoding())
    timeout_s = float(args.get("timeout", 30.0))
    try:
        completed = run_captured(argv, timeout_s)
    except OSError as error:
        raise AutoControlActionException(f"AC_shell_to_var: could not start: {error}") from error
    except subprocess.TimeoutExpired as error:
        # TimeoutExpired subclasses SubprocessError (not AutoControlException
        # nor OSError), so without this it escapes every executor containment
        # boundary and aborts the whole script.
        raise AutoControlActionException(
            f"AC_shell_to_var: command timed out after {timeout_s}s"
        ) from error
    output = completed.stdout.decode(encoding, errors="replace").strip()
    var_name = args.get("var", "shell_output")
    executor.variables.set(var_name, output)
    return {"var": var_name, "output": output,
            "returncode": completed.returncode}


def _now():
    import datetime as _dt
    return _dt.datetime.now()


def exec_now_to_var(executor: Any, args: Mapping[str, Any]) -> Dict[str, Any]:
    """Store the current local time (strftime format) in a flow variable."""
    value = _now().strftime(str(args.get("format", "%Y-%m-%d %H:%M:%S")))
    var_name = args.get("var", "now")
    executor.variables.set(var_name, value)
    return {"var": var_name, "value": value}


def exec_random_to_var(executor: Any,
                       args: Mapping[str, Any]) -> Dict[str, Any]:
    """Store a random value (int / float / choice) in a flow variable."""
    import random
    rng = random.Random(args.get("seed"))  # nosec B311  # reason: non-crypto test data
    kind = str(args.get("kind", "int"))
    if kind == "choice":
        value: Any = rng.choice(list(args.get("choices") or [None]))  # NOSONAR S2245 non-crypto seeded
    elif kind == "float":
        value = rng.uniform(float(args.get("min", 0.0)),
                            float(args.get("max", 1.0)))
    else:
        value = rng.randint(int(args.get("min", 0)), int(args.get("max", 100)))  # NOSONAR S2245 non-crypto
    var_name = args.get("var", "random")
    executor.variables.set(var_name, value)
    return {"var": var_name, "value": value}


def exec_assert_var(executor: Any, args: Mapping[str, Any]) -> Dict[str, Any]:
    """Assert a flow variable satisfies a condition (assertion DSL)."""
    from je_auto_control.utils.assertion import assert_variable
    name = args["name"]
    return assert_variable(
        executor.variables.get_value(name), op=str(args.get("op", "eq")),
        expected=args.get("value"), name=name,
        raise_on_fail=bool(args.get("raise_on_fail", True)),
    ).to_dict()


def exec_pdf_to_var(executor: Any, args: Mapping[str, Any]) -> Dict[str, Any]:
    """Extract a PDF's text (all pages or one page) into a flow variable."""
    from je_auto_control.utils.pdf.pdf_reader import extract_pdf_text
    text = extract_pdf_text(args["path"], pages=args.get("page"))
    var_name = args.get("var", "pdf_text")
    executor.variables.set(var_name, text)
    return {"var": var_name, "length": len(text)}


def exec_otp_to_var(executor: Any, args: Mapping[str, Any]) -> Dict[str, Any]:
    """Generate a TOTP code from a base32 secret into a flow variable (2FA)."""
    from je_auto_control.utils.otp import generate_totp
    code = generate_totp(args["secret"], step=int(args.get("step", 30)),
                         digits=int(args.get("digits", 6)))
    var_name = args.get("var", "otp")
    executor.variables.set(var_name, code)
    return {"var": var_name}


def exec_sql_to_var(executor: Any, args: Mapping[str, Any]) -> Dict[str, Any]:
    """Run a read-only SQLite query and store its result in a flow variable."""
    from je_auto_control.utils.sql.sql_query import query_sqlite
    fetch = str(args.get("fetch", "all"))
    result = query_sqlite(args["database"], args["query"],
                          params=args.get("params"), fetch=fetch)
    var_name = args.get("var", "sql_result")
    executor.variables.set(var_name, result)
    return {"var": var_name, "fetch": fetch}


def exec_assert_db(_executor: Any,
                   args: Mapping[str, Any]) -> Dict[str, Any]:
    """Assert a scalar SQLite query result satisfies a condition.

    Takes the executor every ``BLOCK_COMMANDS`` entry is called with and
    does not need it: this command asserts on the query, storing nothing.
    """
    from je_auto_control.utils.assertion import assert_variable
    from je_auto_control.utils.sql.sql_query import query_sqlite
    value = query_sqlite(args["database"], args["query"],
                         params=args.get("params"), fetch="scalar")
    return assert_variable(
        value, op=str(args.get("op", "eq")), expected=args.get("expected"),
        name="AC_assert_db",
        raise_on_fail=bool(args.get("raise_on_fail", True)),
    ).to_dict()


def exec_read_file_to_var(executor: Any,
                          args: Mapping[str, Any]) -> Dict[str, Any]:
    """Read a file's text content into a flow variable."""
    from pathlib import Path
    # utf-8-sig by default: Notepad and PowerShell write a BOM, which stayed
    # at the front of the variable and failed an equality check.
    text = Path(args["path"]).read_text(encoding=args.get("encoding", "utf-8-sig"))
    var_name = args.get("var", "file_content")
    executor.variables.set(var_name, text)
    return {"var": var_name, "length": len(text)}


def _dig_json(body: str, path: str) -> Any:
    """Navigate a dotted JSON path, e.g. ``data.0.name``."""
    data = json.loads(body)
    for part in str(path).split("."):
        data = data[int(part)] if isinstance(data, list) else data[part]
    return data


def exec_http_to_var(executor: Any, args: Mapping[str, Any]) -> Dict[str, Any]:
    """Request a URL and store the body (or a JSON field) in a flow variable.

    Supports method/headers/json_body/data/auth via the shared HTTP client,
    so the same command drives plain GET reads and POST/PUT API calls.
    """
    from je_auto_control.utils.http_client.http_client import http_request
    response = http_request(
        args["url"], method=str(args.get("method", "GET")),
        headers=args.get("headers"), json_body=args.get("json_body"),
        data=args.get("data"), auth=args.get("auth"),
        timeout=float(args.get("timeout", 30.0)),
    )
    json_path = args.get("json_path")
    body = response["text"]
    value = _dig_json(body, json_path) if json_path else body
    var_name = args.get("var", "http_response")
    executor.variables.set(var_name, value)
    return {"var": var_name, "status": response["status"]}


_SIMPLE_TRANSFORMS: Dict[str, Callable[[str], str]] = {
    "upper": str.upper, "lower": str.lower, "strip": str.strip,
    "title": str.title, "lstrip": str.lstrip, "rstrip": str.rstrip,
}


def _regex_extract(text: str, args: Mapping[str, Any]) -> str:
    import re
    try:
        pattern = re.compile(str(args.get("pattern", "")))
    except re.error as error:
        raise AutoControlActionException(f"invalid regex: {error}") from error
    match = pattern.search(text)
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
        # An empty body is a no-op (it measures nothing), not an error.
        lambda: executor.execute_action(body, _validated=True) if body else None,
        max_ms=float(args.get("max_ms", 1000.0)),
        min_ms=float(args.get("min_ms", 0.0)),
        raise_on_fail=bool(args.get("raise_on_fail", True)),
    ).to_dict()
