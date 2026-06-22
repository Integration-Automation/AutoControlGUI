"""Classify JSON-Schema changes as backward / forward / full compatible.

We can *validate against* a JSON Schema (``json_schema``) and *generate* one
(``action_lint/schema``) but could not answer "will a consumer on the old schema
still read data written under the new schema?" — i.e. classify changes
(added-required field, removed field, narrowed type, removed enum value) under
the Confluent/Avro backward / forward / full rules. This adds that classifier.

Scope: the object-schema subset ``json_schema`` understands —
``properties`` / ``required`` / ``type`` / ``enum``. Pure standard library;
imports no ``PySide6``. Each function is pure (two schema dicts in, report out),
so it is fully deterministic in CI.
"""
from dataclasses import dataclass
from typing import Any, Dict, FrozenSet, List, Mapping

_BACKWARD = frozenset({"backward"})
_FORWARD = frozenset({"forward"})
_BOTH = frozenset({"backward", "forward"})


@dataclass(frozen=True)
class SchemaChange:
    """One classified change between two schemas."""

    path: str
    kind: str
    breaks: FrozenSet[str]

    def to_dict(self) -> Dict[str, Any]:
        """Return a JSON-friendly view of the change."""
        return {"path": self.path, "kind": self.kind,
                "breaks": sorted(self.breaks)}


def _properties(schema: Mapping[str, Any]) -> Dict[str, Any]:
    return schema.get("properties", {}) or {}


def _required(schema: Mapping[str, Any]) -> set:
    return set(schema.get("required", []) or [])


def _types(schema: Mapping[str, Any]) -> FrozenSet[str]:
    kind = schema.get("type")
    if kind is None:
        return frozenset()                       # absent ⇒ "any"
    return frozenset([kind]) if isinstance(kind, str) else frozenset(kind)


def _is_subset(narrow: FrozenSet[str], wide: FrozenSet[str]) -> bool:
    if not wide:                                 # wide is "any" ⇒ everything fits
        return True
    if not narrow:                               # "any" is not a subset of specific
        return False
    return narrow <= wide


def _diff_requiredness(name: str, old_req: set,
                       new_req: set) -> List[SchemaChange]:
    if name in new_req and name not in old_req:
        return [SchemaChange(name, "field_made_required", _BACKWARD)]
    if name in old_req and name not in new_req:
        return [SchemaChange(name, "field_made_optional", _FORWARD)]
    return []


def _diff_type(name: str, old_prop: Mapping[str, Any],
               new_prop: Mapping[str, Any]) -> List[SchemaChange]:
    old_types, new_types = _types(old_prop), _types(new_prop)
    if old_types == new_types:
        return []
    if _is_subset(new_types, old_types):
        return [SchemaChange(name, "type_narrowed", _BACKWARD)]
    if _is_subset(old_types, new_types):
        return [SchemaChange(name, "type_widened", _FORWARD)]
    return [SchemaChange(name, "type_changed", _BOTH)]


def _diff_enum(name: str, old_prop: Mapping[str, Any],
               new_prop: Mapping[str, Any]) -> List[SchemaChange]:
    old_enum, new_enum = old_prop.get("enum"), new_prop.get("enum")
    if old_enum is None and new_enum is None:
        return []
    if old_enum is None:
        return [SchemaChange(name, "enum_added", _BACKWARD)]
    if new_enum is None:
        return [SchemaChange(name, "enum_removed", _FORWARD)]
    changes: List[SchemaChange] = []
    if set(old_enum) - set(new_enum):
        changes.append(SchemaChange(name, "enum_value_removed", _BACKWARD))
    if set(new_enum) - set(old_enum):
        changes.append(SchemaChange(name, "enum_value_added", _FORWARD))
    return changes


def _diff_property(name: str, old_prop: Mapping[str, Any],
                   new_prop: Mapping[str, Any], old_req: set,
                   new_req: set) -> List[SchemaChange]:
    changes = _diff_requiredness(name, old_req, new_req)
    changes.extend(_diff_type(name, old_prop, new_prop))
    changes.extend(_diff_enum(name, old_prop, new_prop))
    return changes


def diff_schemas(old: Mapping[str, Any],
                 new: Mapping[str, Any]) -> List[SchemaChange]:
    """Classify the changes from ``old`` to ``new`` as a list of changes."""
    old_props, new_props = _properties(old), _properties(new)
    old_req, new_req = _required(old), _required(new)
    changes: List[SchemaChange] = []
    for name in new_props:
        if name not in old_props:
            breaks = _BACKWARD if name in new_req else frozenset()
            changes.append(SchemaChange(name, "field_added", breaks))
    for name in old_props:
        if name not in new_props:
            breaks = _FORWARD if name in old_req else frozenset()
            changes.append(SchemaChange(name, "field_removed", breaks))
    for name in old_props.keys() & new_props.keys():
        changes.extend(_diff_property(name, old_props[name], new_props[name],
                                      old_req, new_req))
    return changes


def check_compatibility(old: Mapping[str, Any], new: Mapping[str, Any],
                        mode: str = "backward") -> Dict[str, Any]:
    """Report compatibility for ``mode`` (``backward`` / ``forward`` / ``full``)."""
    modes = _BOTH if mode == "full" else frozenset({mode})
    changes = diff_schemas(old, new)
    breaking = [change for change in changes if change.breaks & modes]
    return {"compatible": not breaking, "mode": mode,
            "changes": [change.to_dict() for change in changes],
            "breaking": [change.to_dict() for change in breaking]}


def is_backward_compatible(old: Mapping[str, Any],
                           new: Mapping[str, Any]) -> bool:
    """Whether ``new`` can read data written under ``old``."""
    return check_compatibility(old, new, "backward")["compatible"]


def is_forward_compatible(old: Mapping[str, Any],
                          new: Mapping[str, Any]) -> bool:
    """Whether ``old`` can read data written under ``new``."""
    return check_compatibility(old, new, "forward")["compatible"]


def is_full_compatible(old: Mapping[str, Any],
                       new: Mapping[str, Any]) -> bool:
    """Whether the change is both backward and forward compatible."""
    return check_compatibility(old, new, "full")["compatible"]
