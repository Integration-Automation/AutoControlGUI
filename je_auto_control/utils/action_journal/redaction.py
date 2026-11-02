"""Sanitize journal payloads before any bytes reach the append boundary."""
from __future__ import annotations

import json
import math
import re

from je_auto_control.utils.action_journal.events import ActionEvent
from je_auto_control.utils.executor.action_redaction import is_sensitive_argument
from je_auto_control.utils.logging.secret_scope import scrub_secret_text

_REFERENCE = re.compile(r"(?:\$\{secrets\.[A-Za-z_][A-Za-z0-9_.-]*\}|secret://[A-Za-z_][A-Za-z0-9_.-]*)\Z")
_MAX_DEPTH = 32


def _unique_object(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result = dict(pairs)
    if len(result) != len(pairs):
        raise ValueError("duplicate encoded action key")
    return result


def _positionals(value: object) -> list[object] | None:
    if isinstance(value, list) and len(value) == 1 and isinstance(value[0], list):
        return value[0]
    return None


class _Sanitizer:  # pylint: disable=too-few-public-methods  # reason: one traversal owns cycle/redaction state
    """Copy JSON-compatible values, tracking why a payload cannot be replayed."""

    def __init__(self) -> None:
        self.reasons: set[str] = set()
        self._parents: set[int] = set()

    def convert(self, value: object, command: str, *, masked: bool = False, depth: int = 0) -> object:
        """Copy input values while honoring command-specific secret argument names."""
        if masked:
            return self._masked(value)
        if depth > _MAX_DEPTH:
            return self._unsupported("payload_depth_limit")
        if value is None or isinstance(value, (bool, int, str)):
            return self._text(value) if isinstance(value, str) else value
        if isinstance(value, float):
            return value if math.isfinite(value) else self._unsupported("nonfinite_number")
        if isinstance(value, (dict, list, tuple)):
            return self._container(value, command, depth)
        return self._unsupported("unsupported_payload")

    def _text(self, value: str) -> str:
        if _REFERENCE.fullmatch(value):
            return value
        if scrub_secret_text(value) != value:
            self.reasons.add("resolved_secret_redacted")
            return "***"
        return value

    def _masked(self, value: object) -> str:
        if isinstance(value, str) and _REFERENCE.fullmatch(value):
            return value
        self.reasons.add("redacted_input")
        return "***"

    def _unsupported(self, reason: str) -> dict[str, str]:
        self.reasons.add(reason)
        return {"unsupported": reason}

    def _container(self, value: dict[object, object] | list[object] | tuple[object, ...],
                   command: str, depth: int) -> object:
        identity = id(value)
        if identity in self._parents:
            return self._unsupported("cyclic_payload")
        self._parents.add(identity)
        try:
            if isinstance(value, dict):
                return self._mapping(value, command, depth)
            if value and isinstance(value[0], str) and value[0].startswith("AC_"):
                return [value[0], *(self._action_argument(item, value[0], depth + 1) for item in value[1:])]
            return [self.convert(item, command, depth=depth + 1) for item in value]
        finally:
            self._parents.remove(identity)

    def _mapping(self, value: dict[object, object], command: str, depth: int) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                self.reasons.add("unsupported_mapping_key")
                continue
            result[self._text(key)] = self._mapping_item(key, item, command, depth + 1)
        return result

    def _mapping_item(self, key: str, item: object, command: str, depth: int) -> object:
        secret = _all_secret(command)
        positionals = _positionals(item) if secret and key == "args" else None
        if positionals is not None:
            return [self._secret_items(positionals, command, depth)]
        if command == "AC_parallel" and key == "branches" and isinstance(item, str):
            return self._encoded_actions(item, command, depth)
        return self.convert(item, command, masked=secret or is_sensitive_argument(command, key), depth=depth)

    def _action_argument(self, value: object, command: str, depth: int) -> object:
        if not _all_secret(command) or isinstance(value, dict):
            return self.convert(value, command, depth=depth)
        if isinstance(value, (list, tuple)):
            return self._secret_items(value, command, depth)
        return self.convert(value, command, masked=True, depth=depth)

    def _secret_items(self, values: list[object] | tuple[object, ...], command: str, depth: int) -> object:
        if depth > _MAX_DEPTH:
            return self._unsupported("payload_depth_limit")
        return [self.convert(item, command, masked=True, depth=depth + 1) for item in values]

    def _encoded_actions(self, value: str, command: str, depth: int) -> object:
        """Inspect runtime-supported JSON branch strings before persistence, preserving safe source text."""
        if not value.strip():
            return value
        try:
            decoded = json.loads(value, object_pairs_hook=_unique_object)
        except (ValueError, RecursionError):
            return self._unsupported("unsupported_encoded_actions")
        if not isinstance(decoded, list):
            return self._unsupported("unsupported_encoded_actions")
        sanitized = self.convert(decoded, command, depth=depth)
        return value if sanitized == decoded else json.dumps(sanitized, allow_nan=False)


def _all_secret(command: str) -> bool:
    return command.startswith("AC_secret_") or command == "AC_write_secret"


def sanitize_event(event: ActionEvent) -> dict[str, object]:
    """Return a sanitized wire record; opaque outcome/error text is never copied.

    Outcomes may contain resolved secret references or credentials in values or
    dynamic keys. Until a typed safe-outcome contract exists, omit their opaque
    payloads. Keep source parameters' unresolved secret refs.
    """
    sanitizer = _Sanitizer()
    payload = event.to_dict()
    payload["parameters"] = sanitizer.convert(event.parameters, event.command)
    if event.status != "incomplete" and event.outcome_type is None:
        payload["outcome_type"] = _outcome_type(event.outcome)
    if event.outcome is not None:
        payload["outcome"] = "***"
        sanitizer.reasons.add("redacted_outcome")
    if event.error is not None:
        payload["error"] = "***"
        sanitizer.reasons.add("redacted_error")
    payload["non_replayable"] = sorted(set(event.non_replayable) | sanitizer.reasons)
    return payload


def _outcome_type(value: object) -> str:
    """Expose only a fixed type category, never arbitrary payload class names."""
    return {type(None): "none", bool: "boolean", int: "integer", float: "number",
            str: "text", dict: "object", list: "array", tuple: "array"}.get(type(value), "unsupported")
