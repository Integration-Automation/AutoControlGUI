"""The two adapter registries, swept for what only a real call would reveal.

``utils/mcp_server/tools/_handlers.py`` and the ``AC_*`` dispatch table in
``utils/executor/action_executor.py`` are the same layer twice: about a thousand
short functions whose whole job is to take a client's arguments, call one
headless function, and hand back something that survives ``json.dumps``. Each is
two to eight lines, so the per-feature tests that touch them are testing the
feature; the adapter itself -- the wiring -- is checked by nobody, and it fails
only when a client calls it.

The technique both sweeps share is what makes them possible at all: **the callee
is replaced by a stub built from its own return annotation**. Before the typing
contract was emptied of exemptions on 2026-08-22 that could not be done -- 136
modules had nothing to read. Now "what is this adapter entitled to assume?" is a
question a program can answer, so an adapter can be run against exactly what its
callee promises, no more and no less, with no mouse, no display and no network
in the picture. An adapter that needs *more* than the promise shows up here
rather than in front of a client.

Arguments never come from the adapter's source. The MCP sweep takes them from
the tool's declared JSON schema in ``_factories.py``; the executor sweep takes
them from the Script Builder's ``command_schema.py`` where a command has an
entry, and from the adapter's own parameter annotations where it does not. Both
sources are maintained in different files from the adapters, so neither sweep
can pass by restating the code it checks.

What this catches: a required property with no matching parameter, a declared
property the adapter rejects, a mandatory parameter the schema never fills, a
swapped or dropped argument, a "pass-through" that is not one, a command name
the table does not resolve, and a return value the JSON boundary cannot encode.

Out of scope by design: an adapter that reaches into two project modules
(it composes them rather than normalising one), and one that imports a
third-party module (it picks its own backend, so what it returns depends on the
machine -- the opposite of what a sweep can assert).
"""
import ast
import importlib
import inspect
import json
import sys
import textwrap
import typing
from typing import Any, Callable, Dict, List, Optional, Tuple

import pytest

from je_auto_control.gui.script_builder.command_schema import (
    FieldSpec, FieldType, _build_specs,
)
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.mcp_server.tools import (
    MCPContent, MCPTool, build_default_tool_registry,
)

_NONE_TYPE = type(None)

# MCP adapters that need more than their callee's return annotation promises.
# Each is a real coupling the type contract does not express, not a stub defect:
_NEEDS_MORE_THAN_THE_CONTRACT = {
    # Uses the return value as a context manager; the annotation is untyped.
    "ac_list_monitors",
    # Its single import is a class, so there is no return annotation to build.
    "ac_anchor_click",
    # Indexes a key out of a Dict[str, Any] the annotation cannot promise.
    "ac_tween_drag",
}


# === Reading a value out of a declared type =================================

# Sample values by JSON-Schema type. Strings carry their property name so a
# swapped pair of same-typed arguments shows as a mismatch, not as two equal
# placeholders.
_SCALARS: Dict[str, Any] = {
    "integer": 3, "number": 1.5, "boolean": True,
    "array": [], "object": {}, "null": None,
}

# One sample per Script Builder field type; a field's own default wins where it
# has one, so enums and paths stay inside the values the editor would offer.
_FIELD_SAMPLES: Dict[FieldType, Callable[[FieldSpec], Any]] = {
    FieldType.STRING: lambda field: f"value-for-{field.name}",
    FieldType.INT: lambda field: 3,
    FieldType.FLOAT: lambda field: 1.5,
    FieldType.BOOL: lambda field: True,
    FieldType.ENUM: lambda field: field.choices[0] if field.choices else "",
    FieldType.FILE_PATH: lambda field: "sample.txt",
    FieldType.RGB: lambda field: [1, 2, 3],
}

