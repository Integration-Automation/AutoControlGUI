"""The strict typing tier covers every module written since it was introduced.

``pyproject.toml`` turns ``disallow_untyped_defs`` and ``disallow_any_generics``
on for a named list of modules. A list a person has to remember to extend is a
list that stops growing, so this compares it against the tree: a module is
either one that predates the tier (``test/verify/typing_strict_baseline.txt``,
which may only shrink) or it is in the tier. There is no third state to forget
a module into.

mypy itself is run by ``test/verify/typing_contract_verify.py`` (three target
platforms, a job of its own in CI). What is checked here needs no mypy: the
lists, and -- read straight from the source -- that the modules in the tier
really do annotate every function, so the suite notices on any interpreter.
"""
import ast
import re
import shutil
import subprocess  # nosec B404  # reason: fixed `git` argv, no shell
from pathlib import Path
from typing import Dict, Iterator, List, Set, Tuple

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10, where pytest itself depends on tomli
    tomllib = pytest.importorskip("tomli")

REPO_ROOT = Path(__file__).resolve().parents[3]
PACKAGE = "je_auto_control"
VERIFY_DIR = REPO_ROOT / "test" / "verify"
EXEMPT_FILE = VERIFY_DIR / "typing_contract_exempt.txt"
BASELINE_FILE = VERIFY_DIR / "typing_strict_baseline.txt"
#: The tag the baseline was measured at.
BASELINE_TAG = "v0.0.225"
STRICT_SETTINGS = ("disallow_untyped_defs", "disallow_any_generics")

#: Modules written after the baseline that are NOT in the strict tier, each
#: with the reason. Empty: every one of them was made clean. An entry here is
#: a debt someone agreed to, not a way to turn a red build green.
NOT_YET_STRICT: Dict[str, str] = {}

#: The only modules that may bind a name to ``Any`` at module level. Each is a
#: typed adapter for an optional SDK the contract deliberately reads as ``Any``
#: (see the ``follow_imports = "skip"`` block in ``pyproject.toml``); the
#: modules around it import the alias instead of spelling ``Any`` themselves.
SDK_ANY_ADAPTERS = {
    # av.VideoFrame and the aiortc-backed host / viewer / recorder classes,
    # which are ``None`` at run time without the ``webrtc`` extra.
    "je_auto_control.gui.remote_desktop._webrtc_types",
}

_BARE_IGNORE = re.compile(r"#\s*type:\s*ignore(?!\[)")


def _module_name(path: Path) -> str:
    parts = path.relative_to(REPO_ROOT).with_suffix("").parts
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _tree_modules() -> Dict[str, Path]:
    """Every module the distribution ships: the package plus its ``py-modules``."""
    found = {_module_name(path): path
             for path in (REPO_ROOT / PACKAGE).rglob("*.py")
             if "__pycache__" not in path.parts}
    for name in _pyproject()["tool"]["setuptools"].get("py-modules", []):
        found[name] = REPO_ROOT / f"{name}.py"
    return found


def _pyproject() -> dict:
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        return tomllib.load(handle)


def _listed(path: Path) -> Set[str]:
    lines = path.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def _strict_patterns() -> List[str]:
    """The module patterns of the override block that carries both strict settings."""
    blocks = [block for block in _pyproject()["tool"]["mypy"]["overrides"]
              if all(block.get(setting) is True for setting in STRICT_SETTINGS)]
    assert len(blocks) == 1, "expected exactly one strict [[tool.mypy.overrides]] block"
    return list(blocks[0]["module"])


def _matches(module: str, patterns: List[str]) -> bool:
    for pattern in patterns:
        if pattern.endswith(".*"):
            if module.startswith(pattern[:-1]):
                return True
        elif module == pattern:
            return True
    return False


def _strict_modules() -> Dict[str, Path]:
    patterns = _strict_patterns()
    return {name: path for name, path in _tree_modules().items() if _matches(name, patterns)}


_SCOPES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef, ast.Lambda)


def _functions(tree: ast.AST, in_class: bool = False) -> Iterator[Tuple[ast.AST, bool]]:
    """Each function with whether it is a method (its nearest scope is a class).

    The nearest *scope*, not the direct parent: a method declared under
    ``if TYPE_CHECKING:`` in a class body is still a method.
    """
    for child in ast.iter_child_nodes(tree):
        if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
            yield child, in_class
        inner = isinstance(child, ast.ClassDef) if isinstance(child, _SCOPES) else in_class
        yield from _functions(child, inner)


def _missing_annotations(node: ast.AST, in_class: bool) -> List[str]:
    """What mypy's ``disallow_untyped_defs`` would name on one function."""
    arguments = node.args
    positional = [*arguments.posonlyargs, *arguments.args]
    decorators = {getattr(item, "id", getattr(item, "attr", "")) for item in node.decorator_list}
    if in_class and positional and "staticmethod" not in decorators:
        positional = positional[1:]      # self / cls
    every = [*positional, *arguments.kwonlyargs, arguments.vararg, arguments.kwarg]
    missing = [arg.arg for arg in every if arg is not None and arg.annotation is None]
    if node.returns is None:
        missing.append("return")
    return missing


def _untyped(tree: ast.AST) -> List[Tuple[int, str, List[str]]]:
    return [(node.lineno, node.name, missing) for node, is_method in _functions(tree)
            for missing in [_missing_annotations(node, is_method)] if missing]


