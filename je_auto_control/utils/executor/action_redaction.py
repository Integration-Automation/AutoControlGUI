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
import json
from typing import Any, FrozenSet

_VAULT_COMMAND_PREFIX = "AC_secret_"
_MASK = "***"

#: Argument names that hold a secret whatever the command.
SENSITIVE_ARGUMENT_NAMES: FrozenSet[str] = frozenset({
    "password", "passphrase", "token", "secret", "api_key", "private_key",
    "client_secret", "authorization", "access_token", "refresh_token", "shared_secret",
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
        return _redact_action(value)
    return [redact_actions(item) for item in value]


def _redact_action(action: list) -> list:
    if _confidential_write(action):
        return [action[0], *(_mask(argument) for argument in action[1:])]
    return [action[0], *(_redact_argument(action[0], argument) for argument in action[1:])]


def _confidential_write(action: list) -> bool:
    if action[0] == 'AC_write_secret':
        return True
    if action[0] != 'AC_write' or len(action) < 2:
        return False
    arguments = action[1]
    if isinstance(arguments, dict):
        return bool(arguments.get('secret', False))
    if isinstance(arguments, list):
        return len(arguments) > 2 and bool(arguments[2])
    return False


def is_sensitive_argument(command: str, name: str) -> bool:
    """Whether argument ``name`` of ``command`` holds a secret."""
    lowered = str(name).lower()
    if command == 'AC_mobile_type_text' and lowered == 'text':
        return True
    return lowered in SENSITIVE_ARGUMENT_NAMES or (
        lowered == "key" and command in _KEYED_COMMANDS) or (
        lowered == "url" and command in _URL_SECRET_COMMANDS)


def _redact_argument(command: str, argument: Any) -> Any:
    if command.startswith(_VAULT_COMMAND_PREFIX):
        return _mask(argument)
    if isinstance(argument, dict):
        return {name: _redact_named_argument(command, name, item)
                for name, item in argument.items()}
    if command == 'AC_execute_journaled' and isinstance(argument, list) and argument:
        return [_redact_serialized_actions(argument[0]), *(redact_actions(item) for item in argument[1:])]
    return _redact_positional(command, argument)


def _redact_positional(command: str, argument: Any) -> Any:
    if command == 'AC_mobile_type_text' and isinstance(argument, list) and argument:
        return [_MASK, *(redact_actions(item) for item in argument[1:])]
    return redact_actions(argument)


def _redact_named_argument(command: str, name: str, value: Any) -> Any:
    if is_sensitive_argument(command, name):
        return _MASK
    if command == 'AC_execute_journaled' and name == 'actions':
        return _redact_serialized_actions(value)
    return redact_actions(value)


def _redact_serialized_actions(value: Any) -> Any:
    if not isinstance(value, str):
        return redact_actions(value)
    try:
        return json.dumps(redact_actions(json.loads(value)), ensure_ascii=False)
    except json.JSONDecodeError:
        return _MASK


def describe_action(action: Any) -> str:
    """``str()`` of ``action`` with secrets masked, for logs and record keys."""
    return str(redact_actions(action))


def _mask(argument: Any) -> Any:
    if isinstance(argument, dict):
        return {key: _MASK for key in argument}
    if isinstance(argument, list):
        return [_MASK for _ in argument]
    return _MASK
