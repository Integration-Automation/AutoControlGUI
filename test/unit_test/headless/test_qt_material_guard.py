"""Every headless test that imports the main window skips without qt_material.

``gui/main_window.py`` imports ``qt_material`` for its theme. Developers have
it installed, the ``pytest-headless`` CI job does not, so a test that imports
the window without ``pytest.importorskip("qt_material")`` passes locally and
fails every CI square. This reads the test sources, so it fails on the
developer's machine too.
"""
import ast
from pathlib import Path

_HEADLESS = Path(__file__).resolve().parent
_WINDOW = "je_auto_control.gui.main_window"


def _imports_window(node: ast.AST) -> bool:
    if isinstance(node, ast.ImportFrom):
        return node.module == _WINDOW or (node.module == "je_auto_control.gui"
                                          and any(alias.name == "main_window" for alias in node.names))
    if isinstance(node, ast.Import):
        return any(alias.name == _WINDOW for alias in node.names)
    return isinstance(node, ast.Constant) and isinstance(node.value, str) and _WINDOW in node.value


def _skips_without_theme(node: ast.AST) -> bool:
    return (isinstance(node, ast.Call) and getattr(node.func, "attr", None) == "importorskip"
            and bool(node.args) and isinstance(node.args[0], ast.Constant)
            and node.args[0].value == "qt_material")


def _unguarded(tree: ast.Module) -> list:
    """Names of the functions (or ``<module>``) that import the window unguarded."""
    if any(_skips_without_theme(node) for statement in tree.body for node in ast.walk(statement)
           if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))):
        return []
    scopes = [node for node in ast.walk(tree) if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))]
    missing = [scope.name for scope in scopes
               if any(_imports_window(node) for node in ast.walk(scope))
               and not any(_skips_without_theme(node) for node in ast.walk(scope))]
    module_level = [node for statement in tree.body
                    if not isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                    for node in ast.walk(statement)]
    if any(isinstance(node, (ast.Import, ast.ImportFrom)) and _imports_window(node) for node in module_level):
        missing.append("<module>")
    return missing


def test_every_main_window_import_skips_without_qt_material():
    offenders = {}
    for path in sorted(_HEADLESS.glob("test_*.py")):
        if path.name == Path(__file__).name:
            continue                               # its own fixtures are strings, not imports
        missing = _unguarded(ast.parse(path.read_text(encoding="utf-8")))
        if missing:
            offenders[path.name] = missing
    assert not offenders, offenders


def test_the_check_sees_an_unguarded_import():
    source = "def test_x():\n    from je_auto_control.gui.main_window import AutoControlGUIUI\n"
    assert _unguarded(ast.parse(source)) == ["test_x"]
    guarded = ("import pytest\ndef test_x():\n    pytest.importorskip('qt_material', exc_type=ImportError)\n"
               "    from je_auto_control.gui.main_window import AutoControlGUIUI\n")
    assert _unguarded(ast.parse(guarded)) == []
