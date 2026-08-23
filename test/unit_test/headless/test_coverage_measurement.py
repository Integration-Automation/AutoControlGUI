"""Why this package cannot measure its own coverage with ``pytest --cov``.

``je_auto_control`` registers a ``pytest11`` entry point, so pytest imports
``je_auto_control.utils.pytest_plugin.plugin`` while it is loading plugins —
and importing that submodule executes ``je_auto_control/__init__.py``, the
facade, which imports several hundred modules. ``pytest-cov`` starts measuring
after plugin loading, so every one of those modules had its import-time lines
(``def`` lines, class bodies, constants, the dispatch tables) recorded as never
executed.

That is not a small correction. Measured 2026-08-23 on one machine, same suite
and same ``[tool.coverage.run]`` config, the *only* difference being when
measurement starts: **52.22%** with ``pytest --cov`` and **72.05%** with
``coverage run -m pytest`` — 11,962 statements, and the files hit hardest were
the biggest ones (``action_executor`` +786, ``_handlers`` +684, the facade
itself +369). The floor in ``pyproject.toml`` had been set from the low number.

So ``quality.yml`` runs ``coverage run -m pytest``, which starts before pytest
loads anything. These tests pin that, because the difference between the two
spellings is invisible in a green build: reverting to ``pytest --cov`` gives
back 24 points and every job still passes.
"""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_QUALITY_YML = _REPO_ROOT / ".github" / "workflows" / "quality.yml"


def test_the_facade_is_imported_before_any_test_runs():
    """The premise: pytest has already imported the package by test time.

    This is what makes the measurement order matter. It holds no matter which
    test file runs first and with no conftest of ours involved, because the
    entry point pulls the facade in during plugin loading.
    """
    assert "je_auto_control" in sys.modules
    assert "je_auto_control.utils.pytest_plugin.plugin" in sys.modules


def test_ci_starts_coverage_before_pytest_loads_plugins():
    """``coverage run -m pytest``, not ``pytest --cov``. See the module docstring."""
    workflow = _QUALITY_YML.read_text(encoding="utf-8")

    assert "python -m coverage run -m pytest" in workflow
    assert "--cov=je_auto_control" not in workflow, (
        "pytest --cov starts measuring after pytest has imported this package "
        "through its pytest11 entry point; it under-reports by ~24 points"
    )
    assert "--cov-fail-under" not in workflow, (
        "the floor is `fail_under` in pyproject.toml so the ratchet has one "
        "home; a second copy in the workflow is a second place to be wrong"
    )


def test_the_coverage_xml_is_written_before_the_floor_is_enforced():
    """A square that misses the floor still has to upload what it was short of."""
    workflow = _QUALITY_YML.read_text(encoding="utf-8")

    assert workflow.index("python -m coverage xml") < \
        workflow.index("python -m coverage report")
