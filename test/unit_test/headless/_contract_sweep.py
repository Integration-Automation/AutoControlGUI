"""The machinery three sweeps share: what a callee promises, and how to fake it.

``test_adapter_registry_sweep`` (MCP tools and the ``AC_*`` table) and
``test_rest_route_sweep`` (the REST route table) all face the same problem.
Each registry is a few hundred short functions whose whole job is to take a
client's arguments, call one headless function, and hand back something that
survives ``json.dumps``. Calling one for real needs a mouse, a screen or a
network; not calling it at all leaves the wiring checked by nobody.

The way out is the same in every case: **replace the callee with a stub built
from its own return annotation**. That became possible when the typing
contract's exemption list was emptied on 2026-08-22 -- before that, 136 modules
had nothing to read. "What is this adapter entitled to assume?" is now a
question a program can answer, so an adapter can be run against exactly what
its callee promises, no more and no less.

This module holds only that shared half: reading a value out of a declared
type, finding the callee an adapter stands in front of, and installing the
stub. Each sweep keeps its own argument source -- a JSON schema, the Script
Builder's field specs, an HTTP request context -- because that is what stops a
sweep from passing by restating the code it checks.

Nothing here is a test; the file is named so pytest does not collect it.
"""
import ast
import dataclasses
import importlib
import inspect
import json
import sys
import textwrap
import typing
from typing import Any, Callable, Dict, FrozenSet, List, Optional, Tuple

import pytest

_NONE_TYPE = type(None)
_PACKAGE = "je_auto_control"


# === Building a value from a JSON Schema node ================================

_SCALARS: Dict[str, Any] = {
    "integer": 3, "number": 1.5, "boolean": True,
    "array": [], "object": {}, "null": None,
}

# The emptiest value each concrete annotation allows, as factories so two
# adapters never share one mutable container.


# A declared `format` narrows what "string" means, and an adapter that parses
# before delegating enforces it. Without this the sweep hands `ac_rrule_next`
# the generic sample and watches `datetime.fromisoformat` reject it -- which
# says nothing about the adapter and everything about the sample.
_STRING_FORMATS: Dict[str, str] = {
    "date-time": "2026-01-02T03:04:05",
    "date": "2026-01-02",
    "time": "03:04:05",
}


def _sample_value(spec: Dict[str, Any], name: str) -> Any:
    """Return a value satisfying one JSON-Schema property node."""
    enum = spec.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    kind = spec.get("type", "string")
    if isinstance(kind, list):
        kind = next((entry for entry in kind if entry != "null"), "string")
    if kind == "array":
        item = spec.get("items")
        return [_sample_value(item, name)] if item else []
    if kind == "string":
        return _STRING_FORMATS.get(spec.get("format"), f"value-for-{name}")
    return _SCALARS.get(kind, f"value-for-{name}")


# === Reading a value out of a declared type =================================

_ZEROS: Dict[Any, Callable[[], Any]] = {
    int: lambda: 0, float: lambda: 0.0, bool: lambda: False,
    str: lambda: "", bytes: lambda: b"",
    list: list, dict: dict, set: set, tuple: tuple,
}



def _value_for_generic(origin: Any, arguments: Tuple[Any, ...],
                       seen: FrozenSet[type] = frozenset()) -> Any:
    """Build the emptiest value a parameterised annotation allows."""
    if origin is typing.Union:
        return None if _NONE_TYPE in arguments else _value_for(arguments[0],
                                                               seen)
    if origin is tuple:
        if not arguments or arguments[-1] is Ellipsis:
            return ()
        return tuple(_value_for(entry, seen) for entry in arguments)
    if origin in (list, set, frozenset, dict):
        return origin()
    raise ValueError(f"unmodelled container {origin!r}")


def _dataclass_value(cls: type, seen: FrozenSet[type]) -> Any:
    """Build an instance of ``cls`` with every field at its emptiest value.

    A dataclass return annotation is not the end of the contract, it is one
    more level of it: each field carries an annotation of its own, so "what
    may the caller assume?" stays a question the program can answer. The
    instance is real -- the adapter's ``.to_dict()``, its attribute reads and
    its comparisons all run against the declared shape rather than a mock that
    answers everything.

    ``seen`` breaks a cycle of dataclasses that reach each other by a bare
    field; a self-reference through ``Optional`` or a container terminates on
    its own, at None and at the empty container.
    """
    if cls in seen:
        raise ValueError(f"self-referential dataclass field on {cls!r}")
    hints = typing.get_type_hints(cls)
    arguments = {field.name: _value_for(hints.get(field.name, field.type),
                                        seen | {cls})
                 for field in dataclasses.fields(cls) if field.init}
    return cls(**arguments)


