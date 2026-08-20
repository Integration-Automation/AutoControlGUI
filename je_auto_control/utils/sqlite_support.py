"""Access to the optional standard-library ``sqlite3`` module.

CPython links ``sqlite3`` against a system library that is not always shipped
with the interpreter: FreeBSD packages it separately as
``databases/py-sqlite3``, and minimal builds leave it out entirely. Ten
AutoControl subsystems keep their state in SQLite and every one of them is
reachable from ``import je_auto_control``, so importing ``sqlite3`` at module
scope made the whole package unimportable on such a Python -- mouse and
keyboard included, neither of which touches a database. Going through here
instead defers the failure to the first call that actually opens one.
"""
from typing import Tuple, Type

from je_auto_control.utils.exception.exceptions import \
    AutoControlUnsupportedOperationException

try:
    import sqlite3 as _sqlite3

    #: For ``except`` clauses in the callers that contain database failures.
    #: The classes are named here rather than at each site so the tuple can be
    #: empty when there is no ``sqlite3`` -- nothing can raise them then, so an
    #: empty tuple catches exactly the right amount: nothing.
    SQLITE_ERRORS: Tuple[Type[BaseException], ...] = (_sqlite3.Error,)
    SQLITE_OPERATIONAL_ERRORS: Tuple[Type[BaseException], ...] = (
        _sqlite3.OperationalError,
    )
except ImportError:  # reason: interpreters built without the sqlite3 extension
    _sqlite3 = None  # type: ignore[assignment]
    SQLITE_ERRORS = ()
    SQLITE_OPERATIONAL_ERRORS = ()

_UNAVAILABLE_MESSAGE = (
    "This Python has no sqlite3 module, so the SQLite-backed features (run "
    "history, checkpoints, work queue, agent memory, remote-desktop audit "
    "log, SQL data sources) cannot run. Install it for this interpreter -- on "
    "FreeBSD it is the separate databases/py-sqlite3 package."
)


def sqlite3_available() -> bool:
    """Whether this interpreter can open SQLite databases."""
    return _sqlite3 is not None


def require_sqlite3():
    """Return the ``sqlite3`` module, raising if this build does not have it.

    Raises ``AutoControlUnsupportedOperationException`` -- the same type the
    platform backends raise for an operation they cannot perform, so the GUI
    tabs, the REST handler and the executor already report it as "unavailable
    here" instead of dying on an ``ImportError`` none of them catch.
    """
    if _sqlite3 is None:
        raise AutoControlUnsupportedOperationException(_UNAVAILABLE_MESSAGE)
    return _sqlite3
