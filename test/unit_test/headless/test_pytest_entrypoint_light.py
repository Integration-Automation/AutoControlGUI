"""The ``pytest11`` entry point loads without importing the package.

pytest imports every ``pytest11`` entry point at start-up, in every
environment the package is installed in. The plugin used to be a submodule of
``je_auto_control``, so each of those runs imported the facade first. It is now
the top-level module ``je_auto_control_pytest``; these tests keep it that way.

The checks run in child interpreters: this process imported the package long
ago, through the tests around this one.
"""
import pathlib
import subprocess  # nosec B404  # reason: runs fixed probes with this interpreter
import sys

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib  # type: ignore[no-redef]  # reason: same API under the older name

ROOT = pathlib.Path(__file__).resolve().parents[3]
PLUGIN_NAMES = ("autocontrol", "autocontrol_executor", "autocontrol_screenshot_dir",
                "pytest_configure", "pytest_runtest_makereport")


def _probe(code: str) -> str:
    done = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,  # nosec B603  # nosemgrep  # reason: fixed argv, no shell
                          timeout=120, cwd=str(ROOT), check=False)
    assert done.returncode == 0, done.stderr[-2000:]
    return done.stdout.strip()


def test_entrypoint_import_is_light():
    out = _probe("import sys, je_auto_control_pytest; "
                 "print(sorted(name for name in sys.modules if name.split('.')[0] == 'je_auto_control'))")
    assert out == "[]"


def test_the_fixture_imports_the_package_only_when_used():
    out = _probe("import sys, je_auto_control_pytest as plugin; "
                 "before = 'je_auto_control' in sys.modules; "
                 "module = plugin.autocontrol.__wrapped__(); "
                 "print(before, module.__name__, 'je_auto_control' in sys.modules)")
    assert out == "False je_auto_control True"


def test_legacy_plugin_exports_same_hooks():
    import je_auto_control_pytest as standalone
    from je_auto_control.utils import pytest_plugin as package
    from je_auto_control.utils.pytest_plugin import plugin as legacy
    for name in PLUGIN_NAMES:
        assert getattr(legacy, name) is getattr(standalone, name), name
        assert getattr(package, name) is getattr(standalone, name), name


def test_both_metadata_files_point_the_entry_point_at_the_top_level_module():
    for name in ("pyproject.toml", "dev.toml"):
        data = tomllib.loads((ROOT / name).read_text(encoding="utf-8"))
        assert data["project"]["entry-points"]["pytest11"] == {"je_auto_control": "je_auto_control_pytest"}, name
        # Without this the module is not in the wheel and the entry point cannot load.
        assert data["tool"]["setuptools"]["py-modules"] == ["je_auto_control_pytest"], name
    assert (ROOT / "je_auto_control_pytest.py").is_file()
