"""``je_auto_control users ...``: manage the RBAC user store from a terminal.

This is how the first admin comes to exist. The REST API and the MCP server
refuse every token until the store has a user, and the ``AC_user_*``
commands need an admin's token -- so the first one is created here, on the
host, by whoever can write the store file::

    je_auto_control users --users /etc/autocontrol/users.json add alice --role admin
    je_auto_control users list                    # store from JE_AUTOCONTROL_RBAC_USERS
    je_auto_control users set-role bob operator
    je_auto_control users rotate-token bob
    je_auto_control users remove bob

``add`` and ``rotate-token`` print the token once, on standard output; it is
not stored (only its hash is) and cannot be shown again. The same commands
run as ``python -m je_auto_control.utils.rbac ...``.
"""
from __future__ import annotations

import argparse
import json
import sys
from typing import Any, List, Optional

from je_auto_control.utils.rbac import admin
from je_auto_control.utils.rbac.authorization import USERS_ENV
from je_auto_control.utils.rbac.users import Role


def add_users_arguments(parser: argparse.ArgumentParser) -> None:
    """Give ``parser`` the ``users`` sub-commands; :func:`cmd_users` runs them."""
    parser.add_argument(
        "--users", metavar="PATH",
        help=f"user store file (default: the one {USERS_ENV} names)")
    parser.add_argument("--json", action="store_true", help="print the result as JSON")
    actions = parser.add_subparsers(dest="users_command", required=True)

    p_add = actions.add_parser("add", help="Add a user and print its token once")
    p_add.add_argument("user_id")
    p_add.add_argument("--role", choices=Role.all(), default=Role.VIEWER)
    p_add.add_argument("--name", default="", help="display name (default: the user id)")
    p_add.add_argument("--tag", action="append", help="free-form tag; may be repeated")

    p_remove = actions.add_parser("remove", help="Remove a user")
    p_remove.add_argument("user_id")

    p_role = actions.add_parser("set-role", help="Change a user's role")
    p_role.add_argument("user_id")
    p_role.add_argument("role", choices=Role.all())

    p_rotate = actions.add_parser(
        "rotate-token", help="Replace a user's token and print the new one once")
    p_rotate.add_argument("user_id")

    actions.add_parser("list", help="List users (no tokens)")
    parser.set_defaults(func=cmd_users)


def _run(args: argparse.Namespace) -> Any:
    command = args.users_command
    if command == "add":
        return admin.add_user(args.user_id, role=args.role, display_name=args.name,
                              tags=args.tag, users_path=args.users)
    if command == "remove":
        return admin.remove_user(args.user_id, users_path=args.users)
    if command == "set-role":
        return admin.set_user_role(args.user_id, args.role, users_path=args.users)
    if command == "rotate-token":
        return admin.rotate_user_token(args.user_id, users_path=args.users)
    return admin.list_users(users_path=args.users)


def _text(command: str, result: Any) -> str:
    """The human form of ``result``; a token gets a line of its own."""
    if command == "list":
        rows = [f"{user['user_id']}\t{user['role']}\t{user['display_name']}" for user in result]
        return "\n".join(rows) + ("\n" if rows else "")
    if command == "remove":
        state = "removed" if result["removed"] else "no such user"
        return f"{result['user_id']}: {state}\n"
    if command == "set-role":
        return f"{result['user_id']}: role is now {result['role']}\n"
    return (f"{result['user_id']}: token (shown once, store it now)\n"
            f"{result['token']}\n")


def cmd_users(args: argparse.Namespace) -> int:
    """Run one ``users`` sub-command; 1 when ``remove`` found nobody to remove."""
    result = _run(args)
    if args.json:
        # dict(): an IssuedToken would serialise the same, this just says so.
        payload = dict(result) if isinstance(result, dict) else result
        sys.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2) + "\n")
    else:
        sys.stdout.write(_text(args.users_command, result))
    if args.users_command == "remove" and not result["removed"]:
        return 1
    return 0


def main(argv: Optional[List[str]] = None) -> int:
    """Entry point of ``python -m je_auto_control.utils.rbac``."""
    from je_auto_control.utils.exception.exceptions import AutoControlException
    parser = argparse.ArgumentParser(
        prog="python -m je_auto_control.utils.rbac",
        description="Manage the RBAC user store of the REST API and MCP server.")
    add_users_arguments(parser)
    args = parser.parse_args(argv)
    try:
        return cmd_users(args)
    except (AutoControlException, OSError, ValueError) as error:
        sys.stderr.write(f"error: {error}\n")
        return 1


__all__ = ["add_users_arguments", "cmd_users", "main"]
