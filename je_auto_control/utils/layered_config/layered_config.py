"""Ordered, deep-merging configuration resolver with per-key provenance.

``json_patch.merge_patch`` merges exactly two documents and ``config_sync``
resolves by last-write-wins timestamp; ``AssetStore`` is flat-per-environment.
None of them compose an ordered ``defaults < file < env < CLI`` precedence
stack with a deep dict merge, nor report *which layer won each key*. This adds
that 12-factor resolver.

Pure standard library (``copy``); imports no ``PySide6``. Layers are plain
mappings supplied by the caller (the env layer is passed in, never read from
``os.environ`` implicitly), so resolution is deterministic in CI.
"""
import copy
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Tuple


@dataclass(frozen=True)
class SourceTrace:
    """Where a resolved key's value came from."""

    key: str
    value: Any
    layer: Optional[str]


@dataclass
class _Layer:
    name: str
    mapping: Dict[str, Any]
    priority: int
    index: int


def deep_merge(base: Mapping[str, Any],
               override: Mapping[str, Any]) -> Dict[str, Any]:
    """Recursively merge ``override`` onto ``base``; ``override`` wins leaves."""
    result: Dict[str, Any] = dict(base)
    for key, value in override.items():
        current = result.get(key)
        if isinstance(value, Mapping) and isinstance(current, Mapping):
            result[key] = deep_merge(current, value)
        else:
            result[key] = copy.deepcopy(value)
    return result


def _get_path(mapping: Mapping[str, Any],
              parts: List[str]) -> Tuple[bool, Any]:
    current: Any = mapping
    for part in parts:
        if not isinstance(current, Mapping) or part not in current:
            return False, None
        current = current[part]
    return True, current


class LayeredConfig:
    """Compose configuration layers by priority with deep merging."""

    def __init__(self) -> None:
        self._layers: List[_Layer] = []

    def add_layer(self, name: str, mapping: Mapping[str, Any],
                  priority: Optional[int] = None) -> "LayeredConfig":
        """Add a layer; higher ``priority`` wins (default: insertion order)."""
        index = len(self._layers)
        resolved_priority = index if priority is None else priority
        self._layers.append(
            _Layer(name, dict(mapping or {}), resolved_priority, index))
        return self

    def layer_names(self) -> List[str]:
        """The layer names in insertion order."""
        return [layer.name for layer in self._layers]

    def _ascending(self) -> List[_Layer]:
        return sorted(self._layers, key=lambda layer: (layer.priority,
                                                       layer.index))

    def resolve(self) -> Dict[str, Any]:
        """Deep-merge all layers in ascending priority into one config dict."""
        merged: Dict[str, Any] = {}
        for layer in self._ascending():
            merged = deep_merge(merged, layer.mapping)
        return merged

    def get(self, dotted_key: str, default: Any = None) -> Any:
        """Return the resolved value for a dotted key, or ``default``."""
        found, value = _get_path(self.resolve(), dotted_key.split("."))
        return value if found else default

    def explain(self, dotted_key: str) -> SourceTrace:
        """Return the value and the winning layer name for a dotted key."""
        parts = dotted_key.split(".")
        found, value = _get_path(self.resolve(), parts)
        if not found:
            raise KeyError(dotted_key)
        for layer in sorted(self._layers, reverse=True,
                            key=lambda item: (item.priority, item.index)):
            layer_found, _ = _get_path(layer.mapping, parts)
            if layer_found:
                return SourceTrace(dotted_key, value, layer.name)
        return SourceTrace(dotted_key, value, None)