# The emptiest value each concrete annotation allows, as factories so two
# adapters never share one mutable container.
_ZEROS: Dict[Any, Callable[[], Any]] = {
    int: lambda: 0, float: lambda: 0.0, bool: lambda: False,
    str: lambda: "", bytes: lambda: b"",
    list: list, dict: dict, set: set, tuple: tuple,
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
        return f"value-for-{name}"
    return _SCALARS.get(kind, f"value-for-{name}")


def _field_value(field: FieldSpec) -> Any:
    """Return a value the visual editor could have produced for one field."""
    if field.default is not None and field.field_type is not FieldType.RGB:
        return field.default
    return _FIELD_SAMPLES[field.field_type](field)


def _annotated_value(annotation: Any, name: str) -> Any:
    """Return an argument value for a parameter with no schema field.

    Structured parameters (the editor leaves those to its raw JSON view) get an
    empty container; scalars get a sample of their annotated type. ``Any`` and
    unannotated parameters get None, which is why a command carrying one is only
    swept when the schema names it.
    """
    origin = typing.get_origin(annotation)
    arguments = typing.get_args(annotation)
    if origin is typing.Union:
        if _NONE_TYPE in arguments:
            return None
        return _annotated_value(arguments[0], name)
    if origin in (list, tuple, set):
        return []
    if origin is dict:
        return {}
    scalars = {int: 3, float: 1.5, bool: True, str: f"value-for-{name}"}
    return scalars.get(annotation)


def _value_for_generic(origin: Any, arguments: Tuple[Any, ...]) -> Any:
    """Build the emptiest value a parameterised annotation allows."""
    if origin is typing.Union:
        return None if _NONE_TYPE in arguments else _value_for(arguments[0])
    if origin is tuple:
        if not arguments or arguments[-1] is Ellipsis:
            return ()
        return tuple(_value_for(entry) for entry in arguments)
    if origin in (list, set, frozenset, dict):
        return origin()
    raise ValueError(f"unmodelled container {origin!r}")


def _value_for(annotation: Any) -> Any:
    """Build the emptiest value a return annotation allows.

    ``Optional[X]`` yields None, containers yield empty containers, scalars
    yield their zero. Raises :class:`ValueError` for an annotation this cannot
    model, which leaves the adapter out of the sweep rather than testing it
    against a value its callee never promised.
    """
    if annotation is inspect.Signature.empty:
        raise ValueError("no return annotation")
    if annotation in (None, _NONE_TYPE, typing.Any):
        return None
    origin = typing.get_origin(annotation)
    if origin is not None:
        return _value_for_generic(origin, typing.get_args(annotation))
    if annotation in _ZEROS:
        return _ZEROS[annotation]()
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
    """Return ``(module, names)`` for each from-import outside the stdlib."""
    return [(child.module, [alias.name for alias in child.names])
            for child in imports
            if isinstance(child, ast.ImportFrom)
            and not _is_stdlib(child.module)]


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
    """Return ``(module, attribute, local_name)`` for ``from X import y as z``."""
    if not isinstance(node, ast.ImportFrom) or not node.module or node.level:
        return None
    if len(node.names) != 1:
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


def _contract_stubs(adapter: Any) -> Optional[Tuple[Any, Dict[str, Any]]]:
    """Return ``(module, {name: value})`` stubbing one adapter's callees.

    Each value comes from that callee's own return annotation, so the adapter
    runs against exactly what the typing contract promises it.
    """
    found = _project_import(adapter)
    if found is None:
        return None
    module_path, names = found
    try:
        module = importlib.import_module(module_path)
    except ImportError:
        return None
    values: Dict[str, Any] = {}
    for name in names:
        target = getattr(module, name, None)
        if not callable(target):
            return None
        try:
            hints = typing.get_type_hints(target)
            values[name] = _value_for(hints.get("return",
                                                inspect.Signature.empty))
        except (ValueError, TypeError, NameError):
            return None
    return module, values


def _install_stubs(monkeypatch: pytest.MonkeyPatch, module: Any,
                   values: Dict[str, Any]) -> None:
    """Replace each named callee with a stub returning its contract value."""
    for name, value in values.items():
        monkeypatch.setattr(module, name, lambda *a, _v=value, **k: _v)


def _is_serialisable(value: Any) -> bool:
    """Return True when a result can cross the JSON boundary."""
    if isinstance(value, MCPContent):
        return True
    if isinstance(value, list) and value and all(
            isinstance(entry, MCPContent) for entry in value):
        return True
    try:
        json.dumps(value)
    except (TypeError, ValueError):
        return False
    return True


# === The MCP tool registry ==================================================

def _tool_arguments(schema: Dict[str, Any],
                    required_only: bool) -> Dict[str, Any]:
    """Build a call payload from a tool's input schema."""
    properties = schema.get("properties") or {}
    names = (schema.get("required") or []) if required_only else list(properties)
    return {name: _sample_value(properties[name], name)
            for name in names if name in properties}


def _unique_by_handler(tools: List[MCPTool]) -> List[MCPTool]:
    """Drop the short aliases, which are copies pointing at the same handler."""
    seen = set()
    unique = []
    for tool in tools:
        if tool.handler in seen:
            continue
        seen.add(tool.handler)
        unique.append(tool)
    return unique


REGISTRY = build_default_tool_registry(read_only=False, aliases=False)
_TOOLS = _unique_by_handler(REGISTRY)
DELEGATING = [(tool, *_delegation(tool.handler)) for tool in _TOOLS
              if _delegation(tool.handler) is not None]
STUBBABLE = [tool for tool in _TOOLS
             if _contract_stubs(tool.handler) is not None]


def _install_recorder(monkeypatch: pytest.MonkeyPatch, module_path: str,
                      attribute: str) -> Tuple[Dict[str, Any], Any, Callable]:
    """Replace ``module_path.attribute`` with a call recorder.

    Returns the record dict, the sentinel the recorder returns, and the real
    callable, whose signature says what the recorded arguments are named.
    """
    module = importlib.import_module(module_path)
    original = getattr(module, attribute)
    record: Dict[str, Any] = {}
    sentinel = object()

    def _recorder(*args: Any, **kwargs: Any) -> Any:
        record["args"] = args
        record["kwargs"] = kwargs
        return sentinel

    monkeypatch.setattr(module, attribute, _recorder)
    return record, sentinel, original


@pytest.mark.parametrize("case", DELEGATING, ids=lambda case: case[0].name)
def test_required_arguments_alone_make_the_tool_callable(case, monkeypatch):
    """A client sending exactly the schema's required properties succeeds."""
    tool, module_path, attribute = case
    record, sentinel, _original = _install_recorder(
        monkeypatch, module_path, attribute)
    payload = _tool_arguments(tool.input_schema, required_only=True)
    assert tool.invoke(payload) is sentinel
    assert record, f"{tool.name} never reached {module_path}.{attribute}"


@pytest.mark.parametrize("case", DELEGATING, ids=lambda case: case[0].name)
def test_declared_arguments_reach_the_delegate_unchanged(case, monkeypatch):
    """Every property the schema declares is accepted and forwarded intact."""
    tool, module_path, attribute = case
    record, sentinel, original = _install_recorder(
        monkeypatch, module_path, attribute)
    payload = _tool_arguments(tool.input_schema, required_only=False)
    assert tool.invoke(payload) is sentinel
    try:
        bound = inspect.signature(original).bind(
            *record["args"], **record["kwargs"]).arguments
    except TypeError as error:  # the real delegate would have rejected it
        pytest.fail(f"{tool.name} calls {attribute} wrongly: {error}")
    for name, value in payload.items():
        if name in bound:
            assert bound[name] == value, (
                f"{tool.name} sent {value!r} but {attribute} bound "
                f"{bound[name]!r} to {name}")
        else:
            # The delegate renames the parameter; the value must still arrive.
            assert any(seen == value for seen in bound.values()), (
                f"{tool.name} dropped {name}={value!r} on the way to "
                f"{module_path}.{attribute}")


@pytest.mark.parametrize("tool", STUBBABLE, ids=lambda tool: tool.name)
def test_tool_result_survives_json(tool, monkeypatch):
    """An adapter fed exactly what its callee promises returns JSON."""
    if tool.name in _NEEDS_MORE_THAN_THE_CONTRACT:
        pytest.skip("documented: needs more than the callee's annotation")
    module, values = _contract_stubs(tool.handler)
    _install_stubs(monkeypatch, module, values)
    result = tool.invoke(_tool_arguments(tool.input_schema,
                                         required_only=False))
    assert _is_serialisable(result), (
        f"{tool.name} returned {type(result).__name__}, which json.dumps "
        "cannot encode")


def test_the_documented_exceptions_are_still_needed(monkeypatch):
    """A named exception that starts passing is stale and must be removed."""
    still_failing = set()
    for tool in STUBBABLE:
        if tool.name not in _NEEDS_MORE_THAN_THE_CONTRACT:
            continue
        module, values = _contract_stubs(tool.handler)
        with monkeypatch.context() as patch:
            _install_stubs(patch, module, values)
            try:
                result = tool.invoke(
                    _tool_arguments(tool.input_schema, required_only=False))
            except Exception:  # noqa: BLE001  # reason: any failure keeps it
                still_failing.add(tool.name)
            else:
                if not _is_serialisable(result):
                    still_failing.add(tool.name)
    assert still_failing == _NEEDS_MORE_THAN_THE_CONTRACT, (
        "these entries now pass and should be deleted: "
        f"{sorted(_NEEDS_MORE_THAN_THE_CONTRACT - still_failing)}")


# === The AC_* dispatch table ================================================

SPECS = _build_specs()
SPECS_BY_COMMAND = {spec.command: spec for spec in SPECS}


def _mandatory_parameters(adapter: Any) -> Dict[str, Any]:
    """Return the parameters a caller must supply, mapped to their annotation."""
    parameters = inspect.signature(adapter).parameters
    return {name: parameter.annotation
            for name, parameter in parameters.items()
            if parameter.default is parameter.empty
            and parameter.kind in (parameter.POSITIONAL_OR_KEYWORD,
                                   parameter.KEYWORD_ONLY)}


def _command_arguments(command: str, adapter: Any) -> Dict[str, Any]:
    """Build the action payload a client would send for one command."""
    spec = SPECS_BY_COMMAND.get(command)
    payload = ({field.name: _field_value(field) for field in spec.fields}
               if spec is not None else {})
    for name, annotation in _mandatory_parameters(adapter).items():
        if name not in payload:
            payload[name] = _annotated_value(annotation, name)
    return payload


def _is_drivable(command: str, adapter: Any) -> bool:
    """Return True when the sweep can supply every argument a command needs.

    Without a schema entry, a mandatory parameter annotated ``Any`` (or not
    annotated at all) leaves nothing to build a value from, and passing None
    would test the adapter's None-handling rather than its wiring.
    """
    if _contract_stubs(adapter) is None:
        return False
    if any(parameter.kind is parameter.VAR_KEYWORD
           for parameter in inspect.signature(adapter).parameters.values()):
        return False
    if command in SPECS_BY_COMMAND:
        return True
    return all(annotation not in (inspect.Parameter.empty, typing.Any)
               for annotation in _mandatory_parameters(adapter).values())


SWEEPABLE = sorted(command for command, adapter in executor.event_dict.items()
                   if _is_drivable(command, adapter))


@pytest.mark.parametrize("command", SWEEPABLE)
def test_command_dispatches_and_records_json(command, monkeypatch):
    """The command runs from a client's arguments and lands JSON in the record."""
    adapter = executor.event_dict[command]
    module, values = _contract_stubs(adapter)
    _install_stubs(monkeypatch, module, values)
    payload = _command_arguments(command, adapter)
    record = executor.execute_action([[command, payload]])
    assert record, f"{command} produced no execution record"
    try:
        json.dumps(record)
    except (TypeError, ValueError) as error:
        pytest.fail(f"{command} put an unencodable value in the record: "
                    f"{error}")


def test_every_schema_field_names_a_parameter_of_its_command():
    """The editor cannot offer a field the executor would reject."""
    unknown = []
    for spec in SPECS:
        adapter = executor.event_dict.get(spec.command)
        if adapter is None:
            continue
        parameters = inspect.signature(adapter).parameters
        if any(parameter.kind is parameter.VAR_KEYWORD
               for parameter in parameters.values()):
            continue
        unknown.extend(f"{spec.command}.{field.name}" for field in spec.fields
                       if field.name not in parameters)
    assert not unknown, f"fields no adapter accepts: {unknown}"


def test_every_schema_command_is_in_the_dispatch_table():
    """A command the editor can emit must be a command the executor knows."""
    known = executor.known_commands()
    missing = [spec.command for spec in SPECS if spec.command not in known]
    assert not missing, f"schema commands the executor cannot run: {missing}"


def _unfielded_mandatory(spec: Any, adapter: Any) -> List[str]:
    """Return this command's mandatory scalar parameters that have no field."""
    parameters = inspect.signature(adapter).parameters
    if any(parameter.kind is parameter.VAR_KEYWORD
           for parameter in parameters.values()):
        return []
    fielded = {field.name for field in spec.fields}
    gaps = []
    for name, annotation in _mandatory_parameters(adapter).items():
        if name in fielded:
            continue
        structured = (typing.get_origin(annotation) is not None
                      or annotation is typing.Any)
        if not structured:
            gaps.append(f"{spec.command}.{name}: {annotation}")
    return gaps


def test_unfielded_mandatory_parameters_are_all_structured():
    """A mandatory parameter with no field must be one no field could express.

    The editor's field types are all scalars, so list- and dict-shaped
    parameters are filled from its raw JSON view instead. A mandatory *scalar*
    with no field is different: it means the editor emits an action that raises
    ``TypeError`` the first time it runs.
    """
    scalar_gaps = []
    for spec in SPECS:
        adapter = executor.event_dict.get(spec.command)
        if adapter is not None:
            scalar_gaps.extend(_unfielded_mandatory(spec, adapter))
    assert not scalar_gaps, (
        f"mandatory scalar parameters the editor never fills: {scalar_gaps}")


# === The sweeps have to keep finding things =================================

def test_both_registries_are_swept_in_bulk():
    """Guard the discovery itself: a broken matcher would sweep nothing."""
    tools = len(REGISTRY)
    assert len(DELEGATING) > tools // 3, (
        f"only {len(DELEGATING)} of {tools} tools matched the pure-delegation "
        "shape -- the AST matcher has probably drifted")
    assert len(STUBBABLE) > tools // 2, (
        f"only {len(STUBBABLE)} of {tools} tools could be stubbed from their "
        "callee's annotations -- the typing contract or the matcher has drifted")
    commands = len(executor.event_dict)
    assert len(SWEEPABLE) > commands // 5, (
        f"only {len(SWEEPABLE)} of {commands} commands matched the "
        "single-project-import shape -- the matcher has probably drifted")
