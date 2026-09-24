"""Per-user state paths are resolved when used, so a test run can redirect them.

The ``pytest11`` plugin imports the whole package before any ``conftest.py``
runs. A module that computes ``Path.home()`` at import time therefore pins the
account's real ``~/.je_auto_control`` for the whole run, and no test suite can
keep that state out of its way: ``test/conftest.py`` redirects ``HOME`` and
``USERPROFILE``, and until 2026-09-23 nine module-level paths ignored it
(signing and encryption keys, the host fingerprint and known hosts, the host
service config, the WebRTC inbox, and three JSONL/JSON stores), while the
suite wrote the real audit chain, address book, quarantine list, run history
and 419 error screenshots.
"""
import ast
import os
import tempfile
from pathlib import Path

import pytest

_PACKAGE = Path(__file__).resolve().parents[3] / "je_auto_control"


def _looks_up_home(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
            and node.func.attr in {"home", "expanduser"})


def import_time_home_lookups(source: str):
    """Line numbers where the home directory is read outside a function body.

    Module level, class bodies, default argument values and decorators all run
    when the module is imported; only function bodies wait to be called.
    """
    found = []

    def expressions(expr):
        found.extend(sub.lineno for sub in ast.walk(expr) if _looks_up_home(sub))

    def visit(node):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda)):
                for default in [*child.args.defaults, *filter(None, child.args.kw_defaults)]:
                    expressions(default)
                for decorator in getattr(child, "decorator_list", []):
                    expressions(decorator)
                continue
            if _looks_up_home(child):
                found.append(child.lineno)
            visit(child)

    visit(ast.parse(source))
    return sorted(set(found))


def test_no_module_reads_the_home_directory_at_import():
    offenders = [
        f"{path.relative_to(_PACKAGE.parent).as_posix()}:{line}"
        for path in sorted(_PACKAGE.rglob("*.py"))
        for line in import_time_home_lookups(path.read_text(encoding="utf-8"))]
    assert not offenders, (
        "resolve these inside a function so HOME can be redirected after "
        "import:\n" + "\n".join(offenders))


def test_the_scanner_sees_every_import_time_form():
    source = (
        "from pathlib import Path\nimport os\n"
        "A = Path.home() / 'x'\n"                               # module level
        "class C:\n    B = os.path.expanduser('~')\n"           # class body
        "def f(p=Path('~').expanduser()):\n    return p\n"      # default value
        "def g():\n    return Path.home()\n"                    # fine: call time
    )
    assert import_time_home_lookups(source) == [3, 5, 6]


@pytest.mark.parametrize("module, function, name", [
    ("je_auto_control.utils.ab_locator.store", "default_stats_path",
     "ab_locator_stats.json"),
    ("je_auto_control.utils.cost_telemetry.store", "default_cost_log_path",
     "cost_events.jsonl"),
    ("je_auto_control.utils.self_healing.heal_log", "default_heal_log_path",
     "self_healing_events.jsonl"),
    ("je_auto_control.utils.action_signing.cipher", "_default_key_path",
     "action_encryption_key"),
    ("je_auto_control.utils.action_signing.signer", "_default_key_path",
     "action_signing_key"),
    ("je_auto_control.utils.remote_desktop.fingerprint", "_host_fingerprint_path",
     "host_fingerprint"),
    ("je_auto_control.utils.remote_desktop.fingerprint", "_known_hosts_path",
     "known_hosts.json"),
    ("je_auto_control.utils.remote_desktop.host_service", "_default_config_path",
     "host_service.json"),
    ("je_auto_control.utils.remote_desktop.webrtc_files", "default_inbox_dir",
     "inbox"),
])
def test_each_default_follows_a_home_set_after_import(monkeypatch, tmp_path,
                                                     module, function, name):
    resolver = getattr(pytest.importorskip(module), function)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    assert resolver() == tmp_path / ".je_auto_control" / name


def test_this_run_has_its_own_home_directory():
    """test/conftest.py hands the whole run a temporary home."""
    home = Path(os.path.expanduser("~")).resolve()
    assert home.is_relative_to(Path(tempfile.gettempdir()).resolve())


def test_the_default_history_store_follows_a_home_set_after_import(
        monkeypatch, tmp_path):
    """Built while the package imports, so it resolves its path lazily.

    It used to call ``_default_history_path()`` at import, so the
    ``run_history.sqlite`` in the account's real home kept changing during a
    test run that had redirected HOME -- the one file the redirection missed.
    """
    from je_auto_control.utils.run_history.history_store import HistoryStore, _default_history_path
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    store = HistoryStore(path=_default_history_path)
    assert store.path == str(tmp_path / ".je_auto_control" / "run_history.sqlite")


_CAPTURE_PROBE = r'''
import sys
from pathlib import PurePath

import je_auto_control  # noqa: F401

marker = sys.argv[1]
hits = []


def captured(value):
    return isinstance(value, (str, PurePath)) and marker in str(value)


for module_name, module in list(sys.modules.items()):
    if not module_name.startswith("je_auto_control") or module is None:
        continue
    for name, value in list(vars(module).items()):
        if captured(value):
            hits.append(f"{module_name}.{name}")
            continue
        inner = getattr(value, "__dict__", None)
        if isinstance(value, type) and value.__module__ != module_name:
            continue
        if isinstance(inner, dict) or hasattr(inner, "items"):
            for attr, attr_value in list(dict(inner).items()):
                if captured(attr_value):
                    hits.append(f"{module_name}.{name}.{attr}")
print("\n".join(sorted(set(hits))))
'''


def test_importing_the_package_captures_no_home_path(tmp_path):
    """Nothing the import leaves behind may already hold the home directory.

    The AST scan above only sees a literal ``Path.home()`` outside a function;
    ``default_history_store`` read its path through a helper called at module
    level and slipped past it. This imports the package with a distinctive
    home and looks for that path in every module global, class attribute and
    module-level object attribute.
    """
    import subprocess  # nosec B404  # reason: runs the test interpreter on a fixed argv
    import sys
    home = tmp_path / "unmistakable-home-marker"
    home.mkdir()
    env = dict(os.environ, HOME=str(home), USERPROFILE=str(home),
               PYTHONPATH=str(_PACKAGE.parent))
    result = subprocess.run(  # nosec B603  # nosemgrep  # reason: fixed argv, the test interpreter
        [sys.executable, "-c", _CAPTURE_PROBE, home.name],
        capture_output=True, text=True, timeout=180, check=True, env=env)
    assert result.stdout.strip() == "", result.stdout
