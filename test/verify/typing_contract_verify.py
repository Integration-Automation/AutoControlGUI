"""Type-check the whole package on every platform it supports, against a shrinking list.

``quality.yml`` used to run ``mypy`` over two paths — ``je_auto_control/api`` and
``je_auto_control/utils/failure_bundle`` — and ``pyproject.toml`` carried a note
saying the rest were "analysed for signatures but not reported until they join
the contract". Nothing was ever going to move a module from *analysed* to
*reported*, because a scope written as an explicit path list only grows when a
human remembers to grow it, and a new module lands outside it by default.

So the scope is inverted here. mypy checks **the whole package**, and the
modules that do not pass yet are named in ``typing_contract_exempt.txt``. A new
module is therefore inside the contract the moment it is written, and the list
is the only thing standing between today's state and a fully typed package. It
may only shrink: this script fails if a listed module has started passing (go
delete the line) just as loudly as it fails if an unlisted one has stopped.

The other half of the widening is *where* the check runs. mypy resolves
``sys.platform`` branches against one target platform, so a Linux-only run never
looks inside the Windows, macOS or platform-gated code — three of this project's
four backends. Measured on this tree, that blind spot is real: 13 modules fail
only when the target is Linux and 3 only when it is Windows. This runs all three
targets and unions the results, so a listed module means "does not pass yet on
every supported platform" and a green run means the same thing on any developer
machine as it does on the Ubuntu runner.

Usage::

    python test/verify/typing_contract_verify.py          # check, exit 1 on drift
    python test/verify/typing_contract_verify.py --fix    # re-measure the list
"""

from __future__ import annotations

import argparse
import json
import subprocess  # nosec B404  # reason: runs mypy, a fixed dev-time argv with no shell
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "je_auto_control"
EXEMPT_FILE = Path(__file__).with_name("typing_contract_exempt.txt")

# mypy resolves `sys.platform` tests against a single target. The supported
# backends live behind those tests, so every target has to be asked separately.
PLATFORMS = ("win32", "linux", "darwin")

_HEADER = """\
# Modules that do not type-check cleanly yet.
#
# This is the shrink-only exemption list described in
# `typing_contract_verify.py`. mypy checks the whole package; everything named
# here is a module that was already failing when the gate widened to cover it.
#
# Rules:
#   * A module may leave this list (fix it, delete the line). That is the point.
#   * A module may not join it to make a red build green — fix the types, or
#     record why not in Progress.md.
#   * The list is measured, never hand-edited:
#         python test/verify/typing_contract_verify.py --fix
#
# "Does not type-check" means on at least one of the three targets mypy can be
# pointed at ({platforms}) — not just the one CI happens to run on.
#
# Measured entries: {count}
"""


def _module_name(relative_path: str) -> str:
    """Return the dotted module name for a package-relative source path."""
    parts = Path(relative_path).with_suffix("").parts
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _failing_modules(platform: str) -> set[str]:
    """Return the modules mypy reports errors in when targeting `platform`."""
    # The marker has to sit on the `subprocess.run(` line itself: Codacy honours
    # `nosemgrep` only on the exact line it reports, and the audit rule reports
    # the call, not the argument. See `je_auto_control/android/adb_client.py`
    # for the same shape.
    completed = subprocess.run(  # nosec B603  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit  # reason: argv is `sys.executable` plus literals and one value from the module-level PLATFORMS tuple; no shell, no environment, no caller input
        [sys.executable, "-m", "mypy", "--platform", platform, "-O", "json", PACKAGE],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    modules: set[str] = set()
    for line in completed.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            # mypy prints its "Found N errors" summary outside the JSON stream.
            continue
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("severity") != "error":
            continue
        path = str(record.get("file", "")).replace("\\", "/")
        if path.startswith(f"{PACKAGE}/") or path == f"{PACKAGE}.py":
            modules.add(_module_name(path))
    if not modules and completed.returncode not in (0, 1):
        raise SystemExit(
            f"mypy failed to run for --platform {platform} "
            f"(exit {completed.returncode}):\n{completed.stderr.strip()}"
        )
    return modules


def _measure() -> set[str]:
    """Return every module failing on at least one supported target platform."""
    failing: set[str] = set()
    for platform in PLATFORMS:
        found = _failing_modules(platform)
        print(f"  --platform {platform}: {len(found)} module(s) with errors")
        failing |= found
    return failing


def _read_exempt() -> set[str]:
    """Return the modules named in the committed exemption list."""
    if not EXEMPT_FILE.exists():
        return set()
    lines = EXEMPT_FILE.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def _write_exempt(modules: set[str]) -> None:
    """Rewrite the exemption list from a fresh measurement."""
    header = _HEADER.format(platforms=", ".join(PLATFORMS), count=len(modules))
    body = "".join(f"{module}\n" for module in sorted(modules))
    EXEMPT_FILE.write_text(f"{header}\n{body}", encoding="utf-8")


def _report(title: str, modules: list[str], advice: str) -> None:
    """Print one drift section."""
    print(f"\n{title} ({len(modules)}):")
    for module in modules:
        print(f"  {module}")
    print(f"  -> {advice}")


def main() -> int:
    """Compare the measured failures against the committed list."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="rewrite the exemption list from a fresh measurement",
    )
    args = parser.parse_args()

    print(f"Type-checking {PACKAGE} for {len(PLATFORMS)} target platforms...")
    failing = _measure()

    if args.fix:
        _write_exempt(failing)
        print(f"\nWrote {len(failing)} module(s) to {EXEMPT_FILE.name}. Review the diff.")
        return 0

    exempt = _read_exempt()
    regressed = sorted(failing - exempt)
    fixed = sorted(exempt - failing)

    if not regressed and not fixed:
        print(f"\nOK: {len(failing)} module(s) failing, all of them listed.")
        return 0

    if regressed:
        _report(
            "Modules failing that are not on the list",
            regressed,
            "fix the type errors; the list may not grow to make this pass",
        )
    if fixed:
        _report(
            "Modules on the list that now pass",
            fixed,
            "delete these lines: python test/verify/typing_contract_verify.py --fix",
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
