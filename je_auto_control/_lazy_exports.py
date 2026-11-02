"""Resolve facade bindings without changing the exported objects."""
from importlib import import_module
from typing import Mapping, NamedTuple


class AttributeBinding(NamedTuple):
    """One original attribute, including its public alias."""

    owner: str
    attribute: str


class ModuleBinding(NamedTuple):
    """An export whose value is the real module itself."""

    owner: str


ExportBinding = AttributeBinding | ModuleBinding


def resolve_export(namespace: dict[str, object], bindings: Mapping[str, ExportBinding], name: str) -> object:
    """Import one owner and retain an explicit assignment made during import."""
    binding = bindings.get(name)
    if binding is None:
        raise AttributeError(f"module {namespace['__name__']!r} has no attribute {name!r}")
    owner = import_module(binding.owner)
    value = getattr(owner, binding.attribute) if isinstance(binding, AttributeBinding) else owner
    return namespace.setdefault(name, value)
