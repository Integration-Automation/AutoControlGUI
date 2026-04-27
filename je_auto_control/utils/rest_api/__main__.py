"""CLI entry: ``python -m je_auto_control.utils.rest_api``.

Starts the REST API in the foreground and prints the URL + bearer token
(or just the URL if a token was supplied via ``--token``). Ctrl-C stops
the server cleanly.
"""
from __future__ import annotations

import argparse
import sys
import time
from typing import Optional

from je_auto_control.utils.rest_api.rest_server import RestApiServer


def _build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="je_auto_control.utils.rest_api",
        description="Run the AutoControl REST API server.",
    )
    parser.add_argument("--host", default="127.0.0.1",
                        help="bind address (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=9939,
                        help="bind port (default 9939, 0 = auto)")
    parser.add_argument("--token", default=None,
                        help="bearer token (auto-generated if omitted)")
    parser.add_argument("--no-audit", action="store_true",
                        help="disable audit-log writes")
    return parser


def main(argv: Optional[list] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    server = RestApiServer(
        host=args.host, port=args.port, token=args.token,
        enable_audit=not args.no_audit,
    )
    server.start()
    host, port = server.address
    print(f"REST API listening at http://{host}:{port}")
    print(f"Bearer token: {server.token}")
    print("Send Authorization: Bearer <token> on every non-/health call.")
    print("Press Ctrl-C to stop.")
    try:
        while True:
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nShutting down...")
    finally:
        server.stop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
