"""The Windows arm64 dependency markers must stay exactly as measured. No Qt.

`opencv-python` and `cryptography` publish no `win_arm64` wheel, so
`pip install` used to fail on Windows arm64 before a single line of this
package ran — pip built OpenCV from source and CMake could not configure for
ARM64. Nothing in the package imports either one at import time, so the whole
blocker lived in `pyproject.toml`'s dependency list, and a PEP 508 marker is
the entire fix.

Three things can silently undo it, and each has a test here:

1. Dropping the marker from one of the three requirements. `je_open_cv` is the
   easy one to miss — it is pure Python, but it depends on `opencv-python`, so
   an unmarked `je_open_cv` drags OpenCV back in through the side door.
2. Writing a marker that does not mean what it looks like. PEP 508 has no
   boolean `not`, so the condition is spelled `A or B`; getting that wrong
   silently excludes far more than one platform.
3. Marking a package that was never a blocker. Pillow was named as one for a
   while and is not: it has always shipped `win_arm64` wheels. Marking it off
   would cost Windows arm64 screenshots for no reason at all.

pip evaluates markers against the *running* interpreter — `--platform` only
changes wheel-compatibility tags — so a local dry-run cannot prove any of
this. Evaluating the marker directly can, and does not need the runner.
"""
import pathlib
import re
from typing import Dict, List

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[3]

# The one marker, spelled exactly as pyproject.toml spells it.
ARM64_MARKER = "sys_platform != 'win32' or platform_machine != 'ARM64'"

# Absent from Windows arm64 because upstream publishes no wheel there.
MARKED = ("je_open_cv", "opencv-python", "cryptography")

# Present everywhere, including Windows arm64. Pillow is on this list on
# purpose: it was once named a blocker and never was one.
UNMARKED = ("pillow", "mss", "defusedxml")

# A marker that names the platform. A Python-version marker is not one.
_PLATFORM_MARKER = re.compile(r"\b(sys_platform|platform_machine|platform_system|os_name)\b")

ENVIRONMENTS: Dict[str, Dict[str, str]] = {
    "windows arm64": {
        "sys_platform": "win32", "platform_machine": "ARM64",
        "platform_system": "Windows",
    },
    "windows x86-64": {
        "sys_platform": "win32", "platform_machine": "AMD64",
        "platform_system": "Windows",
    },
    "linux arm64": {
        "sys_platform": "linux", "platform_machine": "aarch64",
        "platform_system": "Linux",
    },
    "macos arm64": {
        "sys_platform": "darwin", "platform_machine": "arm64",
        "platform_system": "Darwin",
    },
    "freebsd x86-64": {
        "sys_platform": "freebsd14", "platform_machine": "amd64",
        "platform_system": "FreeBSD",
    },
}


def _dependencies() -> List[str]:
    """Return the project's required dependencies, verbatim.

    Read with a small regex rather than `tomllib`: the dependency list is all
    this needs.
    """
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    block = re.search(r"^dependencies = \[(.*?)^\]", text, re.S | re.M)
    assert block is not None, "pyproject.toml has no top-level dependencies array"
    found: List[str] = []
    for line in block.group(1).splitlines():
        quoted = re.match(r'"([^"]+)"', line.strip())
        if quoted is not None:
            found.append(quoted.group(1))
    assert found, "parsed no dependencies; the array format must have changed"
    return found


def _requirements(name: str) -> List[str]:
    """Return every requirement string whose distribution is ``name``."""
    prefix = name.lower()
    return [
        text for text in _dependencies()
        if text.lower().split(";")[0].strip()
        .replace("_", "-").startswith(prefix.replace("_", "-"))
    ]


def _requirement(name: str) -> str:
    """Return the single requirement string whose distribution is ``name``."""
    matches = _requirements(name)
    assert len(matches) == 1, f"{name}: expected one requirement, got {matches}"
    return matches[0]


@pytest.mark.parametrize("name", MARKED)
def test_the_unavailable_wheels_are_marked_off_windows_arm64(name: str) -> None:
    """Each of the three carries the arm64 marker, spelled the one way."""
    requirement = _requirement(name)
    assert ";" in requirement, (
        f"{name} lost its environment marker. Without it, pip resolves "
        f"{name} on Windows arm64, where no wheel exists, and the install "
        f"fails before any of this package runs."
    )
    marker = requirement.split(";", 1)[1].strip()
    assert marker == ARM64_MARKER, (
        f"{name} carries {marker!r}, not the shared arm64 marker "
        f"{ARM64_MARKER!r}. Keep one spelling so all three move together."
    )


@pytest.mark.parametrize("name", UNMARKED)
def test_the_available_wheels_are_not_marked_off_anything(name: str) -> None:
    """Pillow, mss and defusedxml ship for arm64 and carry no platform marker.

    A requirement may be split by Python version, but no line may depend on
    the platform.
    """
    requirements = _requirements(name)
    assert requirements, f"{name} is missing from the dependencies"
    for requirement in requirements:
        marker = requirement.split(";", 1)[1] if ";" in requirement else ""
        assert not _PLATFORM_MARKER.search(marker), (
            f"{name} was marked off a platform ({requirement!r}), but it "
            f"publishes a win_arm64 wheel and was never a blocker. Marking it "
            f"costs that platform a working feature for nothing."
        )


def test_a_platform_marker_on_an_unmarked_package_is_caught() -> None:
    """The check above sees platform names and lets Python versions through."""
    assert _PLATFORM_MARKER.search(ARM64_MARKER)
    assert _PLATFORM_MARKER.search("platform_system=='Darwin'")
    assert not _PLATFORM_MARKER.search("python_version >= '3.11'")


@pytest.mark.parametrize("label,environment", sorted(ENVIRONMENTS.items()))
def test_the_marker_excludes_exactly_one_platform(
        label: str, environment: Dict[str, str]) -> None:
    """Windows arm64 loses the three; every other platform keeps them."""
    markers = pytest.importorskip(
        "packaging.markers",
        reason="packaging is not installed; the spelling test still guards this",
    )
    wanted = label != "windows arm64"
    for name in MARKED:
        requirement = _requirement(name)
        marker = markers.Marker(requirement.split(";", 1)[1].strip())
        assert marker.evaluate(environment) is wanted, (
            f"on {label}, {name} evaluates to {not wanted} — expected "
            f"{wanted}. The marker excludes the wrong set of platforms."
        )
