"""``scripts/stable_release.py`` picks the version a push to ``main`` releases.

PyPI never takes a number twice, so the two ways of getting it wrong are both pinned here without
touching git or the network: bumping past a version that was set by hand (1.0.0 would have gone
out as 1.0.1), and releasing a version that is already tagged. The last tests read
``.github/workflows/stable.yml``, since the script only matters while the publish job runs it.
"""
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "stable_release.py"
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "stable.yml"


def _load_script():
    spec = importlib.util.spec_from_file_location("stable_release", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


stable_release = _load_script()


@pytest.mark.parametrize("declared, tags, expected", [
    ((0, 0, 234), {(0, 0, 233), (0, 0, 234)}, (0, 0, 235)),  # an ordinary merge
    ((1, 0, 0), {(0, 0, 233), (0, 0, 234)}, (1, 0, 0)),      # a version set by hand
    ((1, 0, 0), {(0, 0, 234), (1, 0, 0)}, (1, 0, 1)),        # the merge after it
    ((1, 1, 0), {(1, 0, 0), (1, 0, 7)}, (1, 1, 0)),
    ((0, 0, 1), set(), (0, 0, 1)),                           # no tag yet
])
def test_an_untagged_version_is_released_as_written_and_a_tagged_one_is_bumped(declared, tags, expected):
    assert stable_release.release_version(declared, tags) == expected


def test_an_untagged_version_below_the_newest_tag_is_refused():
    with pytest.raises(SystemExit, match="below the newest tag v1.0.3"):
        stable_release.release_version((1, 0, 2), {(1, 0, 1), (1, 0, 3)})


def test_prepare_rewrites_only_the_project_version(tmp_path, monkeypatch):
    text = '[project]\nname = "je_auto_control"\nversion = "0.0.234"\n\n[tool.x]\nversion = "0.0.234"\n'
    (tmp_path / "pyproject.toml").write_text(text, encoding="utf-8")
    monkeypatch.setattr(stable_release, "released_tags", lambda root: {(0, 0, 234)})
    assert stable_release.prepare(tmp_path) == "0.0.235"
    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == text.replace("0.0.234", "0.0.235", 1)


def test_prepare_leaves_a_hand_set_version_alone(tmp_path, monkeypatch):
    text = '[project]\nversion = "1.0.0"\n'
    (tmp_path / "pyproject.toml").write_text(text, encoding="utf-8")
    monkeypatch.setattr(stable_release, "released_tags", lambda root: {(0, 0, 234)})
    assert stable_release.prepare(tmp_path) == "1.0.0"
    assert (tmp_path / "pyproject.toml").read_text(encoding="utf-8") == text


def test_prepare_refuses_a_pyproject_without_a_plain_version(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.0.0rc1"\n', encoding="utf-8")
    with pytest.raises(SystemExit, match="version line not found"):
        stable_release.prepare(tmp_path)


def test_released_tags_reads_the_release_tags_of_this_repository():
    tags = stable_release.released_tags(REPO_ROOT)
    assert all(len(tag) == 3 for tag in tags)


def test_main_reports_the_version_to_the_workflow(tmp_path, monkeypatch, capsys):
    (tmp_path / "pyproject.toml").write_text('[project]\nversion = "1.0.0"\n', encoding="utf-8")
    output = tmp_path / "github_output"
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(stable_release, "released_tags", lambda root: {(1, 0, 0)})
    assert stable_release.main() == 0
    assert capsys.readouterr().out == "new_version=1.0.1\n"
    assert output.read_text(encoding="utf-8") == "new_version=1.0.1\n"


def test_the_publish_job_takes_its_version_from_the_script_before_it_builds():
    job = WORKFLOW.read_text(encoding="utf-8").split("\n  publish:\n", 1)[1]
    assert "fetch-depth: 0" in job, "the script reads the tags, so the checkout has to fetch them"
    assert job.index("python scripts/stable_release.py") < job.index("python -m build") < job.index("twine upload")
    assert "steps.bump.outputs.new_version" in job


def test_the_publish_job_commits_only_when_the_version_changed():
    # A hand-set version leaves pyproject.toml as main has it; a bare `git commit` would fail there.
    job = WORKFLOW.read_text(encoding="utf-8").split("\n  publish:\n", 1)[1]
    assert "git diff --cached --quiet || git commit" in job
