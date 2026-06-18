"""Command-line entry point.

Installed as the ``je_auto_control`` console script; also runnable via
``python -m je_auto_control.cli``.

Usage::

    je_auto_control run script.json [--var x=10 --var y=20] [--dry-run]
    je_auto_control validate script.json          # alias: lint
    je_auto_control list-commands [--filter mouse] [--json]
    je_auto_control fmt script.json [--check]
    je_auto_control record out.json [--duration 5]
    je_auto_control codegen script.json [--target pytest] [-o test_flow.py]
    je_auto_control version
    je_auto_control list-jobs
    je_auto_control start-server --port 9938
    je_auto_control start-rest --port 9939

The CLI is a thin wrapper around the headless APIs so every feature works
without ever importing PySide6.
"""
import argparse
import json
import signal
import sys
import threading
import time
from typing import Dict, List, Optional, Sequence

from je_auto_control.utils.exception.exceptions import (
    AutoControlActionException,
    AutoControlException,
    AutoControlJsonActionException,
)


def _parse_vars(pairs: Optional[Sequence[str]]) -> Dict[str, object]:
    """Parse ``--var name=value`` entries into a dict (JSON value when parseable)."""
    resolved: Dict[str, object] = {}
    for raw in pairs or []:
        if "=" not in raw:
            raise SystemExit(f"--var must be name=value; got {raw!r}")
        name, value = raw.split("=", 1)
        try:
            resolved[name.strip()] = json.loads(value)
        except ValueError:
            resolved[name.strip()] = value
    return resolved


