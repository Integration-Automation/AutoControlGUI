"""The jobs that hold the PyPI token install and build with hash-locked tooling only.

``publish`` in ``stable.yml`` and ``publish-dev`` in ``dev.yml`` receive ``secrets.PYPI_API_TOKEN``,
so whatever they install runs next to it. Both install one file, ``.github/requirements/publish.txt``:
wheels only, at recorded hashes, generated from ``publish.in`` beside it. They build with
``python -m build --no-isolation``, so the build backend is the locked ``setuptools`` as well, not the
newest one downloaded into a fresh build environment.

Everything here is read from the files as text; nothing is installed or built.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest
from packaging.requirements import Requirement
from packaging.utils import canonicalize_name

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10, where pytest itself depends on tomli
    tomllib = pytest.importorskip("tomli")

REPO_ROOT = Path(__file__).resolve().parents[3]
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
REQUIREMENTS = REPO_ROOT / ".github" / "requirements"
# The metadata files a publish job can build from: scripts/dev_release.py writes dev.toml over pyproject.toml.
METADATA = ("pyproject.toml", "dev.toml")
LOCKED_INSTALL = "python -m pip install --require-hashes --only-binary :all: -r .github/requirements/publish.txt"

_JOB_NAME = re.compile(r"^  ([A-Za-z0-9_-]+):\s*$", re.MULTILINE)
_PIP_INSTALL = re.compile(r"(?:python3? -m )?\bpip3? install\b.*")
_BUILD = re.compile(r"\bpython3? -m build\b.*")
_RUN_OR_IMPORT = re.compile(r"python3? -m ([A-Za-z_]\w*)|^\s*import ([A-Za-z_]\w*)", re.MULTILINE)
_PIN = re.compile(r"^([A-Za-z0-9][\w.-]*)==(\S+)", re.MULTILINE)


def _jobs(workflow: Path) -> list[tuple[str, str]]:
    """Return ``(job name, job text without comment lines)`` for each job of a workflow."""
    jobs = workflow.read_text(encoding="utf-8").split("\njobs:\n", 1)[1]
    names = list(_JOB_NAME.finditer(jobs))
    ends = [name.start() for name in names[1:]] + [len(jobs)]
    return [(name.group(1), _without_comments(jobs[name.end():end])) for name, end in zip(names, ends)]


def _without_comments(text: str) -> str:
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("#"))


def _token_jobs() -> list[tuple[str, str]]:
    """Return ``(workflow:job, job text)`` for each job that reads the PyPI token."""
    return [(f"{workflow.name}:{name}", body)
            for workflow in sorted(WORKFLOWS.glob("*.yml"))
            for name, body in _jobs(workflow)
            if "secrets.PYPI_API_TOKEN" in body]


TOKEN_JOBS = _token_jobs()
token_job = pytest.mark.parametrize(
    "body", [body for _name, body in TOKEN_JOBS], ids=[name for name, _body in TOKEN_JOBS])


def _named_in_publish_in() -> set[str]:
    """Return the distributions ``publish.in`` names, one at the start of each line that is not a comment."""
    text = (REQUIREMENTS / "publish.in").read_text(encoding="utf-8")
    return {canonicalize_name(found) for found in re.findall(r"^([A-Za-z0-9][\w.-]*)", text, re.MULTILINE)}


def _locked() -> dict[str, str]:
    """Return ``{distribution: version}`` for every pin in ``publish.txt``."""
    text = (REQUIREMENTS / "publish.txt").read_text(encoding="utf-8")
    return {canonicalize_name(name): version for name, version in _PIN.findall(text)}


def _build_requires(metadata: str) -> list[Requirement]:
    with (REPO_ROOT / metadata).open("rb") as handle:
        return [Requirement(item) for item in tomllib.load(handle)["build-system"]["requires"]]


def _tools(body: str) -> set[str]:
    """Return what a job runs with ``python -m`` or imports in an inline script, less pip and the stdlib."""
    named = {module or imported for module, imported in _RUN_OR_IMPORT.findall(body)}
    return {canonicalize_name(name) for name in named - {"pip"} - set(sys.stdlib_module_names)}


def test_the_jobs_that_hold_the_pypi_token_are_the_two_publish_jobs():
    # A third job that gains the token is covered by the tests below, but should be a decision.
    assert [name for name, _body in TOKEN_JOBS] == ["dev.yml:publish-dev", "stable.yml:publish"]


@token_job
def test_a_job_with_the_pypi_token_installs_only_the_hash_locked_tooling(body):
    # An unpinned install, a second install or a pip upgrade takes whatever was uploaded that day.
    assert [command.strip().strip("\"'") for command in _PIP_INSTALL.findall(body)] == [LOCKED_INSTALL]


@token_job
def test_a_job_with_the_pypi_token_builds_with_the_locked_backend(body):
    # An isolated build downloads the newest setuptools each time, outside the lock.
    builds = _BUILD.findall(body)
    assert builds, "the job no longer runs python -m build: update this guard"
    assert all("--no-isolation" in command for command in builds)


@pytest.mark.parametrize("metadata", METADATA)
def test_the_lock_satisfies_build_system_requires(metadata):
    # --no-isolation checks the requirement instead of installing it, so a floor raised without
    # regenerating the lock has to fail here, not in the job that is about to upload.
    locked = _locked()
    requires = _build_requires(metadata)
    assert requires, f"{metadata} names no build backend"
    for requirement in requires:
        name = canonicalize_name(requirement.name)
        assert name in locked, f"{metadata} needs {requirement}, which publish.txt does not pin"
        assert requirement.specifier.contains(locked[name], prereleases=True), (
            f"{metadata} needs {requirement}, publish.txt pins {locked[name]}: regenerate the lock")


def test_publish_in_names_the_tools_the_jobs_run_and_the_build_backend():
    # A tool a job starts using has to be locked first, or the release fails at that step.
    used = set().union(*(_tools(body) for _name, body in TOKEN_JOBS))
    backend = {canonicalize_name(requirement.name)
               for metadata in METADATA for requirement in _build_requires(metadata)}
    assert _named_in_publish_in() == used | backend


def test_the_lock_pins_everything_publish_in_names():
    # publish.txt is generated; editing publish.in alone changes nothing the jobs install.
    assert _named_in_publish_in() <= set(_locked())


def test_the_lock_is_resolved_for_the_python_the_jobs_set_up():
    # The lock holds the wheels of one Python version; a job on another one may find none that match.
    header = (REQUIREMENTS / "publish.txt").read_text(encoding="utf-8").splitlines()[1]
    assert "--generate-hashes" in header
    assert "--only-binary :all:" in header
    locked_for = re.search(r"--python-version (\S+)", header).group(1)
    set_up = {version for _name, body in TOKEN_JOBS
              for version in re.findall(r"python-version:\s*\"([^\"]+)\"", body)}
    assert set_up == {locked_for}


def test_dependabot_watches_the_hash_locked_requirements():
    # From "/" Dependabot does not look as deep as .github/requirements, so the lock would never be updated.
    text = (REPO_ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")
    entries = re.split(r"^\s*-\s*package-ecosystem:", text, flags=re.MULTILINE)[1:]
    pip = next(entry for entry in entries if entry.split()[0].strip("\"'") == "pip")
    assert set(re.findall(r"^\s*-\s*\"(/[^\"]*)\"", pip, re.MULTILINE)) == {"/", "/.github/requirements"}
