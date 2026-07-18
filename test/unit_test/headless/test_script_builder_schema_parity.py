"""Parity between the Script Builder schema and the executor's real signatures.

The builder emits ``[command, params]`` and the executor dispatches
``event(**params)``. So every field the schema declares must be a parameter the
dispatch target actually accepts — a renamed or invented field is not a
cosmetic mismatch, it is a guaranteed TypeError the moment the step runs.

Existing tests only assert command *names* exist in the schema, which is why
two such fields shipped: ``AC_click_mouse`` declared ``times`` (click_mouse has
no such parameter, and its default=1 was committed on load, so the most basic
command failed with no user input at all), and ``AC_execute_process`` declared
``program_path`` against ``start_exe(exe_path)``.
"""
import inspect

import pytest

from je_auto_control.gui.script_builder.command_schema import _build_specs
from je_auto_control.utils.executor.action_executor import executor


def _dispatch_targets():
    """Yield (command, spec, signature) for specs with an introspectable target.

    Block commands (AC_try, AC_loop, …) are dispatched as ``handler(executor,
    args)`` rather than ``event(**params)``, so they are not in event_dict and
    are out of scope here.
    """
    for spec in _build_specs():
        target = executor.event_dict.get(spec.command)
        if target is None:
            continue
        try:
            sig = inspect.signature(target)
        except (TypeError, ValueError):      # builtins without signatures
            continue
        yield spec, sig


def _accepts_arbitrary_kwargs(sig) -> bool:
    return any(p.kind == p.VAR_KEYWORD for p in sig.parameters.values())


def test_every_schema_field_is_accepted_by_its_dispatch_target():
    offenders = []
    for spec, sig in _dispatch_targets():
        if _accepts_arbitrary_kwargs(sig):
            continue
        accepted = set(sig.parameters) | set(spec.body_keys or ())
        for field in spec.fields:
            if field.name not in accepted:
                offenders.append(
                    f"{spec.command}: schema field {field.name!r} is not a "
                    f"parameter of {sig}"
                )
    assert offenders == [], (
        "Script Builder would emit params the executor cannot accept:\n  "
        + "\n  ".join(offenders)
    )


@pytest.mark.parametrize("command, field_name", [
    ("AC_click_mouse", "times"),
    ("AC_execute_process", "program_path"),
])
def test_previously_broken_fields_stay_gone(command, field_name):
    """Pin the two specific regressions above by name."""
    spec = next(s for s in _build_specs() if s.command == command)
    assert field_name not in {f.name for f in spec.fields}


def test_the_two_repaired_commands_bind_cleanly():
    """The end-to-end property that actually matters: params bind to the call."""
    click = executor.event_dict["AC_click_mouse"]
    inspect.signature(click).bind(mouse_keycode="mouse_left", x=1, y=2)

    start = executor.event_dict["AC_execute_process"]
    spec = next(s for s in _build_specs() if s.command == "AC_execute_process")
    field = spec.fields[0].name
    inspect.signature(start).bind(**{field: "notepad.exe"})
