"""Typed, schema-validated configuration (a stdlib pydantic-settings analog).

``assets._coerce`` coerces a single value and ``json_schema`` validates JSON
structure, but nothing bound a resolved config dict into a typed object with
required-field enforcement and choice constraints. This validates a mapping
against declared fields, coercing types and reporting actionable errors.

Pure standard library (``dataclasses``); imports no ``PySide6``. Validation is a
pure function (mapping in, report out), so it is fully deterministic in CI.
"""
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


def coerce(value: Any, kind: str) -> Any:
    """Coerce ``value`` to ``kind`` (``str`` / ``int`` / ``float`` / ``bool``)."""
    if kind == "int":
        return int(value)
    if kind == "float":
        return float(value)
    if kind == "bool":
        return _to_bool(value)
    if kind == "str":
        return str(value)
    return value


@dataclass
class ConfigSchema:
    """A set of named :class:`ConfigField` definitions."""

    fields: Dict[str, ConfigField] = dataclass_field(default_factory=dict)

    @classmethod
    def from_dict(cls, spec: Mapping[str, Mapping[str, Any]]) -> "ConfigSchema":
        """Build a schema from a ``{name: {type, default, required, ...}}`` spec."""
        fields = {name: ConfigField(
            type=raw.get("type", "str"),
            default=raw.get("default", _MISSING),
            required=bool(raw.get("required", False)),
            choices=raw.get("choices"),
            env=raw.get("env")) for name, raw in spec.items()}
        return cls(fields)

    def _resolve_field(self, name: str, definition: ConfigField,
                       mapping: Mapping[str, Any]) -> Any:
        """Return ``(status, payload)``: ``ok``/value, ``error``/dict, ``skip``."""
        if name in mapping:
            try:
                value = coerce(mapping[name], definition.type)
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

    def validate(self, mapping: Mapping[str, Any]) -> Dict[str, Any]:
        """Validate ``mapping``; return ``{ok, config, errors}``."""
        config: Dict[str, Any] = {}
        errors: List[Dict[str, str]] = []
        for name, definition in self.fields.items():
            status, payload = self._resolve_field(name, definition, mapping)
            if status == "ok":
                config[name] = payload
            elif status == "error":
                errors.append(payload)
        return {"ok": not errors, "config": config, "errors": errors}


def validate_config(spec: Mapping[str, Mapping[str, Any]],
                    mapping: Mapping[str, Any]) -> Dict[str, Any]:
    """Validate ``mapping`` against a schema ``spec`` dict in one call."""
    return ConfigSchema.from_dict(spec).validate(mapping)
