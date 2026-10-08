"""The variable scope of the current top-level run.

The module-level executor is one object per process, and so was its
:class:`VariableScope`: what one REST, MCP or socket request (or one
``execute_action_with_vars`` call) set stayed there for the next, whose
``${user}`` then resolved to the previous caller's value instead of failing
with ``Unknown variable``.

:func:`execution_scope` opens a fresh scope for one run and makes it the
module executor's scope for as long as the ``with`` block lasts. The binding
is a :class:`contextvars.ContextVar`, so it is per thread (and per asyncio
task): two server threads running at once each see their own scope, and a
thread started inside the block does not inherit it. Code that hands work to
another thread on behalf of the run -- the DAG runner's pool -- captures the
scope first and re-binds it there with :func:`bound_scope`.

Outside any ``execution_scope`` the module executor falls back to its own
process-lifetime scope, which is what plain ``executor.execute_action(...)``
calls and the GUI's Variables tab use.

Things that are a run of their own when called from Python but a nested step
when called from an action list -- a state machine, a plan generated from a
description -- use :func:`run_level_scope`: they join the enclosing run if
there is one and otherwise get a scope that lasts exactly as long as they do.
"""
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Mapping, Optional

from je_auto_control.utils.script_vars.scope import VariableScope

_ACTIVE: ContextVar[Optional[VariableScope]] = ContextVar(
    "je_auto_control_execution_scope", default=None)


def current_scope() -> Optional[VariableScope]:
    """The scope bound by the enclosing :func:`execution_scope`, else ``None``."""
    return _ACTIVE.get()


@contextmanager
def bound_scope(scope: VariableScope) -> Iterator[VariableScope]:
    """Make an existing ``scope`` the current run's on this thread; restore on exit."""
    token = _ACTIVE.set(scope)
    try:
        yield scope
    finally:
        _ACTIVE.reset(token)


@contextmanager
def run_level_scope() -> Iterator[VariableScope]:
    """Join the enclosing run's scope, or open a fresh one for the block.

    Inside an :func:`execution_scope` (or a scope re-bound with
    :func:`bound_scope`) the block is a step of that run and shares its
    variables, as any nested action list does. With no run in progress the
    block is the run: it gets an empty scope that is dropped when it ends, so
    what it sets never reaches the process scope or the next caller.
    """
    active = _ACTIVE.get()
    if active is not None:
        yield active
        return
    with execution_scope() as scope:
        yield scope


@contextmanager
def execution_scope(variables: Optional[Mapping[str, Any]] = None
                    ) -> Iterator[VariableScope]:
    """Run the block in a fresh variable scope seeded with ``variables``.

    Everything the module executor runs inside the block -- including nested
    bodies, macros and ``AC_set_var`` -- reads and writes this scope, and it
    is dropped when the block ends: the previous binding (an enclosing
    ``execution_scope``, or the process scope) is restored even on error.
    A ``variables`` mapping with an invalid name raises ``ValueError`` before
    anything is bound.
    """
    scope = VariableScope()
    if variables:
        scope.update_many(variables)
    with bound_scope(scope):
        yield scope
