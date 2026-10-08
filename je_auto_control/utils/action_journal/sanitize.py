"""Make an action's arguments safe to persist, before they are persisted.

The journal is a file other tools read, so a secret has to be gone *before*
the line is written -- masking a line already on disk leaves the secret in
the file's history. :func:`sanitise_params` reuses the executor's own
redaction (``utils/executor/action_redaction``) and adds what a journal needs
on top of a log line:

* a value that is only a reference (``${secrets.NAME}``, ``${var}``) is kept:
  it names a secret without containing one, and it is what makes the step
  replayable;
* every masked value and every value JSON cannot hold is listed with the
  reason it cannot be replayed, instead of being silently wrong.

Pure standard library; imports no ``PySide6``.
"""
import math
from typing import Any, Callable, Dict, Mapping, Tuple

from je_auto_control.utils.action_journal.events import MASK, UNSERIALISABLE_KEY
from je_auto_control.utils.executor.action_redaction import redact_actions
from je_auto_control.utils.script_vars.interpolate import _PLACEHOLDER

REASON_SECRET = "secret masked before the journal was written"  # nosec B105  # reason: explanatory text, not a credential
_REASON_TYPE = "not JSON-serialisable ({})"
_REASON_FLOAT = "non-finite number ({})"
_SCALARS = (str, int, bool, type(None))


def _plain(value: Any, path: str, notes: Dict[str, str]) -> Any:
    """``value`` as JSON-ready data; what JSON cannot hold becomes a marker."""
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        notes[path] = _REASON_FLOAT.format(value)
        return {UNSERIALISABLE_KEY: "float"}
    if isinstance(value, _SCALARS):
        return value
    if isinstance(value, Mapping):
        return {str(key): _plain(item, f"{path}.{key}", notes)
                for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item, f"{path}[{index}]", notes)
                for index, item in enumerate(value)]
    # The type name only: a repr can hold a secret and cannot be parsed back.
    kind = type(value).__qualname__
    notes[path] = _REASON_TYPE.format(kind)
    return {UNSERIALISABLE_KEY: kind}


def _is_reference(value: Any) -> bool:
    return isinstance(value, str) and _PLACEHOLDER.fullmatch(value) is not None


def _settle_masked(plain: Any, path: str, notes: Dict[str, str]) -> Any:
    if _is_reference(plain):
        return plain
    notes[path] = REASON_SECRET
    return MASK


def _settle(plain: Any, masked: Any, path: str, notes: Dict[str, str]) -> Any:
    """Keep references the redaction masked; note everything else it masked."""
    if masked == MASK and plain != MASK:
        return _settle_masked(plain, path, notes)
    if isinstance(plain, dict) and isinstance(masked, dict):
        return {key: _settle(item, masked.get(key, MASK), f"{path}.{key}", notes)
                for key, item in plain.items()}
    if isinstance(plain, list) and isinstance(masked, list) and len(plain) == len(masked):
        return [_settle(item, masked[index], f"{path}[{index}]", notes)
                for index, item in enumerate(plain)]
    return masked


def sanitise_params(command: str, params: Any) -> Tuple[Any, Dict[str, str]]:
    """``(safe_params, unreplayable)`` for one action's argument value.

    ``unreplayable`` maps a path such as ``params.body[0][1].password`` to why
    the value there is not what the action was given.
    """
    notes: Dict[str, str] = {}
    plain = _plain(params, "params", notes)
    masked = redact_actions([command, plain])[1]
    return _settle(plain, masked, "params", notes), notes


def replace_unreplayable(params: Any, unreplayable: Mapping[str, str],
                         substitute: Callable[[str], Any], path: str = "params") -> Any:
    """A copy of ``params`` with each unreplayable value swapped for ``substitute(path)``."""
    if path in unreplayable:
        return substitute(path)
    if isinstance(params, dict):
        return {key: replace_unreplayable(item, unreplayable, substitute, f"{path}.{key}")
                for key, item in params.items()}
    if isinstance(params, list):
        return [replace_unreplayable(item, unreplayable, substitute, f"{path}[{index}]")
                for index, item in enumerate(params)]
    return params


def describe_outcome(value: Any) -> Dict[str, Any]:
    """What an action returned, by type and size -- never its text.

    A returned string may be a secret read from the vault, the clipboard or
    the screen, so only numbers and booleans are stored as values.
    """
    kind = type(value).__qualname__
    if value is None or isinstance(value, bool):
        return {"type": kind, "value": value}
    if isinstance(value, int) or (isinstance(value, float) and math.isfinite(value)):
        return {"type": kind, "value": value}
    if isinstance(value, (str, bytes, list, tuple, dict, set, frozenset)):
        return {"type": kind, "size": len(value)}
    return {"type": kind}
