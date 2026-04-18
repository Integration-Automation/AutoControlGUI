"""Command-line entry point.

Usage::

    python -m je_auto_control.cli run script.json [--var x=10 --var y=20]
    python -m je_auto_control.cli list-jobs
    python -m je_auto_control.cli start-server --port 9938
    python -m je_auto_control.cli start-rest --port 9939

The CLI is a thin wrapper around the headless APIs so every feature works
without ever importing PySide6.
"""
import argparse
import json
import signal
import sys
import time
from typing import Dict, List, Optional, Sequence


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
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
