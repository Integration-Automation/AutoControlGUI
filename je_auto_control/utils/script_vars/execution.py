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

"Does not inherit" is enforced here, not left to the interpreter. A new thread
starts with an empty context on the builds this was written on, but with a
*copy of its creator's* context on a free-threaded build, under
``-X thread_inherit_context=1``, and whenever a library runs a callable through
``contextvars.copy_context()``. A scheduler, observer or hotkey thread started
by one request would then keep that request's scope for the rest of the
process: reading variables of a run that ended long ago and writing into a
scope nobody else can see. So a binding records the thread that made it and
:func:`current_scope` honours it on that thread only; anywhere else it reads
as "no run in progress" and the process scope applies, on every build.

Outside any ``execution_scope`` the module executor falls back to its own
process-lifetime scope, which is what plain ``executor.execute_action(...)``
calls and the GUI's Variables tab use.

Things that are a run of their own when called from Python but a nested step
when called from an action list -- a state machine, a plan generated from a
description -- use :func:`run_level_scope`: they join the enclosing run if
there is one and otherwise get a scope that lasts exactly as long as they do.
"""
import threading
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Any, Iterator, Mapping, NamedTuple, Optional

from je_auto_control.utils.script_vars.scope import VariableScope


class _Binding(NamedTuple):
    """A scope and the thread it was bound on."""

    scope: VariableScope
    #: The binding thread's marker (see :func:`_thread_marker`). An object, not
    #: ``threading.get_ident()``: an ident is reused once its thread has ended,
    #: and the binding keeps this object alive, so it cannot be mistaken.
    owner: object


_ACTIVE: ContextVar[Optional[_Binding]] = ContextVar(
    "je_auto_control_execution_scope", default=None)
_THREAD = threading.local()


def _thread_marker() -> object:
    """An object that identifies the calling thread and nothing else."""
    marker = getattr(_THREAD, "marker", None)
    if marker is None:
        marker = _THREAD.marker = object()
    return marker


def current_scope() -> Optional[VariableScope]:
    """The scope bound by the enclosing :func:`execution_scope`, else ``None``.

    ``None`` also on a thread that only inherited a copy of another thread's
    context: a binding counts on the thread that made it.
    """
    binding = _ACTIVE.get()
    if binding is None or binding.owner is not _thread_marker():
        return None
    return binding.scope


@contextmanager
def bound_scope(scope: VariableScope) -> Iterator[VariableScope]:
    """Make an existing ``scope`` the current run's on this thread; restore on exit."""
    token = _ACTIVE.set(_Binding(scope, _thread_marker()))
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
    active = current_scope()
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
