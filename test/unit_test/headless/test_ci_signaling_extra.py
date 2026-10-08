"""CI installs the ``[signaling]`` extra, so the signaling-server tests run there.

Every test of ``utils/remote_desktop/signaling_server.py`` begins with
``pytest.importorskip("fastapi")``. While the headless job installed only
``.[webrtc]`` they were skipped on every square: the server half of config
sync (revision checks, operation ids, account isolation, the body guard) was
exercised on developer machines and nowhere else.

Read from the files as text; nothing is installed.
"""
import re
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_WORKFLOWS = ("quality.yml", "dev.yml")
#: What the server tests import: the extra's three packages, and httpx,
#: which ``fastapi.testclient`` needs and the extra does not.
_PINNED = ("fastapi", "starlette", "uvicorn", "httpx")


def _workflow(name: str) -> str:
    return (_REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


def _one_line(text: str, marker: str, also: str = "") -> str:
    """The one line naming ``marker`` (and ``also``: other jobs install things too)."""
    found = {line.strip() for line in text.splitlines() if marker in line and also in line}
    assert len(found) == 1, f"expected one distinct line naming {marker}, got {sorted(found)}"
    return found.pop()


def _extra(name: str) -> list:
    text = (_REPO_ROOT / name).read_text(encoding="utf-8")
    line = _one_line(text, "signaling = [")
    return re.findall(r'"([A-Za-z0-9_.-]+)[^"]*"', line)


@pytest.mark.parametrize("name", _WORKFLOWS)
def test_the_headless_job_installs_the_signaling_extra(name):
    # The headless job is the one that installs the WebRTC extra without the GUI one.
    install = _one_line(_workflow(name), 'pip install -e ".[webrtc')
    extras = re.search(r'pip install -e "\.\[([^\]]+)\]"', install)
    assert extras is not None, install
    assert {"webrtc", "signaling"} <= set(extras.group(1).split(","))


@pytest.mark.parametrize("name", _WORKFLOWS)
def test_what_the_server_tests_import_is_pinned_exactly(name):
    tooling = _one_line(_workflow(name), "pytest==", also="coverage==")
    for package in _PINNED:
        assert re.search(rf"\b{package}==\d+(\.\d+)+\b", tooling), (
            f"{name}: {package} is not pinned on the test tooling line")


def test_the_pins_cover_everything_the_extra_declares():
    for name in ("pyproject.toml", "dev.toml"):
        assert set(_extra(name)) <= set(_PINNED), name


def test_the_pinned_starlette_is_past_the_host_header_fix():
    # CVE-2026-48710: the floor in the extra is 1.0.1.
    pinned = re.search(r"starlette==(\d+)\.(\d+)\.(\d+)",
                       _one_line(_workflow("quality.yml"), "pytest==", also="coverage=="))
    assert pinned is not None
    assert tuple(int(part) for part in pinned.groups()) >= (1, 0, 1)
