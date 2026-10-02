"""Keep coverage startup and the established floor consistent with CI.

The automatic plugin now imports only pytest; fresh-process tests in
``test_pytest_entrypoint_light`` enforce that boundary. CI retains
``coverage run -m pytest`` to measure every import, including explicit legacy
plugins and other integrations that load the facade during pytest startup.
"""
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[3]
_QUALITY_YML = _REPO_ROOT / ".github" / "workflows" / "quality.yml"


def test_ci_starts_coverage_before_pytest_loads_plugins():
    """``coverage run -m pytest``, not ``pytest --cov``. See the module docstring."""
    workflow = _QUALITY_YML.read_text(encoding="utf-8")

    assert "python -m coverage run -m pytest" in workflow
    assert "--cov=je_auto_control" not in workflow, (
        "coverage must start before plugin loading, including explicit legacy plugins"
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