def _any_aliases(tree: ast.Module) -> List[str]:
    """Module-level names bound to ``Any`` (``X = Any``, at any nesting of ``if``)."""
    names: List[str] = []
    pending = list(tree.body)
    while pending:
        node = pending.pop()
        if isinstance(node, ast.If):
            pending.extend([*node.body, *node.orelse])
        elif isinstance(node, ast.Assign) and getattr(node.value, "id", "") == "Any":
            names.extend(target.id for target in node.targets if isinstance(target, ast.Name))
    return sorted(names)


def test_exemptions_remain_empty():
    exemptions = _listed(EXEMPT_FILE)
    assert exemptions == set()


def test_the_strict_tier_never_relaxes_a_package_wide_setting():
    base = _pyproject()["tool"]["mypy"]
    assert base["check_untyped_defs"] is True and base["no_implicit_optional"] is True
    assert "ignore_errors" not in base
    for block in base["overrides"]:
        assert "ignore_errors" not in block, f"ignore_errors in the override for {block['module']}"
        assert block.get("check_untyped_defs", True) is True
        for setting in STRICT_SETTINGS:
            assert block.get(setting, True) is True, f"{setting} switched off for {block['module']}"


def test_every_module_is_strict_or_predates_the_tier():
    """A module in neither list is new code that nobody asked mypy to hold to the tier."""
    patterns = _strict_patterns()
    baseline = _listed(BASELINE_FILE)
    modules = _tree_modules()
    unassigned = sorted(name for name in modules
                        if name not in baseline and name not in NOT_YET_STRICT
                        and not _matches(name, patterns))
    assert unassigned == [], (
        "add these to the strict [[tool.mypy.overrides]] block in pyproject.toml "
        "(the baseline list may not grow)")


def test_the_lists_name_only_modules_that_exist():
    modules = set(_tree_modules())
    stale_baseline = sorted(_listed(BASELINE_FILE) - modules)
    assert stale_baseline == [], "delete these lines from typing_strict_baseline.txt"
    stale_strict = sorted(pattern for pattern in _strict_patterns()
                          if not pattern.endswith(".*") and pattern not in modules)
    assert stale_strict == [], "these strict overrides match no module"
    assert sorted(set(NOT_YET_STRICT) - modules) == []
    assert all(reason.strip() for reason in NOT_YET_STRICT.values())


def test_the_baseline_is_the_package_at_its_tag():
    """Where the tag is available, the baseline is what it says it is -- or smaller."""
    git = shutil.which("git")
    if git is None:
        pytest.skip("git is not installed")
    listing = subprocess.run(  # nosec B603  # nosemgrep  # reason: fixed argv, no shell, no input
        [git, "ls-tree", "-r", "--name-only", BASELINE_TAG, "--", PACKAGE],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False)
    if listing.returncode != 0:
        pytest.skip(f"{BASELINE_TAG} is not in this clone (shallow checkout)")
    at_tag = {_module_name(REPO_ROOT / line) for line in listing.stdout.split()
              if line.endswith(".py")}
    grown = sorted(_listed(BASELINE_FILE) - at_tag)
    assert grown == [], f"modules newer than {BASELINE_TAG} were added to the baseline"


def test_the_pytest_plugin_module_is_type_checked():
    """``py-modules`` ship beside the package and are held to the same contract."""
    shipped = _pyproject()["tool"]["setuptools"]["py-modules"]
    verify = (VERIFY_DIR / "typing_contract_verify.py").read_text(encoding="utf-8")
    for name in shipped:
        assert f'"{name}.py"' in verify, f"typing_contract_verify.py does not check {name}.py"
        assert _matches(name, _strict_patterns())


def test_new_modules_have_complete_annotations():
    untyped_public_signatures = []
    for name, path in sorted(_strict_modules().items()):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        untyped_public_signatures += [
            f"{name}:{line} {function}({', '.join(missing)})"
            for line, function, missing in _untyped(tree)]
    assert untyped_public_signatures == []


def test_adapter_is_only_sdk_any_boundary():
    sdk_any_leaks = []
    for name, path in sorted(_strict_modules().items()):
        source = path.read_text(encoding="utf-8")
        if name not in SDK_ANY_ADAPTERS:
            sdk_any_leaks += [f"{name}: {alias} = Any" for alias in _any_aliases(ast.parse(source))]
        sdk_any_leaks += [f"{name}:{number} unscoped type: ignore"
                          for number, line in enumerate(source.splitlines(), 1)
                          if _BARE_IGNORE.search(line)]
    assert sdk_any_leaks == []
    assert SDK_ANY_ADAPTERS <= set(_strict_modules()), "an adapter must itself be strict"


@pytest.mark.parametrize("source, expected", [
    ("def f(a, b: int): ...", [(1, "f", ["a", "return"])]),
    ("class C:\n    def m(self, x) -> None: ...", [(2, "m", ["x"])]),
    ("class C:\n    @staticmethod\n    def s(x) -> None: ...", [(3, "s", ["x"])]),
    ("def f(*args, **kwargs) -> None: ...", [(1, "f", ["args", "kwargs"])]),
    ("def f(a: int, *, b: str = '') -> None:\n    def g(c: int) -> int: return c", []),
])
def test_the_annotation_scan_sees_what_mypy_would(source, expected):
    """The scan above is only evidence if it fails on an untyped function."""
    assert _untyped(ast.parse(source)) == expected


def test_the_alias_scan_sees_an_any_alias():
    tree = ast.parse("from typing import Any\nif True:\n    A = B = Any\nelse:\n    C = Any\nD = int")
    assert _any_aliases(tree) == ["A", "B", "C"]
