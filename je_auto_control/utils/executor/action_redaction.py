"""Mask secret arguments before an action is logged or recorded.

``AC_secret_init`` / ``AC_secret_unlock`` take the vault passphrase and
``AC_secret_set`` the secret itself; every argument of those is masked. Any
other command has the arguments masked whose name says they are secret
(``password``, ``token``...), and the signing, encryption and JWT commands
their ``key`` -- elsewhere ``key`` is a keyboard key. The executor logs every
action list it runs and keys its result record by ``str(action)``, so these
values reached the log file and every caller of the record (REST, MCP, the
socket server, run history) in plain text. The walk is recursive because a
command nested in a block (``AC_loop``, ``AC_if``...) is logged with its
parent.
"""
from typing import Any, FrozenSet

_VAULT_COMMAND_PREFIX = "AC_secret_"
_MASK = "***"

#: Argument names that hold a secret whatever the command.
SENSITIVE_ARGUMENT_NAMES: FrozenSet[str] = frozenset({
    "password", "passphrase", "token", "secret", "api_key", "private_key",
    "client_secret", "authorization", "access_token", "refresh_token",
    # The credential headers, which arrive as the keys of a ``headers`` dict.
    "proxy-authorization", "cookie", "set-cookie", "x-api-key", "x-auth-token",
})

#: Commands whose ``url`` argument is itself a credential: a Slack, Discord or
#: Teams webhook URL is the key that posts to the channel.
_URL_SECRET_COMMANDS: FrozenSet[str] = frozenset({"AC_notify_webhook"})

#: Commands whose ``key`` argument is a cryptographic key.
_KEYED_COMMANDS: FrozenSet[str] = frozenset({
    "AC_sign_action_file", "AC_verify_action_file", "AC_encrypt_action_file",
    "AC_decrypt_action_file", "AC_jwt_encode", "AC_jwt_decode",
})


def redact_actions(value: Any) -> Any:
    """Return a copy of ``value`` with every secret argument masked.

    Anything that is not an action keeps its shape; nothing is mutated.
    """
    if isinstance(value, dict):
        # By name at every depth: only top-level arguments were masked, so
        # {"smtp": {"password": ...}} and {"headers": {"Authorization": ...}}
        # reached the log and the run record.
        return {key: _MASK if str(key).lower() in SENSITIVE_ARGUMENT_NAMES else redact_actions(item)
                for key, item in value.items()}
    if not isinstance(value, list):
        return value
    if value and isinstance(value[0], str) and value[0].startswith("AC_"):
        return [value[0], *(_redact_argument(value[0], argument) for argument in value[1:])]
    return [redact_actions(item) for item in value]


def is_sensitive_argument(command: str, name: str) -> bool:
    """Whether argument ``name`` of ``command`` holds a secret."""
    lowered = str(name).lower()
    return lowered in SENSITIVE_ARGUMENT_NAMES or (
        lowered == "key" and command in _KEYED_COMMANDS) or (
        lowered == "url" and command in _URL_SECRET_COMMANDS)


def _redact_argument(command: str, argument: Any) -> Any:
    if command.startswith(_VAULT_COMMAND_PREFIX):
        return _mask(argument)
    if isinstance(argument, dict):
        return {name: _MASK if is_sensitive_argument(command, name) else redact_actions(item)
                for name, item in argument.items()}
    return redact_actions(argument)


def describe_action(action: Any) -> str:
    """``str()`` of ``action`` with secrets masked, for logs and record keys."""
    return str(redact_actions(action))


def _mask(argument: Any) -> Any:
    if isinstance(argument, dict):
        return {key: _MASK for key in argument}
    if isinstance(argument, list):
        return [_MASK for _ in argument]
    return _MASK
