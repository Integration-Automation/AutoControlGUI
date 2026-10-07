"""``dev.toml`` must describe the same package as ``pyproject.toml``, under another name.

Development metadata must preserve the requirements and entry points tested
under ``pyproject.toml``. A difference between the two ships a package nothing tested: an unpinned or unmarked
dependency, a missing extra, console script or pytest plugin entry point, or a wheel without its
package data (``py.typed``, the remote desktop web viewer).
"""
from pathlib import Path

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10, where pytest itself depends on tomli
    tomllib = pytest.importorskip("tomli")

REPO_ROOT = Path(__file__).resolve().parents[3]

# The [project] keys that decide what an install pulls in and exposes.
SAME_IN_BOTH = ("requires-python", "dependencies", "optional-dependencies",
                "scripts", "gui-scripts", "entry-points")


def _load(name: str) -> dict:
    with (REPO_ROOT / name).open("rb") as handle:
        return tomllib.load(handle)


STABLE = _load("pyproject.toml")
DEV = _load("dev.toml")


def test_the_two_packages_differ_by_name():
    assert STABLE["project"]["name"] == "je_auto_control"
    assert DEV["project"]["name"] == "je_auto_control_dev"


@pytest.mark.parametrize("key", SAME_IN_BOTH)
def test_the_dev_package_installs_and_exposes_what_the_stable_one_does(key):
    assert DEV["project"].get(key) == STABLE["project"].get(key), (
        f"[project] {key} differs: copy it from pyproject.toml into dev.toml")


def test_the_dev_wheel_is_built_the_same_way_and_ships_the_same_files():
    # Package discovery and package data decide which files reach the wheel.
    assert DEV["tool"]["setuptools"] == STABLE["tool"]["setuptools"]
    assert DEV["build-system"] == STABLE["build-system"]


def test_the_dev_version_is_a_plain_release_number():
    # Keep the development version in the same numeric format as the stable version.
    major, minor, patch = DEV["project"]["version"].split(".")
    assert (major + minor + patch).isdigit()
