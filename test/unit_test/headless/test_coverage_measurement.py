"""Why this package measures its coverage with ``coverage run -m pytest``.

``je_auto_control`` registers a ``pytest11`` entry point. Until 2026-10 it
pointed at ``je_auto_control.utils.pytest_plugin.plugin``, so pytest imported
that submodule while loading plugins — which executes
``je_auto_control/__init__.py``, the facade, and with it several hundred
modules. ``pytest-cov`` starts measuring after plugin loading, so every one of
those modules had its import-time lines (``def`` lines, class bodies,
constants, the dispatch tables) recorded as never executed.

That is not a small correction. Measured 2026-08-23 on one machine, same suite
and same ``[tool.coverage.run]`` config, the *only* difference being when
measurement starts: **52.22%** with ``pytest --cov`` and **72.05%** with
``coverage run -m pytest`` — 11,962 statements, and the files hit hardest were
the biggest ones (``action_executor`` +786, ``_handlers`` +684, the facade
itself +369). The floor in ``pyproject.toml`` had been set from the low number.

So ``quality.yml`` runs ``coverage run -m pytest``, which starts before pytest
loads anything. These tests pin that, because the difference between the two
spellings is invisible in a green build: reverting to ``pytest --cov`` gave
back 24 points and every job still passed.

The entry point is now the top-level module ``je_auto_control_pytest``, which
imports only pytest (``test_pytest_entrypoint_light.py``), so the plugin no
longer pulls the facade in. ``coverage run`` stays all the same: it does not
depend on what any plugin imports or on which build of the package is
installed — an environment that still has an older install keeps the old
entry point until it is reinstalled — and nothing has re-measured
``pytest --cov`` against it since the move.
"""
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_QUALITY_YML = _REPO_ROOT / ".github" / "workflows" / "quality.yml"


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
