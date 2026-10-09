"""Release helper for the stable channel, ``je_auto_control`` on PyPI.

The ``publish`` job of ``.github/workflows/stable.yml`` runs ``python scripts/stable_release.py``
before it builds. The script decides which version that push to ``main`` releases and writes it to
``pyproject.toml``:

* the version ``pyproject.toml`` declares already has a ``v<version>`` tag: one patch above it,
  which is every ordinary merge;
* it has no tag yet: that version as written. This is how a minor or major release is made --
  set the version in ``pyproject.toml`` in the pull request that should ship it. It must be above
  every tag, since PyPI never takes a number twice and a lower one would not be the newest.

It prints ``new_version=X.Y.Z`` and appends the same line to ``$GITHUB_OUTPUT``.
"""
from __future__ import annotations

import os
import re
import subprocess  # nosec B404  # reason: runs the fixed command `git tag --list` and nothing else
import sys
from pathlib import Path

Version = tuple[int, int, int]

VERSION_LINE = re.compile(r'^(version\s*=\s*)"(\d+)\.(\d+)\.(\d+)"', re.MULTILINE)
TAG = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def as_version(parts: tuple[str, ...]) -> Version:
    """Turn the three captured number strings of a version into a comparable tuple."""
    major, minor, patch = (int(part) for part in parts)
    return major, minor, patch


def released_tags(root: Path) -> set[Version]:
    """Return the versions that have a ``vX.Y.Z`` tag in the repository at ``root``."""
    listing = subprocess.run(  # nosec B603 B607  # reason: fixed argv, git from the runner's PATH
        ["git", "tag", "--list", "v*"], cwd=root, check=True, capture_output=True, text=True, timeout=60,
    ).stdout
    found = (TAG.match(line.strip()) for line in listing.splitlines())
    return {as_version(match.groups()) for match in found if match}


def release_version(declared: Version, tags: set[Version]) -> Version:
    """Return the version to release: ``declared`` when it is untagged, else one patch above it."""
    if declared in tags:
        major, minor, patch = declared
        return major, minor, patch + 1
    newest = max(tags, default=None)
    if newest is not None and declared < newest:
        raise SystemExit(
            "pyproject.toml declares {0}.{1}.{2}, which has no tag and is below the newest tag "
            "v{3}.{4}.{5}".format(*declared, *newest))
    return declared


def prepare(root: Path) -> str:
    """Write the version to release into ``pyproject.toml`` under ``root`` and return it."""
    path = root / "pyproject.toml"
    text = path.read_text(encoding="utf-8")
    line = VERSION_LINE.search(text)
    if line is None:
        raise SystemExit("version line not found in pyproject.toml")
    version = "{0}.{1}.{2}".format(*release_version(as_version(line.groups()[1:]), released_tags(root)))
    path.write_text(VERSION_LINE.sub(rf'\g<1>"{version}"', text, count=1), encoding="utf-8", newline="\n")
    return version


def main() -> int:
    """Prepare the checkout in the current directory; return the process exit code."""
    line = f"new_version={prepare(Path.cwd())}"
    print(line)
    output = os.environ.get("GITHUB_OUTPUT")
    if output:
        with open(output, "a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
