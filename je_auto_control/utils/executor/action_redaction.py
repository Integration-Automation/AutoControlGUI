"""Mask the arguments of secret-vault commands before an action is logged or recorded.

``AC_secret_init`` / ``AC_secret_unlock`` take the vault passphrase and
``AC_secret_set`` the secret itself. The executor logs every action list it
runs and keys its result record by ``str(action)``, so those values reached
the log file and every caller of the record (REST, MCP, the socket server,
run history) in plain text. The walk is recursive because a secret command
nested in a block (``AC_loop``, ``AC_if``...) is logged with its parent.
"""
from typing import Any

_SECRET_PREFIX = "AC_secret_"
_MASK = "***"


def redact_actions(value: Any) -> Any:
    """Return a copy of ``value`` with every ``AC_secret_*`` argument masked.

    Anything that is not an action keeps its shape; nothing is mutated.
    """
    if isinstance(value, dict):
        return {key: redact_actions(item) for key, item in value.items()}
    if not isinstance(value, list):
        return value
    if value and isinstance(value[0], str) and value[0].startswith(_SECRET_PREFIX):
        return [value[0], *(_mask(argument) for argument in value[1:])]
    return [redact_actions(item) for item in value]


def describe_action(action: Any) -> str:
    """``str()`` of ``action`` with secrets masked, for logs and record keys."""
    return str(redact_actions(action))


def _mask(argument: Any) -> Any:
    if isinstance(argument, dict):
        return {key: _MASK for key in argument}
    if isinstance(argument, list):
        return [_MASK for _ in argument]
    return _MASK
