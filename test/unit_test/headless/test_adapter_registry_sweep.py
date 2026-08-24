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
import inspect
import json
import threading
import typing
from typing import Any, Callable, Dict, List

import pytest

from headless._contract_sweep import (
    NONE_TYPE, contract_stubs, delegation, install_recorder, install_stubs,
    is_serialisable, sample_value,
)

from je_auto_control.gui.script_builder.command_schema import (
    FieldSpec, FieldType, _build_specs,
)
from je_auto_control.utils.executor.action_executor import executor
from je_auto_control.utils.mcp_server.tools import (
    MCPContent, MCPTool, build_default_tool_registry,
)


# MCP adapters that need more than their callee's return annotation promises.
# Each is a real coupling the type contract does not express, not a stub defect:
_NEEDS_MORE_THAN_THE_CONTRACT = {
    # Uses the return value as a context manager; the annotation is untyped.
    "ac_list_monitors",
    # Indexes a key out of a Dict[str, Any] the annotation cannot promise.
    "ac_tween_drag",
    "ac_voice_dispatch",
    # Its anchor's `kind` selects a locator backend, and the first value the
    # enum offers is `image` -- so the call leaves the adapter and goes into
    # OpenCV template matching against a real screen.
    "ac_anchor_click",
    # Needs a viewer that registered earlier. The registry it is handed is
    # real and empty, and refusing an unknown viewer is what it is for.
    "ac_presence_update_cursor",
    "ac_presence_set_role",
    # Needs an interaction recorded into the cassette first; a fresh one
    # misses by design.
    "ac_http_replay",
}


@pytest.fixture(autouse=True)
def _in_a_directory_of_its_own(tmp_path, monkeypatch):
    """Run every sweep case in an empty directory.

    An adapter whose callee is a class builds the real object out of the
    client's own arguments, and some of those objects are stores: a
    checkpoint store handed the sample file path creates a SQLite database
    where it stands. In the repository that leaves files behind and makes one
    case depend on whether another ran first; here each case gets a directory
    nobody else can see.
    """
    monkeypatch.chdir(tmp_path)


@pytest.fixture(autouse=True)
def _leaves_no_background_work_behind():
    """No sweep case may outlive itself in a thread.

    Running the genuine object rather than a stand-in means an adapter whose
    job is to *start* something really starts it: `AC_usb_watch_start` leaves
    a hotplug poller running, and on Windows that poller shells out to
    PowerShell every interval. Any later test that patches `subprocess.run`
    process-wide and reads the first call it recorded then sees the poller's
    argv instead of its own -- which is how `test_wayland_libei` failed on one
    square of the matrix and nowhere else.

    The sweep stops what it starts, below; this is the guard that says so, and
    it names the next adapter to grow a thread instead of letting it become
    somebody else's flake.
    """
    before = {thread.ident for thread in threading.enumerate()}
    yield
    left = [thread.name for thread in threading.enumerate()
            if thread.ident not in before and thread.is_alive()]
    assert not left, f"the case left these threads running: {left}"


def _stop_whatever_it_started(name: str, dispatch) -> None:
    """Run the `_stop` sibling of a `_start` adapter, where there is one.

    Every `_start` in either registry has one, which is what makes this a
    convention rather than a special case -- and running it is coverage of
    the stop adapter too, from the only state where stopping means anything.
    """
    if not name.endswith("_start"):
        return
    dispatch(name[:-len("_start")] + "_stop")


# === Reading a value out of a declared type =================================

# Sample values by JSON-Schema type. Strings carry their property name so a
# swapped pair of same-typed arguments shows as a mismatch, not as two equal
# placeholders.
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
        if NONE_TYPE in arguments:
            return None
        return _annotated_value(arguments[0], name)
    if origin in (list, tuple, set):
        return []
    if origin is dict:
        return {}
    scalars = {int: 3, float: 1.5, bool: True, str: f"value-for-{name}"}
    return scalars.get(annotation)


# === The MCP tool registry ==================================================

def _tool_arguments(schema: Dict[str, Any],
                    required_only: bool) -> Dict[str, Any]:
    """Build a call payload from a tool's input schema."""
    properties = schema.get("properties") or {}
    names = (schema.get("required") or []) if required_only else list(properties)
    return {name: sample_value(properties[name], name)
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


def _invoke_by_name(name: str) -> None:
    """Call one tool by name with what its own schema declares, if it exists."""
    for tool in REGISTRY:
        if tool.name == name:
            tool.invoke(_tool_arguments(tool.input_schema, required_only=False))
            return


REGISTRY = build_default_tool_registry(read_only=False, aliases=False)
_TOOLS = _unique_by_handler(REGISTRY)
DELEGATING = [(tool, *delegation(tool.handler)) for tool in _TOOLS
              if delegation(tool.handler) is not None]
STUBBABLE = [tool for tool in _TOOLS
             if contract_stubs(tool.handler) is not None]


@pytest.mark.parametrize("case", DELEGATING, ids=lambda case: case[0].name)
def test_required_arguments_alone_make_the_tool_callable(case, monkeypatch):
    """A client sending exactly the schema's required properties succeeds."""
    tool, module_path, attribute = case
    record, sentinel, _original = install_recorder(
        monkeypatch, module_path, attribute)
    payload = _tool_arguments(tool.input_schema, required_only=True)
    assert tool.invoke(payload) is sentinel
    assert record, f"{tool.name} never reached {module_path}.{attribute}"


@pytest.mark.parametrize("case", DELEGATING, ids=lambda case: case[0].name)
def test_declared_arguments_reach_the_delegate_unchanged(case, monkeypatch):
    """Every property the schema declares is accepted and forwarded intact."""
    tool, module_path, attribute = case
    record, sentinel, original = install_recorder(
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
    install_stubs(monkeypatch, contract_stubs(tool.handler))
    result = tool.invoke(_tool_arguments(tool.input_schema,
                                         required_only=False))
    _stop_whatever_it_started(tool.name, lambda stop: _invoke_by_name(stop))
    assert is_serialisable(result, (MCPContent,)), (
        f"{tool.name} returned {type(result).__name__}, which json.dumps "
        "cannot encode")


def test_the_documented_exceptions_are_still_needed(monkeypatch):
    """A named exception that starts passing is stale and must be removed."""
    still_failing = set()
    for tool in STUBBABLE:
        if tool.name not in _NEEDS_MORE_THAN_THE_CONTRACT:
            continue
        stubs = contract_stubs(tool.handler)
        with monkeypatch.context() as patch:
            install_stubs(patch, stubs)
            try:
                result = tool.invoke(
                    _tool_arguments(tool.input_schema, required_only=False))
            except Exception:  # noqa: BLE001  # reason: any failure keeps it
                still_failing.add(tool.name)
            else:
                if not is_serialisable(result, (MCPContent,)):
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
    if contract_stubs(adapter) is None:
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
    install_stubs(monkeypatch, contract_stubs(adapter))
    payload = _command_arguments(command, adapter)
    record = executor.execute_action([[command, payload]])
    _stop_whatever_it_started(command, lambda stop: executor.execute_action(
        [[stop, _command_arguments(stop, executor.event_dict[stop])]]))
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
