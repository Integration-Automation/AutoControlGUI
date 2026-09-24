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
import collections.abc
import dataclasses
import functools
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
#: How far into a nested object the sample builder will follow `properties`.
_MAX_SCHEMA_DEPTH = 4

_STRING_FORMATS: Dict[str, str] = {
    "date-time": "2026-01-02T03:04:05",
    "date": "2026-01-02",
    "time": "03:04:05",
}


def _sample_value(spec: Dict[str, Any], name: str, depth: int = 0) -> Any:
    """Return a value satisfying one JSON-Schema property node.

    A declared ``object`` is built from its own ``properties`` rather than
    left empty: a tool whose ``anchor`` argument names ``kind`` as required
    is describing a payload no client would send as ``{}``, and handing the
    adapter ``{}`` tests the sample, not the wiring. ``depth`` stops a schema
    that describes itself.
    """
    enum = spec.get("enum")
    if isinstance(enum, list) and enum:
        return enum[0]
    kind = spec.get("type", "string")
    if isinstance(kind, list):
        kind = next((entry for entry in kind if entry != "null"), "string")
    if kind == "array":
        item = spec.get("items")
        return [_sample_value(item, name, depth + 1)] if item else []
    if kind == "object":
        properties = spec.get("properties") or {}
        if not properties or depth >= _MAX_SCHEMA_DEPTH:
            return {}
        return {key: _sample_value(sub, key, depth + 1)
                for key, sub in properties.items()}
    if kind == "string":
        return _STRING_FORMATS.get(spec.get("format"), f"value-for-{name}")
    return _SCALARS.get(kind, f"value-for-{name}")


# === Reading a value out of a declared type =================================

_ZEROS: Dict[Any, Callable[[], Any]] = {
    int: lambda: 0, float: lambda: 0.0, bool: lambda: False,
    str: lambda: "", bytes: lambda: b"",
    list: list, dict: dict, set: set, tuple: tuple,
}

# An annotation is free to promise the abstract protocol rather than the
# concrete type, and `Mapping[str, X]` originates at `collections.abc.Mapping`,
# which cannot be instantiated. The emptiest value satisfying each is the
# builtin that registers as it.
_ABSTRACT_CONTAINERS: Dict[Any, Callable[[], Any]] = {
    collections.abc.Mapping: dict, collections.abc.MutableMapping: dict,
    collections.abc.Sequence: list, collections.abc.MutableSequence: list,
    collections.abc.Iterable: list, collections.abc.Iterator: iter([]).__iter__,
    collections.abc.Collection: list,
    collections.abc.Set: set, collections.abc.MutableSet: set,
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
    if origin in _ABSTRACT_CONTAINERS:
        return _ABSTRACT_CONTAINERS[origin]()
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


def _constructed_value(cls: type, seen: FrozenSet[type]) -> Any:
    """Build a real instance of a first-party class from its own ``__init__``.

    This is `_dataclass_value` one level along, and for the same reason: a
    constructor's parameters carry annotations, so "what does calling this
    promise the caller?" stays a question the program can answer. The instance
    is the genuine class, not a double -- its methods run, its ``to_dict()``
    runs, and an adapter that calls one with the wrong arguments still raises.
    That is what keeps "the adapter ran" and "the adapter was checked" from
    coming apart, which a double answering every method would not.

    Only the constructor's *required* parameters are filled: a default is the
    class's own statement of what the caller may leave out.

    Raising :class:`ValueError` leaves the adapter out of the sweep, which is
    the right answer for all three ways this can fail -- a class outside the
    package (the adapter is choosing a backend), a parameter the contract
    never described, and zero values that break an invariant the annotation
    cannot express (``rate must be positive`` for a token bucket, say).
    """
    if cls in seen:
        raise ValueError(f"self-referential constructor on {cls!r}")
    if not getattr(cls, "__module__", "").startswith(_PACKAGE + "."):
        raise ValueError(f"not a first-party class: {cls!r}")
    if _module_picks_a_backend(cls.__module__):
        raise ValueError(f"{cls!r} is defined beside a third-party import")
    try:
        signature = inspect.signature(cls.__init__)
        hints = typing.get_type_hints(cls.__init__)
    except (TypeError, ValueError, NameError) as error:
        raise ValueError(f"unreadable constructor on {cls!r}: {error}") from error
    arguments = {}
    for name, parameter in signature.parameters.items():
        if name == "self" or parameter.default is not parameter.empty:
            continue
        if parameter.kind not in (parameter.POSITIONAL_OR_KEYWORD,
                                  parameter.KEYWORD_ONLY):
            continue
        if name not in hints:
            raise ValueError(f"{cls!r} takes an unannotated {name}")
        arguments[name] = _value_for(hints[name], seen | {cls})
    try:
        return cls(**arguments)
    except Exception as error:  # noqa: BLE001  # reason: any refusal means the contract's zero values do not build one, and the adapter leaves the sweep
        raise ValueError(
            f"{cls!r} refuses its contract's zero values: {error}") from error


@functools.lru_cache(maxsize=None)
def _module_picks_a_backend(module_path: str) -> bool:
    """Return True when the module at ``module_path`` imports a third-party one.

    The sweeps already refuse an adapter that imports a third-party package,
    because what it returns then depends on what is installed on the machine
    rather than on any contract. A real instance moves that question one level
    down: ``S3ArtifactStore`` constructs from its annotations perfectly well
    and then reaches for ``boto3`` the moment a method is called. Same rule,
    same seam, one level along -- and it keeps eight adapters off the
    documented-exception list, where they would all have said "boto3".
    """
    try:
        source = inspect.getsource(sys.modules[module_path])
    except (OSError, TypeError, KeyError):
        return True
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Import):
            if any(not _is_stdlib(alias.name)
                   and not alias.name.startswith(_PACKAGE) for alias in node.names):
                return True
        elif isinstance(node, ast.ImportFrom) and node.module and not node.level:
            root = node.module.split(".")[0]
            if not _is_stdlib(root) and root != _PACKAGE:
                return True
    return False


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
    if isinstance(annotation, type):
        return _constructed_value(annotation, seen)
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
        target = getattr(owner, attribute)
        if isinstance(target, type):
            # A class callee is left alone: the adapter constructs the real
            # object out of the client's own arguments, which is both the
            # strongest form of "run against the declared type" and the only
            # one that keeps the arguments under test. Replacing the class
            # with something returning a prepared instance would throw those
            # arguments away -- and take the class's own constructors with
            # them, since a stub standing in for a class has no `from_dict`.
            # `_constructed_value` below still has to succeed, so a class the
            # contract cannot build stays out of the sweep rather than being
            # run blind.
            try:
                _value_for(target)
            except (ValueError, TypeError, NameError):
                return None
            continue
        try:
            hints = typing.get_type_hints(target)
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
