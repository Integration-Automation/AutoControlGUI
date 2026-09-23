"""The security lower bounds in ``pyproject.toml`` stay where they were raised.

Each bound excludes versions with a known vulnerability in code this package
runs: lowering one silently re-admits it for anyone installing that extra.
"""
import pathlib
import re

import pytest

tomllib = pytest.importorskip("tomllib")

_PYPROJECT = pathlib.Path(__file__).resolve().parents[3] / "pyproject.toml"

#: requirement name -> (minimum version, why).
_FLOORS = {
    "cryptography": ("48.0.1", "GHSA-537c-gmf6-5ccf"),
    "starlette": ("1.0.1", "CVE-2026-48710, Host-header path confusion (signaling server)"),
    "zeroconf": ("0.149.16", "CVE-2026-47180 and siblings, mDNS memory / CPU exhaustion (discovery)"),
}


def _requirements():
    project = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))["project"]
    yield from project.get("dependencies", [])
    for extra in project.get("optional-dependencies", {}).values():
        yield from extra


def _version(text):
    return tuple(int(part) for part in re.findall(r"\d+", text))


@pytest.mark.parametrize("name", sorted(_FLOORS))
def test_the_security_floor_holds(name):
    minimum, reason = _FLOORS[name]
    bounds = [re.search(r">=\s*([\d.]+)", requirement)
              for requirement in _requirements()
              if re.match(rf"{name}\b", requirement)]
    assert bounds, f"{name} is no longer a requirement; drop its floor here"
    for bound in bounds:
        assert bound and _version(bound.group(1)) >= _version(minimum), (
            f"{name} must be >= {minimum} ({reason})")
