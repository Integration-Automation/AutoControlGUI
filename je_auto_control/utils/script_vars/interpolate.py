"""Substitute ``${var}`` placeholders in action JSON before execution.

A placeholder that exactly matches ``${name}`` is replaced by the raw value
(preserving type — int stays int). A placeholder embedded in a larger string
falls back to string substitution, e.g. ``"x=${x}"`` → ``"x=42"``.

Unknown variables raise ``ValueError`` so mistakes fail fast rather than
silently executing with wrong values.
"""
import json
import re
from pathlib import Path
from typing import Any, Mapping, MutableMapping

_PLACEHOLDER = re.compile(r"\$\{([A-Za-z_]\w*)\}")


def interpolate_value(value: Any, variables: Mapping[str, Any]) -> Any:
    """Recursively interpolate placeholders inside ``value``."""
    if isinstance(value, str):
        return _interpolate_string(value, variables)
    if isinstance(value, list):
        return [interpolate_value(item, variables) for item in value]
    if isinstance(value, dict):
        return {k: interpolate_value(v, variables) for k, v in value.items()}
    return value


def interpolate_actions(actions: list, variables: Mapping[str, Any]) -> list:
    """Return a new action list with placeholders substituted."""
    return interpolate_value(actions, variables)


def _interpolate_string(text: str, variables: Mapping[str, Any]) -> Any:
    exact = _PLACEHOLDER.fullmatch(text)
    if exact is not None:
        return _lookup(exact.group(1), variables)
    return _PLACEHOLDER.sub(
        lambda m: str(_lookup(m.group(1), variables)), text
    )


def _lookup(name: str, variables: Mapping[str, Any]) -> Any:
    if name not in variables:
        raise ValueError(f"Unknown variable: ${{{name}}}")
    return variables[name]


def load_vars_from_json(path: str,
                        into: MutableMapping[str, Any] = None
                        ) -> MutableMapping[str, Any]:
    """Load a flat JSON object as a variable bag."""
    with open(Path(path), encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object of variables")
    if into is None:
        into = {}
    for key, value in data.items():
        if not isinstance(key, str):
            raise ValueError(f"{path}: variable names must be strings")
        into[key] = value
    return into
