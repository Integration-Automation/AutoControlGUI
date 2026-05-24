"""Transport-agnostic slash-command router for the chat-ops layer.

Plug commands in by registering handlers; feed inbound chat lines in
through :meth:`CommandRouter.dispatch` and get a :class:`CommandResult`
back (or None when the message wasn't a registered command). The
Slack / Discord / Webhook transports build on this without each
re-implementing parsing, argument quoting, or unknown-command
handling.
"""
from __future__ import annotations

import shlex
import threading
from dataclasses import asdict, dataclass, field
from typing import Any, Callable, Dict, List, Optional


# Built-in commands always available even when the operator only
# registers their own scripts. Keep this set small — listing scripts
# and reporting status is universal enough to be the bot's "?" reply.
_BUILTIN_LIST = "list"
_BUILTIN_HELP = "help"


class ChatOpsError(ValueError):
    """Raised for malformed commands the user can fix in their next message."""


@dataclass(frozen=True)
class CommandResult:
    """One reply the bot will post back to the chat channel."""

    text: str
    artifact_path: Optional[str] = None
    succeeded: bool = True
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


CommandHandler = Callable[[List[str], Dict[str, Any]], CommandResult]


@dataclass(frozen=True)
class CommandSpec:
    """Registered handler: name, callable, help text, RBAC tag."""

    name: str
    handler: CommandHandler
    description: str = ""
    required_role: Optional[str] = None


class CommandRouter:
    """Slash-prefix command parser + dispatcher.

    Default prefix is ``/``; configure another in the constructor when
    integrating with a chat platform that reserves ``/``.
    """

    def __init__(self, *, prefix: str = "/") -> None:
        if not prefix:
            raise ChatOpsError("prefix must be a non-empty string")
        self._prefix = prefix
        self._commands: Dict[str, CommandSpec] = {}
        self._lock = threading.Lock()
        self._register_builtins()

    @property
    def prefix(self) -> str:
        return self._prefix

    # --- registration --------------------------------------------

    def register(self, name: str, handler: CommandHandler,
                 *, description: str = "",
                 required_role: Optional[str] = None) -> CommandSpec:
        """Register ``name`` → ``handler``. Overwrites prior registration."""
        clean = _validate_name(name)
        spec = CommandSpec(
            name=clean, handler=handler,
            description=description, required_role=required_role,
        )
        with self._lock:
            self._commands[clean] = spec
        return spec

    def unregister(self, name: str) -> bool:
        with self._lock:
            return self._commands.pop(_validate_name(name), None) is not None

    def list_commands(self) -> List[CommandSpec]:
        with self._lock:
            return sorted(self._commands.values(), key=lambda c: c.name)

    # --- dispatch -------------------------------------------------

    def parse(self, message: str) -> Optional[List[str]]:
        """Return tokenised argv if ``message`` starts with the prefix, else None."""
        if not isinstance(message, str):
            return None
        text = message.strip()
        if not text.startswith(self._prefix):
            return None
        body = text[len(self._prefix):].strip()
        if not body:
            return None
        try:
            return shlex.split(body)
        except ValueError as error:
            raise ChatOpsError(f"could not parse command: {error}") from error

    def dispatch(self, message: str,
                 *, context: Optional[Dict[str, Any]] = None,
                 ) -> Optional[CommandResult]:
        """Route a chat message to a handler. Returns None when not a command."""
        argv = self.parse(message)
        if argv is None:
            return None
        return self._dispatch_argv(argv, context or {})

    def _dispatch_argv(self, argv: List[str],
                       context: Dict[str, Any]) -> CommandResult:
        name, rest = argv[0], argv[1:]
        with self._lock:
            spec = self._commands.get(name)
        if spec is None:
            return _unknown_command_reply(name, self.list_commands())
        if not _role_authorised(spec, context):
            return CommandResult(
                text=(f"command {name!r} requires role "
                      f"{spec.required_role!r}; you do not have it."),
                succeeded=False,
            )
        try:
            return spec.handler(rest, context)
        except ChatOpsError as error:
            return CommandResult(text=f"{name}: {error}", succeeded=False)
        except (RuntimeError, OSError, ValueError) as error:
            return CommandResult(
                text=f"{name} failed: {type(error).__name__}: {error}",
                succeeded=False,
            )

    # --- builtins -------------------------------------------------

    def _register_builtins(self) -> None:
        self.register(
            _BUILTIN_HELP, self._cmd_help,
            description="Show the list of registered commands.",
        )
        self.register(
            _BUILTIN_LIST, self._cmd_help,
            description="Alias of /help.",
        )

    def _cmd_help(self, _argv: List[str],
                  _context: Dict[str, Any]) -> CommandResult:
        rows = [
            f"  {self._prefix}{spec.name}\t{spec.description or '(no description)'}"
            for spec in self.list_commands()
        ]
        text = "Available commands:\n" + "\n".join(rows)
        return CommandResult(text=text)


# --- internals ----------------------------------------------------

def _validate_name(name: str) -> str:
    if not isinstance(name, str):
        raise ChatOpsError("command name must be a string")
    clean = name.strip().lower()
    if not clean:
        raise ChatOpsError("command name must be non-empty")
    if any(char.isspace() for char in clean):
        raise ChatOpsError("command name must not contain whitespace")
    return clean


def _role_authorised(spec: CommandSpec,
                     context: Dict[str, Any]) -> bool:
    if spec.required_role is None:
        return True
    user_role = context.get("user_role")
    if not isinstance(user_role, str):
        return False
    return user_role.strip().lower() == spec.required_role.strip().lower()


def _unknown_command_reply(name: str,
                            known: List[CommandSpec]) -> CommandResult:
    suggestions = [s.name for s in known if s.name.startswith(name[:1])]
    hint = ""
    if suggestions:
        hint = f" Did you mean: {', '.join(sorted(suggestions))}?"
    return CommandResult(
        text=f"unknown command {name!r}.{hint}",
        succeeded=False,
    )


__all__ = [
    "ChatOpsError", "CommandHandler", "CommandResult", "CommandRouter",
    "CommandSpec",
]
