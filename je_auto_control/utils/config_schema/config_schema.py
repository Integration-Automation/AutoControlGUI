"""Typed, schema-validated configuration (a stdlib pydantic-settings analog).

``assets._coerce`` coerces a single value and ``json_schema`` validates JSON
structure, but nothing bound a resolved config dict into a typed object with
required-field enforcement and choice constraints. This validates a mapping
against declared fields, coercing types and reporting actionable errors.

A value comes from the mapping first, then from the field's ``env`` variable,
then from its default (the pydantic-settings order).

Pure standard library (``dataclasses``); imports no ``PySide6``. Validation is a
function of the mapping and the environment it is given (``environ``, default
``os.environ``), so passing ``environ={}`` makes it fully deterministic in CI.
"""
import os
from dataclasses import dataclass, field as dataclass_field
from typing import Any, Dict, List, Mapping, Optional, Sequence

_MISSING = object()


@dataclass
class ConfigField:
    """A single typed configuration field."""

    type: str = "str"
    default: Any = _MISSING
    required: bool = False
    choices: Optional[Sequence[Any]] = None
    env: Optional[str] = None


def _to_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    text = str(value).strip().lower()
    if text in ("true", "1", "yes", "on"):
        return True
    if text in ("false", "0", "no", "off"):
        return False
    raise ValueError(f"not a boolean: {value!r}")


_KINDS = ("str", "int", "float", "bool")


def coerce(value: Any, kind: str) -> Any:
    """Coerce ``value`` to ``kind`` (``str`` / ``int`` / ``float`` / ``bool``).

    ``ValueError`` for an unknown ``kind``, which used to return the value
    unchecked (``"integer"`` passed ``"abc"``), and ``TypeError`` for a list,
    dict or ``None``, which ``str`` turned into ``"[1, 2]"`` / ``"None"``.
    """
    if kind not in _KINDS:
        raise ValueError(f"unknown config type {kind!r}; known: {list(_KINDS)}")
    if value is None or isinstance(value, (list, tuple, dict, set)):
        raise TypeError(f"not a {kind}: {value!r}")
    if kind == "int":
        # int(2.9) is 2, and int(Decimal("2.9")) too: a silent loss.
        if not isinstance(value, (int, str)) and not float(value).is_integer():
            raise ValueError(f"not an integer: {value!r}")
        return int(value)
    if kind == "float":
        return float(value)
    if kind == "bool":
        return _to_bool(value)
    return str(value)


@dataclass
class ConfigSchema:
    """A set of named :class:`ConfigField` definitions."""

    fields: Dict[str, ConfigField] = dataclass_field(default_factory=dict)

    @classmethod
    def from_dict(cls, spec: Mapping[str, Mapping[str, Any]]) -> "ConfigSchema":
        """Build a schema from a ``{name: {type, default, required, ...}}`` spec."""
        for name, raw in spec.items():
            if raw.get("type", "str") not in _KINDS:
                raise ValueError(f"field {name!r}: unknown type {raw.get('type')!r}; known: {list(_KINDS)}")
        fields = {name: ConfigField(
            type=raw.get("type", "str"),
            default=raw.get("default", _MISSING),
            # _to_bool: bool("false") is True, so "false" made a field required.
            required=_to_bool(raw.get("required", False)),
            choices=raw.get("choices"),
            env=raw.get("env")) for name, raw in spec.items()}
        return cls(fields)

    def _resolve_field(self, name: str, definition: ConfigField,
                       mapping: Mapping[str, Any],
                       environ: Mapping[str, str]) -> Any:
        """Return ``(status, payload)``: ``ok``/value, ``error``/dict, ``skip``."""
        raw: Any = _MISSING
        if name in mapping:
            raw = mapping[name]
        elif definition.env and definition.env in environ:
            raw = environ[definition.env]
        if raw is not _MISSING:
            try:
                value = coerce(raw, definition.type)
            except (ValueError, TypeError):
                return "error", {"field": name,
                                 "error": f"cannot coerce to {definition.type}"}
            if definition.choices is not None and value not in definition.choices:
                return "error", {"field": name, "error": "not an allowed choice"}
            return "ok", value
        if definition.default is not _MISSING:
            return "ok", definition.default
        if definition.required:
            return "error", {"field": name, "error": "required"}
        return "skip", None

    def validate(self, mapping: Mapping[str, Any],
                 environ: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
        """Validate ``mapping``; return ``{ok, config, errors}``.

        A field missing from ``mapping`` is read from its ``env`` variable in
        ``environ`` (default ``os.environ``) before falling back to its default.
        """
        env = os.environ if environ is None else environ
        config: Dict[str, Any] = {}
        errors: List[Dict[str, str]] = []
        for name, definition in self.fields.items():
            status, payload = self._resolve_field(name, definition, mapping, env)
            if status == "ok":
                config[name] = payload
            elif status == "error":
                errors.append(payload)
        return {"ok": not errors, "config": config, "errors": errors}


def validate_config(spec: Mapping[str, Mapping[str, Any]],
                    mapping: Mapping[str, Any],
                    environ: Optional[Mapping[str, str]] = None) -> Dict[str, Any]:
    """Validate ``mapping`` against a schema ``spec`` dict in one call."""
    return ConfigSchema.from_dict(spec).validate(mapping, environ)
