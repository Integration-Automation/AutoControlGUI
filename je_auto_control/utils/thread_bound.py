"""A context variable whose value counts only on the thread that set it.

Several pieces of per-call state are kept in a :class:`contextvars.ContextVar`
and documented as belonging to the calling thread: who a request is served as,
which device a matrix worker drives, which run a heal event belongs to, which
stop token a run answers to. That held because a new thread started with an
empty context -- a property of the interpreter, not of the code. On a
free-threaded build, under ``-X thread_inherit_context=1``, and whenever a
library runs a callable through ``contextvars.copy_context()``, a new thread
starts with a *copy of its creator's* context instead. A scheduler, observer
or hotkey thread first started while a request was being served would then
keep that request's identity (or device, or stop token) for the rest of the
process.

:class:`ThreadBoundVar` records the thread that set a value and returns it on
that thread only; anywhere else it reads as its default, on every build. Code
that hands work to another thread on purpose captures the value first and sets
it again there, as ``AC_parallel`` does for the caller and the stop token.
The run's variable scope (:mod:`je_auto_control.utils.script_vars.execution`)
follows the same rule with its own copy of this logic.
"""
import threading
from contextvars import ContextVar, Token
from typing import Generic, Optional, Tuple, TypeVar

_Value = TypeVar("_Value")

_THREAD = threading.local()


def thread_marker() -> object:
    """An object that identifies the calling thread and nothing else.

    An object, not ``threading.get_ident()``: an ident is reused once its
    thread has ended, and a binding keeps this object alive, so a later thread
    cannot be mistaken for the one that made it.
    """
    marker = getattr(_THREAD, "marker", None)
    if marker is None:
        marker = _THREAD.marker = object()
    return marker


class ThreadBoundVar(Generic[_Value]):
    """A ``ContextVar`` that a thread started later does not inherit.

    ``get`` / ``set`` / ``reset`` as on a ``ContextVar``; ``get`` returns
    ``default`` on any thread other than the one that called ``set``.
    Within one thread it behaves exactly as a ``ContextVar`` does, asyncio
    tasks included.
    """

    def __init__(self, name: str, default: _Value) -> None:
        self._default = default
        self._var: "ContextVar[Optional[Tuple[_Value, object]]]" = ContextVar(name, default=None)

    def get(self) -> _Value:
        """The value set on this thread, else the default."""
        binding = self._var.get()
        if binding is None or binding[1] is not thread_marker():
            return self._default
        return binding[0]

    def set(self, value: _Value) -> "Token[Optional[Tuple[_Value, object]]]":
        """Set ``value`` for this thread; hand the token to :meth:`reset`."""
        return self._var.set((value, thread_marker()))

    def reset(self, token: "Token[Optional[Tuple[_Value, object]]]") -> None:
        """Restore what was set before the :meth:`set` that returned ``token``."""
        self._var.reset(token)


__all__ = ["ThreadBoundVar", "thread_marker"]