def cmd_run(args: argparse.Namespace) -> int:
    from je_auto_control.utils.executor.action_executor import (
        execute_action, execute_action_with_vars,
    )
    from je_auto_control.utils.json.json_file import read_action_json
    actions = read_action_json(args.script)
    variables = _parse_vars(args.var)
    if args.dry_run:
        from je_auto_control.utils.executor.action_executor import executor
        if variables:
            from je_auto_control.utils.script_vars.interpolate import (
                interpolate_actions,
            )
            actions = interpolate_actions(actions, variables)
        result = executor.execute_action(actions, dry_run=True)
    elif variables:
        result = execute_action_with_vars(actions, variables)
    else:
        result = execute_action(actions)
    json.dump(result, sys.stdout, indent=2, default=str, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Validate an action file's structure without executing it."""
    from je_auto_control.utils.executor.action_executor import executor
    from je_auto_control.utils.executor.action_schema import validate_actions
    from je_auto_control.utils.json.json_file import read_action_json
    actions = read_action_json(args.script)
    validate_actions(actions, executor.known_commands())
    sys.stdout.write(f"OK: {len(actions)} action(s)\n")
    return 0


def cmd_list_commands(args: argparse.Namespace) -> int:
    """Print the known ``AC_*`` commands as text or JSON."""
    from je_auto_control.utils.executor.action_executor import executor
    names = sorted(executor.known_commands())
    if args.filter:
        needle = args.filter.lower()
        names = [name for name in names if needle in name.lower()]
    if args.json:
        json.dump(names, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
    else:
        for name in names:
            sys.stdout.write(f"{name}\n")
    return 0


def cmd_fmt(args: argparse.Namespace) -> int:
    """Canonicalise an action file's JSON, or report drift under ``--check``."""
    from je_auto_control.utils.json.json_file import format_action_json
    changed = format_action_json(args.script, check=args.check)
    if args.check:
        if changed:
            sys.stderr.write(f"would reformat: {args.script}\n")
            return 1
        return 0
    sys.stdout.write(
        f"{'reformatted' if changed else 'unchanged'}: {args.script}\n")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    """Record mouse/keyboard input into an action file."""
    if sys.platform == "darwin":
        sys.stderr.write("record is not supported on macOS\n")
        return 1
    from je_auto_control.wrapper.auto_control_record import record_to_json
    stop_event = threading.Event()
    if args.duration is None:
        sys.stderr.write("Recording... press Enter to stop.\n")
        threading.Thread(
            target=_set_on_enter, args=(stop_event,), daemon=True).start()
    actions = record_to_json(
        args.output, stop_event=stop_event, timeout=args.duration)
    sys.stderr.write(f"Recorded {len(actions)} action(s) to {args.output}\n")
    return 0


def _set_on_enter(stop_event: threading.Event) -> None:
    """Block on a line of stdin, then signal the recorder to stop."""
    try:
        sys.stdin.readline()
    except (EOFError, OSError):
        pass
    stop_event.set()


def cmd_codegen(args: argparse.Namespace) -> int:
    """Generate pytest/python/robot source from an action file."""
    from je_auto_control.utils.codegen.codegen import (
        generate_code, generate_code_file,
    )
    from je_auto_control.utils.json.json_file import read_action_json
    if args.output:
        generate_code_file(args.script, args.output, target=args.target,
                           name=args.name, style=args.style)
        sys.stderr.write(f"Wrote {args.target} code to {args.output}\n")
        return 0
    code = generate_code(read_action_json(args.script), target=args.target,
                         name=args.name, style=args.style)
    sys.stdout.write(code)
    return 0


def cmd_version(_: argparse.Namespace) -> int:
    """Print the installed ``je_auto_control`` version."""
    from importlib.metadata import PackageNotFoundError, version
    try:
        sys.stdout.write(version("je_auto_control") + "\n")
    except PackageNotFoundError:
        sys.stdout.write("unknown\n")
    return 0


def cmd_list_jobs(_: argparse.Namespace) -> int:
    from je_auto_control.utils.scheduler.scheduler import default_scheduler
    jobs = default_scheduler.list_jobs()
    for job in jobs:
        kind = "cron" if job.is_cron else f"{job.interval_seconds}s"
        sys.stdout.write(
            f"{job.job_id}\t{kind}\truns={job.runs}\t{job.script_path}\n"
        )
    return 0


def cmd_start_server(args: argparse.Namespace) -> int:
    from je_auto_control.utils.socket_server.auto_control_socket_server import (
        start_autocontrol_socket_server,
    )
    server = start_autocontrol_socket_server(args.host, args.port)
    sys.stdout.write(f"Socket server listening on {args.host}:{args.port}\n")
    _run_until_signal(server.shutdown)
    server.server_close()
    return 0


def cmd_start_rest(args: argparse.Namespace) -> int:
    from je_auto_control.utils.rest_api.rest_server import start_rest_api_server
    server = start_rest_api_server(args.host, args.port)
    sys.stdout.write(f"REST API listening on {server.address[0]}:{server.address[1]}\n")
    _run_until_signal(server.stop)
    return 0


def _run_until_signal(shutdown: callable) -> None:
    stopping = {"flag": False}

    def _handler(_signum, _frame):
        stopping["flag"] = True

    signal.signal(signal.SIGINT, _handler)
    try:
        while not stopping["flag"]:
            time.sleep(0.25)
    finally:
        shutdown()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="je_auto_control")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="Execute an action JSON file")
    p_run.add_argument("script")
    p_run.add_argument("--var", action="append",
                       help="name=value override; may be repeated")
    p_run.add_argument("--dry-run", action="store_true",
                       help="record actions without calling them")
    p_run.set_defaults(func=cmd_run)

    for name in ("validate", "lint"):
        p_validate = sub.add_parser(name, help="Validate an action JSON file")
        p_validate.add_argument("script")
        p_validate.set_defaults(func=cmd_validate)

    p_list = sub.add_parser("list-commands", help="List known AC_* commands")
    p_list.add_argument("--filter", help="Only names containing this text")
    p_list.add_argument("--json", action="store_true", help="Emit JSON")
    p_list.set_defaults(func=cmd_list_commands)

    p_fmt = sub.add_parser("fmt", help="Canonicalise an action file's JSON")
    p_fmt.add_argument("script")
    p_fmt.add_argument("--check", action="store_true",
                       help="Exit 1 if the file is not already formatted")
    p_fmt.set_defaults(func=cmd_fmt)

    p_record = sub.add_parser("record", help="Record input into an action file")
    p_record.add_argument("output")
    p_record.add_argument("--duration", type=float, default=None,
                          help="Auto-stop after N seconds (else press Enter)")
    p_record.set_defaults(func=cmd_record)

    p_codegen = sub.add_parser(
        "codegen", help="Generate test code from an action file")
    p_codegen.add_argument("script")
    p_codegen.add_argument("--target", choices=("pytest", "python", "robot"),
                           default="pytest")
    p_codegen.add_argument("--style", choices=("calls", "actions"),
                           default="calls")
    p_codegen.add_argument("--name", default="recorded_flow")
    p_codegen.add_argument("-o", "--output", help="Write to file instead of stdout")
    p_codegen.set_defaults(func=cmd_codegen)

    p_version = sub.add_parser("version", help="Print the installed version")
    p_version.set_defaults(func=cmd_version)

    p_jobs = sub.add_parser("list-jobs", help="List scheduler jobs")
    p_jobs.set_defaults(func=cmd_list_jobs)

    p_srv = sub.add_parser("start-server", help="Start the TCP socket server")
    p_srv.add_argument("--host", default="127.0.0.1")
    p_srv.add_argument("--port", type=int, default=9938)
    p_srv.set_defaults(func=cmd_start_server)

    p_rest = sub.add_parser("start-rest", help="Start the REST API server")
    p_rest.add_argument("--host", default="127.0.0.1")
    p_rest.add_argument("--port", type=int, default=9939)
    p_rest.set_defaults(func=cmd_start_rest)
    return parser


def main(argv: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (AutoControlActionException, AutoControlException,
            AutoControlJsonActionException, OSError, RuntimeError,
            ValueError) as error:
        sys.stderr.write(f"error: {error}\n")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
