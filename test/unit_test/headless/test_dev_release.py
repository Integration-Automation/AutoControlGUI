"""``scripts/dev_release.py`` numbers and gates the ``je_auto_control_dev`` releases CI publishes.

A wrong version is refused by PyPI (a number is never reused) and a wrong comparison either
publishes on every push or never again, so both are pinned here without touching the network.
The last tests read ``.github/workflows/dev.yml``: the job that runs the script must publish only
a tested push to ``dev``, and must test it the way ``quality.yml`` tests ``main``.
"""
import importlib.util
import io
import re
import zipfile
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
SCRIPT = REPO_ROOT / "scripts" / "dev_release.py"
WORKFLOWS = REPO_ROOT / ".github" / "workflows"
SQUARE = re.compile(r"^\s*- \{ os: .+ \}\s*$", re.MULTILINE)


def _load_script():
    spec = importlib.util.spec_from_file_location("dev_release", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


dev_release = _load_script()


def _wheel(version: str, source: str = "VALUE = 1\n", requires: str = "mss==10.2.0") -> bytes:
    info = f"je_auto_control_dev-{version}.dist-info"
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("je_auto_control/__init__.py", source)
        archive.writestr(f"{info}/METADATA",
                         f"Name: je_auto_control_dev\nVersion: {version}\nRequires-Dist: {requires}\n")
        archive.writestr(f"{info}/RECORD", f"je_auto_control/__init__.py,sha256={version}\n")
        archive.writestr(f"{info}/WHEEL", f"Generator: setuptools ({version})\n")
        archive.writestr(f"{info}/licenses/LICENSE", "MIT\n")
    return buffer.getvalue()


@pytest.mark.parametrize("floor, released, expected", [
    ((0, 0, 135), {(0, 0, 135): None, (0, 0, 134): None}, "0.0.136"),
    ((0, 0, 135), {(0, 0, 140): None}, "0.0.141"),
    ((0, 1, 0), {(0, 0, 140): None}, "0.1.1"),
    ((0, 0, 135), {}, "0.0.136"),
])
def test_next_version_is_one_patch_above_the_floor_and_every_release(floor, released, expected):
    assert dev_release.next_version(floor, released) == expected


def test_published_keeps_plain_releases_and_their_wheels(monkeypatch):
    payload = (
        b'{"releases": {'
        b'"0.0.134": [{"packagetype": "sdist", "url": "https://files.pythonhosted.org/a.tar.gz"}],'
        b'"0.0.135": [{"packagetype": "sdist", "url": "https://files.pythonhosted.org/b.tar.gz"},'
        b' {"packagetype": "bdist_wheel", "url": "https://files.pythonhosted.org/b.whl"}],'
        b'"0.0.136.dev1": [{"packagetype": "bdist_wheel", "url": "https://files.pythonhosted.org/c.whl"}],'
        b'"0.0.133": []}}'
    )
    monkeypatch.setattr(dev_release, "fetch", lambda url: payload)
    assert dev_release.published("je_auto_control_dev") == {
        (0, 0, 134): None,
        (0, 0, 135): "https://files.pythonhosted.org/b.whl",
    }


def test_fetch_refuses_a_host_that_is_not_pypi():
    with pytest.raises(ValueError):
        dev_release.fetch("https://example.com/je_auto_control_dev.whl")


def test_prepare_writes_pyproject_from_dev_toml_with_the_next_version(tmp_path, monkeypatch):
    dev_toml = (REPO_ROOT / "dev.toml").read_text(encoding="utf-8")
    (tmp_path / "dev.toml").write_text(dev_toml, encoding="utf-8")
    asked = []
    monkeypatch.setattr(dev_release, "published", lambda name: asked.append(name) or {(9, 9, 9): None})

    assert dev_release.prepare(tmp_path) == "9.9.10"

    written = (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert asked == ["je_auto_control_dev"]
    assert written == dev_release.VERSION_LINE.sub(r'\g<1>"9.9.10"', dev_toml, count=1)
    assert written.count('version = "9.9.10"') == 1


def test_fingerprint_ignores_what_only_the_version_number_changes():
    assert dev_release.fingerprint(_wheel("0.0.135")) == dev_release.fingerprint(_wheel("0.0.136"))


@pytest.mark.parametrize("difference", [{"source": "VALUE = 2\n"}, {"requires": "mss==10.3.0"}])
def test_fingerprint_sees_changed_code_and_changed_metadata(difference):
    assert dev_release.fingerprint(_wheel("0.0.135")) != dev_release.fingerprint(
        _wheel("0.0.136", **difference))


@pytest.mark.parametrize("latest, expected", [
    ({}, True),
    ({"source": "VALUE = 0\n"}, True),
    ({"source": "VALUE = 1\n"}, False),
])
def test_changed_compares_the_built_wheel_with_the_newest_published_one(
        tmp_path, monkeypatch, latest, expected):
    (tmp_path / "je_auto_control_dev-0.0.136-py3-none-any.whl").write_bytes(_wheel("0.0.136"))
    url = "https://files.pythonhosted.org/je_auto_control_dev-0.0.135-py3-none-any.whl"
    released = {(0, 0, 134): "https://files.pythonhosted.org/old.whl", (0, 0, 135): url} if latest else {}
    monkeypatch.setattr(dev_release, "published", lambda name: released)
    monkeypatch.setattr(dev_release, "fetch", lambda asked: _wheel("0.0.135", **latest) if asked == url else b"")

    assert dev_release.changed(tmp_path) is expected


def test_changed_publishes_when_the_newest_release_has_no_wheel(tmp_path, monkeypatch):
    (tmp_path / "je_auto_control_dev-0.0.136-py3-none-any.whl").write_bytes(_wheel("0.0.136"))
    monkeypatch.setattr(dev_release, "published", lambda name: {(0, 0, 135): None})

    assert dev_release.changed(tmp_path) is True


def test_main_writes_the_result_where_the_workflow_reads_it(tmp_path, monkeypatch):
    output = tmp_path / "github_output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    monkeypatch.setattr(dev_release, "changed", lambda dist: False)

    assert dev_release.main(["changed", str(tmp_path)]) == 0
    assert output.read_text(encoding="utf-8") == "changed=false\n"
    assert dev_release.main(["publish"]) == 2


def _workflow(name: str) -> str:
    return (WORKFLOWS / name).read_text(encoding="utf-8")


def _publish_job() -> str:
    return re.split(r"^  publish-dev:\s*$", _workflow("dev.yml"), maxsplit=1, flags=re.MULTILINE)[1]


def _line_with(text: str, marker: str) -> str:
    found = {line.strip() for line in text.splitlines() if marker in line}
    assert len(found) == 1, f"expected one distinct line naming {marker}, got {sorted(found)}"
    return found.pop()


def test_the_workflow_runs_for_dev_and_nothing_else():
    triggers = _workflow("dev.yml").split("permissions:", 1)[0]
    assert re.findall(r"branches: \[ (.+) \]", triggers) == ['"dev"', '"dev"']
    assert "schedule" not in triggers


def test_the_workflow_publishes_only_a_tested_push_to_dev():
    job = _publish_job()
    assert "needs: [pytest-headless]" in job
    assert "if: github.event_name == 'push' && github.ref == 'refs/heads/dev'" in job


def test_the_workflow_uploads_only_a_changed_build_and_keeps_no_credentials():
    job = _publish_job()
    upload = job.index("twine upload")
    assert job.index("dev_release.py prepare") < job.index("python -m build --no-isolation") < upload
    assert job.index("dev_release.py changed dist") < upload
    assert job.index("git ls-remote origin refs/heads/dev") < upload
    assert "if: steps.compare.outputs.changed == 'true' && steps.tip.outputs.current == 'true'" in job
    assert "persist-credentials: false" in job


def test_dev_is_tested_the_way_main_is():
    dev, quality = _workflow("dev.yml"), _workflow("quality.yml")
    squares = {line.strip() for line in SQUARE.findall(dev)}
    assert squares, "dev.yml names no matrix square"
    assert squares <= {line.strip() for line in SQUARE.findall(quality)}
    assert _line_with(dev, "pytest==") == _line_with(quality, "pytest==")
    assert _line_with(dev, 'pip install -e "') == _line_with(quality, 'pip install -e "')
    assert "python -m pytest -v --tb=short --timeout=120" in dev


def test_the_dev_package_is_built_with_the_tooling_the_stable_one_is():
    # Both jobs install the same hash-locked file and build with the backend it pins
    # (test_publish_tooling_lock.py says what those two lines must be).
    job, stable = _publish_job(), _workflow("stable.yml")
    assert _line_with(job, "--require-hashes") == _line_with(stable, "--require-hashes")
    assert _line_with(job, "python -m build") == _line_with(stable, "python -m build")
