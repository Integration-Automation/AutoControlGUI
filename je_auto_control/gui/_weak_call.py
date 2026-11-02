"""Callbacks for a background task that do not keep the tab alive.

A task's handle, and the relay under it, are descendants of the tab that
started the work. A connection from one of them to ``functools.partial(self.x,
...)``, to a lambda or to a nested function holds the tab's Python wrapper for
as long as the handle exists -- so the last reference to a parentless tab could
be the one its own grandchild held, and was released from inside that
grandchild's destructor. Qt then destroyed the tab in the middle of destroying
its child and the process aborted, with no traceback.

:class:`WeakCall` keeps a bound method as a weak reference plus its leading
arguments, and :func:`weak_slot` makes the plain callable a signal is
connected to. A ``functools.partial`` of a bound method is taken apart the same
way, so a helper that receives ``on_done`` from a tab can simply wrap what it
was given. Anything else (a module-level function, a signal's ``emit``, a
method of a child widget) is held as it is: write the callback as a method and
pass its arguments, never as a lambda or a nested function that closes over
the tab -- ``test_gui_weak_callbacks.py`` fails a new one.
"""
import functools
import weakref
from typing import Any, Callable, Dict, Optional, Tuple

Callback = Optional[Callable[..., object]]


def _is_bound_method(callback: object) -> bool:
    return getattr(callback, "__self__", None) is not None and hasattr(callback, "__func__")


class WeakCall:
    """``callback(*args, *outcome)`` that does not keep a bound method's object alive."""

    def __init__(self, callback: Callback, args: Tuple[Any, ...] = ()) -> None:
        keywords: Dict[str, Any] = {}
        while isinstance(callback, functools.partial):
            args = tuple(callback.args) + tuple(args)
            keywords = {**callback.keywords, **keywords}
            callback = callback.func
        self._args = args
        self._keywords = keywords
        self._strong: Callback = None
        self._weak: Optional[weakref.WeakMethod[Callable[..., Any]]] = None
        if _is_bound_method(callback):
            self._weak = weakref.WeakMethod(callback)   # type: ignore[arg-type]
        else:
            self._strong = callback

    def __call__(self, *outcome: object) -> bool:
        """Run the callback if there is one and its object still exists; return whether it ran."""
        callback = self._weak() if self._weak is not None else self._strong
        if not callable(callback):
            return False
        callback(*self._args, *outcome, **self._keywords)
        return True


def _run(call: WeakCall, *outcome: object) -> None:
    """GUI thread: deliver one outcome to whoever is still there."""
    call(*outcome)


def weak_slot(callback: Callback, *args: Any) -> Callable[..., None]:
    """Return what to connect a task's signal to so that ``callback(*args, value)`` runs weakly.

    The result is a partial of a module-level function: it holds the
    :class:`WeakCall`, never the object ``callback`` is bound to.
    """
    return functools.partial(_run, WeakCall(callback, args))


__all__ = ["Callback", "WeakCall", "weak_slot"]
