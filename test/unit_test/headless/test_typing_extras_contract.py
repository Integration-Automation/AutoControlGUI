"""The ``--extras`` mode of the typing contract, and the CI job that runs it.

``typing_contract_verify.py`` reads PySide6, aiortc and av as ``Any`` so its
verdict cannot depend on what is installed. ``--extras`` drops exactly those
three from the override and compares against its own shrink-only list. mypy
itself runs in the ``typing-extras`` job of ``quality.yml`` (three targets, a
minute); what is held here is everything that would make that job measure the
wrong thing without failing.
"""
import importlib.util
import re
from pathlib import Path
from types import ModuleType
from typing import Set

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10, where pytest itself depends on tomli
    tomllib = pytest.importorskip("tomli")

REPO_ROOT = Path(__file__).resolve().parents[3]
VERIFY = REPO_ROOT / "test" / "verify" / "typing_contract_verify.py"
EXTRAS_LIST = REPO_ROOT / "test" / "verify" / "typing_extras_exempt.txt"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "quality.yml"
DROPPED = {"PySide6", "PySide6.*", "aiortc", "aiortc.*", "av", "av.*"}


def _script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("typing_contract_verify_under_test", VERIFY)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _skipped_modules(config: dict) -> Set[str]:
    """Every module a ``follow_imports = "skip"`` override names."""
    found: Set[str] = set()
    for override in config["tool"]["mypy"]["overrides"]:
        if override.get("follow_imports") == "skip":
            found |= set(override["module"])
    return found


def _job(name: str) -> str:
    """The text of one job of ``quality.yml``."""
    text = WORKFLOW.read_text(encoding="utf-8")
    match = re.search(rf"^  {re.escape(name)}:\n(.*?)(?=^  [\w-]+:\n|\Z)", text,
                      flags=re.MULTILINE | re.DOTALL)
    assert match, f"quality.yml has no `{name}` job"
    return match.group(1)


def _listed() -> Set[str]:
    lines = EXTRAS_LIST.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def test_the_extras_configuration_drops_exactly_three_libraries(tmp_path, monkeypatch):
    script = _script()
    monkeypatch.setattr(script, "_missing_extras", lambda: [])
    written = script._extras_config(tmp_path)
    assert written.name == "pyproject.toml", "mypy reads [tool.mypy] only from a file of that name"
    with (REPO_ROOT / "pyproject.toml").open("rb") as handle:
        original = tomllib.load(handle)
    with written.open("rb") as handle:
        relaxed = tomllib.load(handle)
    assert _skipped_modules(original) - _skipped_modules(relaxed) == DROPPED
    assert _skipped_modules(relaxed) - _skipped_modules(original) == set()
    for config in (original, relaxed):
        for override in config["tool"]["mypy"]["overrides"]:
            override["module"] = [name for name in override["module"] if name not in DROPPED]
    assert relaxed == original, "--extras changed something other than the three libraries"


def test_extras_mode_refuses_to_run_without_the_libraries(tmp_path, monkeypatch):
    script = _script()
    monkeypatch.setattr(script, "_missing_extras", lambda: ["aiortc"])
    with pytest.raises(SystemExit) as stopped:
        script._extras_config(tmp_path)
    assert "aiortc" in str(stopped.value) and "gui,webrtc" in str(stopped.value)


def test_extras_mode_stops_when_the_override_was_reworded(tmp_path, monkeypatch):
    script = _script()
    monkeypatch.setattr(script, "_missing_extras", lambda: [])
    (tmp_path / "pyproject.toml").write_text("[tool.mypy]\n", encoding="utf-8")
    monkeypatch.setattr(script, "REPO_ROOT", tmp_path)
    with pytest.raises(SystemExit) as stopped:
        script._extras_config(tmp_path / "out")
    assert "EXTRAS_OVERRIDE_LINES" in str(stopped.value)


def test_the_extras_list_names_modules_that_exist_and_is_counted():
    listed = _listed()
    for module in sorted(listed):
        relative = Path(*module.split("."))
        assert ((REPO_ROOT / relative).with_suffix(".py").is_file()
                or (REPO_ROOT / relative / "__init__.py").is_file()), f"{module} is listed and gone"
    header = EXTRAS_LIST.read_text(encoding="utf-8")
    assert f"# Measured entries: {len(listed)}\n" in header.replace("\r\n", "\n")


def test_the_two_lists_stay_apart():
    """The ordinary contract's list is empty; nothing may be parked in it from the other."""
    script = _script()
    assert script.EXEMPT_FILE != script.EXTRAS_EXEMPT_FILE
    assert script._read_exempt(script.EXEMPT_FILE) == set()


def test_the_required_job_still_installs_no_extras():
    job = _job("typing-stable-api")
    assert "pip install -e ." in job and "[gui" not in job and "webrtc" not in job
    assert "typing_contract_verify.py --extras" not in job


def test_the_extras_job_runs_both_questions_on_pinned_libraries():
    job = _job("typing-extras")
    assert 'pip install -e ".[gui,webrtc]"' in job
    for pin in ("mypy==", "PySide6==", "aiortc==", "av=="):
        assert pin in job, f"the extras job no longer pins {pin}"
    assert re.search(r"run: python test/verify/typing_contract_verify\.py\n", job.replace("\r\n", "\n"))
    assert "run: python test/verify/typing_contract_verify.py --extras" in job
