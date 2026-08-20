"""``import je_auto_control`` must not need a Python built with sqlite3.

``sqlite3`` is in the standard library but not in every build of it: CPython
links it against a system library, and FreeBSD ships the result as the separate
``databases/py-sqlite3`` package. Ten AutoControl subsystems keep their state in
SQLite -- run history, checkpoints, the work queue, agent memory, the
remote-desktop audit log, SQL data sources, and the three error tuples that
catch their failures -- and every one of them is reachable from the facade, so
``import sqlite3`` at module scope made the whole package unimportable on such
an interpreter. Moving a mouse needs no database; that is what this file pins.

Like ``test_facade_import_is_light``, the check is made the way the machine
without it would make it: ``_sqlite3`` is blocked outright in a subprocess --
which is precisely what FreeBSD's stock ``python311`` reports -- and the facade
has to import anyway.
"""
import os
import pathlib
import subprocess  # nosec B404  # reason: fixed argv, sys.executable, no shell
import sys

import pytest

from je_auto_control.utils.exception.exceptions import (
    AutoControlException, AutoControlUnsupportedOperationException,
)
from je_auto_control.utils import sqlite_support
from je_auto_control.utils.run_history.history_store import HistoryStore

#: The working tree, so the subprocess tests the checkout rather than whatever
#: version of the package happens to be installed in site-packages.
REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]

_PROBE = '''
import pathlib
import sys


class _NoSqlite:
    """Refuse the sqlite3 extension the way FreeBSD's python311 does."""

    def find_spec(self, fullname, path=None, target=None):
        if fullname == "_sqlite3":
            raise ModuleNotFoundError(
                "No module named '_sqlite3'", name="_sqlite3")
        return None


for name in [m for m in sys.modules if m.split(".")[0] in ("sqlite3", "_sqlite3")]:
    del sys.modules[name]
sys.meta_path.insert(0, _NoSqlite())

import je_auto_control  # noqa: E402

if "sqlite3" in sys.modules:
    raise SystemExit("sqlite3 reached sys.modules")

# The catch tuples the containment boundaries splice in have to survive the
# absence: empty, so `except (ValueError, *SQLITE_ERRORS)` still compiles and
# still catches everything it did before.
from je_auto_control.utils import sqlite_support  # noqa: E402

if sqlite_support.SQLITE_ERRORS or sqlite_support.SQLITE_OPERATIONAL_ERRORS:
    raise SystemExit("the sqlite3 error tuples are not empty without sqlite3")
if sqlite_support.sqlite3_available():
    raise SystemExit("sqlite3_available() lied")

# Importing must not open (or create) the default run-history database either.
db = pathlib.Path.home() / ".je_auto_control" / "run_history.sqlite"
if db.exists():
    raise SystemExit("importing the facade created %s" % db)

print("ok", len(je_auto_control.__all__))
'''


def test_facade_imports_without_sqlite3(tmp_path):
    """The facade imports on an interpreter with no ``_sqlite3``."""
    home = tmp_path / "home"
    home.mkdir()
    env = dict(os.environ, PYTHONPATH=str(REPO_ROOT),
               HOME=str(home), USERPROFILE=str(home))
    env.pop("HOMEDRIVE", None)
    env.pop("HOMEPATH", None)
    # argv is this interpreter plus a module-level literal probe. No shell.
    result = subprocess.run(  # nosec B603  # nosemgrep  # reason: literal argv, no shell
        [sys.executable, "-c", _PROBE],
        capture_output=True, text=True, timeout=180, check=False, env=env)
    assert result.returncode == 0, (
        "import je_auto_control needs sqlite3:\n"
        f"{result.stdout}\n{result.stderr}")
    assert result.stdout.startswith("ok "), result.stdout


def test_require_sqlite3_reports_it_the_way_backends_do(monkeypatch):
    """Without the module, using a store raises the unsupported-operation type.

    That type is what the GUI tabs, the REST handler and the executor already
    translate into "not available here"; a bare ``ImportError`` would escape
    every one of those boundaries.
    """
    monkeypatch.setattr(sqlite_support, "_sqlite3", None)
    assert sqlite_support.sqlite3_available() is False
    with pytest.raises(AutoControlUnsupportedOperationException) as caught:
        sqlite_support.require_sqlite3()
    assert isinstance(caught.value, AutoControlException)
    assert "databases/py-sqlite3" in str(caught.value)


def test_error_tuples_hold_the_real_classes_when_sqlite3_is_there():
    """With the module present the catch tuples are its exception classes.

    They are tuples rather than the classes themselves so that the same
    ``except`` clauses stay valid, and catch nothing, on a build without it --
    which the subprocess probe above asserts on the empty side.
    """
    sqlite3 = pytest.importorskip("sqlite3")
    assert sqlite_support.sqlite3_available() is True
    assert sqlite_support.SQLITE_ERRORS == (sqlite3.Error,)
    assert sqlite_support.SQLITE_OPERATIONAL_ERRORS == (sqlite3.OperationalError,)


def test_history_store_opens_the_database_on_first_use(tmp_path):
    """Constructing the store must not touch the disk; using it must.

    The module-level ``default_history_store`` is built while the facade is
    importing, so anything its constructor does happens on every ``import
    je_auto_control``.
    """
    pytest.importorskip("sqlite3")
    db_path = tmp_path / "nested" / "run_history.sqlite"
    store = HistoryStore(path=db_path)
    assert not db_path.parent.exists(), "constructing the store made directories"

    run_id = store.start_run("scheduler", "job-1", "script.json")
    assert db_path.exists()
    assert store.get_run(run_id) is not None
    store.close()


def test_closing_a_store_that_never_opened_is_a_no_op(tmp_path):
    """``close()`` before any query neither connects nor raises."""
    db_path = tmp_path / "unused.sqlite"
    store = HistoryStore(path=db_path)
    store.close()
    assert not db_path.exists()


def test_a_closed_store_does_not_silently_reopen(tmp_path):
    """After ``close()``, a query still fails instead of starting a new file.

    The lazy connection could otherwise resurrect a closed store -- and for an
    in-memory store that means quietly returning an empty history.
    """
    sqlite3 = pytest.importorskip("sqlite3")
    store = HistoryStore(path=tmp_path / "closed.sqlite")
    store.start_run("scheduler", "job-1", "script.json")
    store.close()
    with pytest.raises(sqlite3.ProgrammingError):
        store.count()