def _value_for(annotation: Any, seen: FrozenSet[type] = frozenset()) -> Any:
    """Build the emptiest value a return annotation allows.

    ``Optional[X]`` yields None, containers yield empty containers, scalars
    yield their zero, and a dataclass yields an instance built the same way
    from its own fields. Raises :class:`ValueError` for an annotation this
    cannot model, which leaves the adapter out of the sweep rather than
    testing it against a value its callee never promised.
    """
    if annotation is inspect.Signature.empty:
        raise ValueError("no return annotation")
    if annotation in (None, _NONE_TYPE, typing.Any):
        return None
    origin = typing.get_origin(annotation)
    if origin is not None:
        return _value_for_generic(origin, typing.get_args(annotation), seen)
    if annotation in _ZEROS:
        return _ZEROS[annotation]()
    if isinstance(annotation, type) and dataclasses.is_dataclass(annotation):
        return _dataclass_value(annotation, seen)
    raise ValueError(f"unmodelled return annotation {annotation!r}")


# === Finding the callee an adapter stands in front of =======================

def _adapter_source(adapter: Any) -> Optional[ast.FunctionDef]:
    """Return the parsed definition of ``adapter``, or None if unavailable."""
    try:
        source = textwrap.dedent(inspect.getsource(adapter))
    except (OSError, TypeError):
        return None
    node = ast.parse(source).body[0]
    return node if isinstance(node, ast.FunctionDef) else None


def _is_stdlib(module_path: str) -> bool:
    """Return True for a standard-library module path."""
    return module_path.split(".")[0] in sys.stdlib_module_names


def _is_foreign_import(node: ast.stmt) -> bool:
    """Return True for an import that is neither stdlib nor first-party-from.

    A plain ``import`` of a third-party package means the adapter picks its own
    backend; a relative import means the source could not be resolved to a
    module path. Either way the adapter is out of scope.
    """
    if isinstance(node, ast.Import):
        return any(not _is_stdlib(alias.name) for alias in node.names)
    return not node.module or bool(node.level)


def _first_party_from_imports(imports: List[ast.stmt]
                              ) -> List[Tuple[str, List[str]]]:
    """Return ``(module, names)`` for each from-import inside this package.

    "First party" is the package prefix, not merely "not the stdlib": a
    ``from PySide6... import`` is a backend choice like a plain third-party
    import, and it is the prefix that lets the resolved path be imported below
    without trusting whatever the parsed source happened to say.
    """
    return [(child.module, [alias.name for alias in child.names])
            for child in imports
            if isinstance(child, ast.ImportFrom)
            and child.module.startswith(_PACKAGE + ".")]


def _project_import(adapter: Any) -> Optional[Tuple[str, List[str]]]:
    """Return ``(module, names)`` for the one project callee an adapter imports.

    Standard-library imports are ignored: ``import json`` inside an adapter
    parses a field the visual editor passed as text, and ``import base64``
    encodes what the callee returned -- neither is the callee.
    """
    node = _adapter_source(adapter)
    if node is None:
        return None
    imports = [child for child in ast.walk(node)
               if isinstance(child, (ast.Import, ast.ImportFrom))]
    if any(_is_foreign_import(child) for child in imports):
        return None
    found = _first_party_from_imports(imports)
    return found[0] if len(found) == 1 else None


def _sole_imported_name(node: ast.stmt) -> Optional[Tuple[str, str, str]]:
    """Return ``(module, attribute, local_name)`` for ``from X import y as z``.

    ``X`` has to be inside this package: a delegator standing in front of
    ``json.dumps`` is not wiring under test, and it is the prefix that lets the
    parsed path be imported below without trusting what the source said.
    """
    if not isinstance(node, ast.ImportFrom) or not node.module or node.level:
        return None
    if len(node.names) != 1 or not node.module.startswith(_PACKAGE + "."):
        return None
    alias = node.names[0]
    return node.module, alias.name, alias.asname or alias.name


def _returned_callee(node: ast.stmt) -> Optional[str]:
    """Return the plain name a ``return name(...)`` statement calls."""
    if not isinstance(node, ast.Return):
        return None
    call = node.value
    if not isinstance(call, ast.Call) or not isinstance(call.func, ast.Name):
        return None
    return call.func.id


def _delegated_call(node: ast.FunctionDef) -> Optional[Tuple[str, str]]:
    """Return ``(module, attribute)`` for a body that is import-then-return."""
    body = [statement for statement in node.body
            if not (isinstance(statement, ast.Expr)
                    and isinstance(statement.value, ast.Constant))]
    if len(body) != 2:
        return None
    imported = _sole_imported_name(body[0])
    called = _returned_callee(body[1])
    if imported is None or called is None or called != imported[2]:
        return None
    return imported[0], imported[1]


def _delegation(adapter: Any) -> Optional[Tuple[str, str]]:
    """Return ``(module, attribute)`` when ``adapter`` is a pure delegator.

    A pure delegator's body is exactly one ``from ... import name`` followed by
    ``return name(...)``. Anything else -- a temporary, a branch, a second
    import -- means the adapter does work of its own; the output sweeps cover
    those instead.
    """
    node = _adapter_source(adapter)
    return None if node is None else _delegated_call(node)


