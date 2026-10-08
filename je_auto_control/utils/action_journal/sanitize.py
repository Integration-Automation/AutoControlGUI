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
import json
import math
import os
from typing import Any, Callable, Dict, List, Mapping, Sequence, Tuple

from je_auto_control.utils.action_journal.events import MASK, UNSERIALISABLE_KEY
from je_auto_control.utils.executor.action_redaction import redact_actions
from je_auto_control.utils.script_vars.interpolate import _PLACEHOLDER

REASON_MASKED = "secret masked before the journal was written"
REASON_KNOWN = "holds a secret value this run resolved; masked before the journal was written"
#: Shorter values are not masked by exact match: replacing every ``7`` or
#: ``ab`` would shred the text and show where the secret's characters are.
MIN_KNOWN_SECRET_CHARS = 4
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
    notes[path] = REASON_MASKED
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


#: Argument / result keys whose string value names a file a command writes.
_PATH_KEYS = frozenset({
    "file_path", "output_path", "path", "save_path", "screenshot_path",
    "report_path", "artifact_path", "out_path", "output", "destination",
})
#: Result keys whose string value identifies a trace.
_TRACE_KEYS = ("trace_id", "traceparent")
_IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".bmp", ".gif", ".webp")
#: File-system timestamps are coarser than ``time.time()`` (2 s on FAT).
_MTIME_SLACK_S = 2.0


def _written_since(path: str, started_at: float) -> bool:
    """Whether ``path`` is a file last written after ``started_at``."""
    try:
        return os.path.isfile(path) and (
            os.path.getmtime(path) >= started_at - _MTIME_SLACK_S)
    except (OSError, ValueError):
        return False


def _named_paths(value: Any) -> List[Tuple[str, str]]:
    """``(key, path)`` for each path-named string at the top level of ``value``."""
    if not isinstance(value, Mapping):
        return []
    return [(str(key), item) for key, item in value.items()
            if key in _PATH_KEYS and isinstance(item, str) and item]


def artifacts_of_step(params: Any, result: Any, started_at: float
                      ) -> List[Dict[str, str]]:
    """What a finished step left behind, read from its arguments and result.

    A file counts only when a path-named argument or result key names it *and*
    it was written while the step ran, so an input file a command merely read
    is not reported as its product. A trace id in the result is kept as an id.
    Unresolved ``${...}`` references name no file and are skipped.
    """
    found: List[Dict[str, str]] = []
    seen = set()
    for source, path in _named_paths(params) + _named_paths(result):
        if path in seen or not _written_since(path, started_at):
            continue
        seen.add(path)
        kind = "image" if path.lower().endswith(_IMAGE_SUFFIXES) else "file"
        found.append({"kind": kind, "path": os.path.abspath(path), "source": source})
    if isinstance(result, Mapping):
        found.extend({"kind": "trace", "id": result[key], "source": key}
                     for key in _TRACE_KEYS
                     if isinstance(result.get(key), str) and result[key])
    return found


def secret_forms(value: str) -> Tuple[str, ...]:
    """``value`` and the escaped spellings it takes inside a ``repr`` or JSON."""
    forms = {value, repr(value)[1:-1], json.dumps(value)[1:-1],
             json.dumps(value, ensure_ascii=False)[1:-1]}
    return tuple(form for form in forms if form)


def mask_known_text(text: str, forms: Sequence[str]) -> str:
    """``text`` with every exact occurrence of a known secret form masked.

    ``forms`` is longest first, so a secret that contains another is masked
    whole.
    """
    for form in forms:
        if form in text:
            text = text.replace(form, MASK)
    return text


def mask_known_params(params: Any, forms: Sequence[str], notes: Dict[str, str],
                      path: str = "params") -> Any:
    """``params`` with known secret values masked in every string, noting each."""
    if isinstance(params, str):
        masked = mask_known_text(params, forms)
        if masked != params:
            notes[path] = REASON_KNOWN
        return masked
    if isinstance(params, dict):
        return {key: mask_known_params(item, forms, notes, f"{path}.{key}")
                for key, item in params.items()}
    if isinstance(params, list):
        return [mask_known_params(item, forms, notes, f"{path}[{index}]")
                for index, item in enumerate(params)]
    return params
