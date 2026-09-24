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
import functools
from contextlib import contextmanager
from typing import Any, Callable, Iterator, Tuple, Type, TypeVar

from je_auto_control.utils.exception.exceptions import (
    AutoControlException, AutoControlUnsupportedOperationException,
)

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


_Function = TypeVar("_Function", bound=Callable[..., Any])


def sqlite_errors_as(error_type: Type[AutoControlException]) -> Callable[[_Function], _Function]:
    """Decorate a store method so ``sqlite3.Error`` leaves it as ``error_type``.

    ``sqlite3.Error`` derives from ``Exception`` alone, so a corrupt database
    file or a lock held past the timeout escaped every boundary that contains
    the ``AutoControlException`` family -- and ended the background thread
    (a hotkey listener, a host service) that had called the store.
    """
    def decorate(function: _Function) -> _Function:
        @functools.wraps(function)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            try:
                return function(*args, **kwargs)
            except SQLITE_ERRORS as error:
                raise error_type(f"{function.__qualname__}: {error}") from error
        return wrapper  # type: ignore[return-value]
    return decorate


def last_row_id(cursor: Any) -> int:
    """Return the id of the row a just-executed INSERT created.

    ``Cursor.lastrowid`` is ``None`` until an INSERT has run on that
    cursor, so every caller that returns it has to say what it means when
    it is not there rather than hand ``None`` on as an id.
    """
    row_id = cursor.lastrowid
    if row_id is None:
        raise AutoControlException("INSERT did not report a row id")
    return int(row_id)


@contextmanager
def autocommit_connection(db_path: str, *, timeout: float = 30.0) -> Iterator[Any]:
    """Open ``db_path`` in autocommit mode with ``Row`` rows; close it on exit.

    ``with sqlite3.connect(...) as conn`` only commits or rolls back -- it
    never closes -- so every store that used it leaked one connection per
    call until garbage collection. A transaction the caller began with
    ``BEGIN`` and did not finish is rolled back by the close.
    """
    driver = require_sqlite3()
    connection = driver.connect(db_path, timeout=timeout, isolation_level=None)
    try:
        connection.row_factory = driver.Row
        yield connection
    finally:
        connection.close()


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