def _sole_attribute_on(node: ast.FunctionDef, name: str) -> Optional[str]:
    """Return the one attribute an adapter reaches for on the local ``name``.

    Several dozen adapters import a module-level singleton rather than a
    function -- ``default_observer``, ``default_scheduler``, ``registry`` --
    and call one method on it. That is the same wiring shape one indirection
    along, so the callee is the method and its annotation is the contract.
    Two different methods mean the adapter orchestrates the object instead of
    standing in front of one call, and it stays out of the sweep.
    """
    attributes = {child.attr for child in ast.walk(node)
                  if isinstance(child, ast.Attribute)
                  and isinstance(child.value, ast.Name)
                  and child.value.id == name}
    return attributes.pop() if len(attributes) == 1 else None


def _submodule(module: Any, name: str) -> Any:
    """Return ``module.name`` when the imported name is a submodule.

    ``from ...usb.passthrough import commands`` binds a module, and a package
    only grows that attribute once something has imported it -- which, for a
    lazily-imported adapter, may not have happened yet.
    """
    # Both halves are ``je_auto_control.*`` paths parsed out of this
    # repository's own source; no caller supplies either.
    path = f"{module.__name__}.{name}"
    try:
        return importlib.import_module(path)  # nosemgrep  # reason: prefix-checked at the parse site
    except ImportError:
        return None


def _callee_of(adapter: Any, module: Any, name: str
               ) -> Optional[Tuple[Any, str]]:
    """Return the ``(owner, attribute)`` pair an adapter actually calls."""
    target = getattr(module, name, None)
    if callable(target):
        return module, name
    if target is None:
        target = _submodule(module, name)
    if target is None:
        return None
    node = _adapter_source(adapter)
    attribute = None if node is None else _sole_attribute_on(node, name)
    if attribute is None or not callable(getattr(target, attribute, None)):
        return None
    return target, attribute


def _contract_stubs(adapter: Any) -> Optional[List[Tuple[Any, str, Any]]]:
    """Return ``(owner, attribute, value)`` for each of an adapter's callees.

    Each value comes from that callee's own return annotation, so the adapter
    runs against exactly what the typing contract promises it. The owner is
    the callee's module for a plain function and the singleton itself for a
    method on one.
    """
    found = _project_import(adapter)
    if found is None:
        return None
    module_path, names = found
    try:
        # ``module_path`` is a ``je_auto_control.*`` path parsed out of this
        # repository's own source; no caller supplies it.
        module = importlib.import_module(module_path)  # nosemgrep  # reason: prefix-checked at the parse site
    except ImportError:
        return None
    stubs: List[Tuple[Any, str, Any]] = []
    for name in names:
        callee = _callee_of(adapter, module, name)
        if callee is None:
            return None
        owner, attribute = callee
        try:
            hints = typing.get_type_hints(getattr(owner, attribute))
            stubs.append((owner, attribute,
                          _value_for(hints.get("return",
                                               inspect.Signature.empty))))
        except (ValueError, TypeError, NameError):
            return None
    return stubs


def _install_stubs(monkeypatch: pytest.MonkeyPatch,
                   stubs: List[Tuple[Any, str, Any]]) -> None:
    """Replace each named callee with a stub returning its contract value."""
    for owner, attribute, value in stubs:
        monkeypatch.setattr(owner, attribute, lambda *a, _v=value, **k: _v)


def _is_serialisable(value: Any, native: Tuple[type, ...] = ()) -> bool:
    """Return True when a result can cross the JSON boundary.

    ``native`` names the types a registry encodes itself -- the MCP registry
    turns its own content objects into JSON on the way out, so one of those,
    or a non-empty list of them, is already at the boundary.
    """
    if native and isinstance(value, native):
        return True
    if native and isinstance(value, list) and value and all(
            isinstance(entry, native) for entry in value):
        return True
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return False
    return True


def _install_recorder(monkeypatch: pytest.MonkeyPatch, module_path: str,
                      attribute: str) -> Tuple[Dict[str, Any], Any, Callable]:
    """Replace ``module_path.attribute`` with a call recorder.

    Returns the record dict, the sentinel the recorder returns, and the real
    callable, whose signature says what the recorded arguments are named.
    """
    # ``module_path`` is the ``je_auto_control.*`` path `_sole_imported_name`
    # parsed and prefix-checked; no caller supplies it.
    module = importlib.import_module(module_path)  # nosemgrep  # reason: prefix-checked at the parse site
    original = getattr(module, attribute)
    record: Dict[str, Any] = {}
    sentinel = object()

    def _recorder(*args: Any, **kwargs: Any) -> Any:
        record["args"] = args
        record["kwargs"] = kwargs
        return sentinel

    monkeypatch.setattr(module, attribute, _recorder)
    return record, sentinel, original


# Public names for the sweeps; the underscored ones above stay private to the
# implementation so a future change here does not read as a change there.
value_for = _value_for
adapter_source = _adapter_source
project_import = _project_import
delegation = _delegation
contract_stubs = _contract_stubs
install_stubs = _install_stubs
sample_value = _sample_value
NONE_TYPE = _NONE_TYPE
install_recorder = _install_recorder
is_serialisable = _is_serialisable
is_stdlib = _is_stdlib
