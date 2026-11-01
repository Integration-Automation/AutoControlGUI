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

``--extras`` is the same measurement with one thing changed. The contract above
forces every optional third-party module to ``Any`` (``follow_imports = "skip"``
in ``pyproject.toml``), so that its verdict cannot depend on which extras are
installed -- which also means a call into PySide6 or aiortc is never checked
against that library's real signatures. ``--extras`` drops PySide6, aiortc and
av from that override (nothing else changes), requires them to be installed,
and compares what fails against its own shrink-only list,
``typing_extras_exempt.txt``. The two lists answer different questions and are
kept apart: "is our own code consistent" is empty and stays empty; "is it
consistent with Qt's and aiortc's types" starts at what was measured the day
the question was first asked.

Usage::

    python test/verify/typing_contract_verify.py                   # check, exit 1 on drift
    python test/verify/typing_contract_verify.py --fix             # re-measure the list
    python test/verify/typing_contract_verify.py --extras          # the same against real Qt / aiortc types
    python test/verify/typing_contract_verify.py --extras --fix
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess  # nosec B404  # reason: runs mypy, a fixed dev-time argv with no shell
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PACKAGE = "je_auto_control"
# Top-level modules the distribution ships beside the package (`py-modules` in
# `pyproject.toml`). They are installed and imported like the package, so they
# are checked like it; a path list that only named the package left the pytest
# plugin outside the contract without anyone having decided that.
EXTRA_MODULES = ("je_auto_control_pytest.py",)
EXEMPT_FILE = Path(__file__).with_name("typing_contract_exempt.txt")

# mypy resolves `sys.platform` tests against a single target. The supported
# backends live behind those tests, so every target has to be asked separately.
PLATFORMS = ("win32", "linux", "darwin")

# `--extras`: the lines of the "forced to Any" override in `pyproject.toml` that
# are dropped, and the distributions that must then be importable. The lines are
# matched as text on purpose -- a reworded override makes this script stop with
# a message instead of quietly measuring the ordinary contract a second time.
EXTRAS_EXEMPT_FILE = Path(__file__).with_name("typing_extras_exempt.txt")
EXTRAS_OVERRIDE_LINES = (
    '    "PySide6", "PySide6.*",\n',
    '    "aiortc", "aiortc.*", "av", "av.*",\n',
)
EXTRAS_PACKAGES = ("PySide6", "aiortc", "av")

_EXTRAS_HEADER = """\
# Modules that do not type-check against the real PySide6 / aiortc / av types.
#
# The shrink-only list of `typing_contract_verify.py --extras`. The ordinary
# contract treats those three libraries as `Any`; this run does not, and these
# are the modules that were already inconsistent with the libraries' own
# signatures when the question was first asked (mixins that call methods of the
# widget they are mixed into, `QLayout | None` used unguarded, and the like).
#
# Rules: the same as `typing_contract_exempt.txt`. A module may leave; it may
# not join; the list is measured, never hand-edited:
#         python test/verify/typing_contract_verify.py --extras --fix
# Measure with the versions the `typing-extras` job of `quality.yml` pins.
#
# Targets: {platforms}
# Measured entries: {count}
"""

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


def _missing_extras() -> list[str]:
    """Return the libraries `--extras` checks against that are not installed."""
    return [name for name in EXTRAS_PACKAGES if importlib.util.find_spec(name) is None]


def _extras_config(directory: Path) -> Path:
    """Write `pyproject.toml` minus the PySide6 / aiortc / av override lines; return the copy."""
    missing = _missing_extras()
    if missing:
        raise SystemExit(
            f"--extras needs {', '.join(missing)} installed: pip install -e .[gui,webrtc]")
    text = (REPO_ROOT / "pyproject.toml").read_text(encoding="utf-8")
    for line in EXTRAS_OVERRIDE_LINES:
        if text.count(line) != 1:
            raise SystemExit(
                f"pyproject.toml no longer holds the override line {line.strip()!r}; "
                "update EXTRAS_OVERRIDE_LINES in this script to match")
        text = text.replace(line, "")
    config = directory / "pyproject.toml"
    config.write_text(text, encoding="utf-8")
    return config


def _failing_modules(platform: str, config: Path | None = None) -> set[str]:
    """Return the modules mypy reports errors in when targeting `platform`."""
    options = [] if config is None else ["--config-file", str(config)]
    # The marker has to sit on the `subprocess.run(` line itself: Codacy honours
    # `nosemgrep` only on the exact line it reports, and the audit rule reports
    # the call, not the argument. See `je_auto_control/android/adb_client.py`
    # for the same shape.
    completed = subprocess.run(  # nosec B603  # nosemgrep: python.lang.security.audit.dangerous-subprocess-use-audit.dangerous-subprocess-use-audit  # reason: argv is `sys.executable` plus literals and values from the module-level PLATFORMS / EXTRA_MODULES tuples; no shell, no environment, no caller input
        [sys.executable, "-m", "mypy", *options, "--platform", platform, "-O", "json", PACKAGE, *EXTRA_MODULES],
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
        if path.startswith(f"{PACKAGE}/") or path in (f"{PACKAGE}.py", *EXTRA_MODULES):
            modules.add(_module_name(path))
    if not modules and completed.returncode not in (0, 1):
        raise SystemExit(
            f"mypy failed to run for --platform {platform} "
            f"(exit {completed.returncode}):\n{completed.stderr.strip()}"
        )
    return modules


def _measure(config: Path | None = None) -> set[str]:
    """Return every module failing on at least one supported target platform."""
    failing: set[str] = set()
    for platform in PLATFORMS:
        found = _failing_modules(platform, config)
        print(f"  --platform {platform}: {len(found)} module(s) with errors")
        failing |= found
    return failing


def _read_exempt(exempt_file: Path = EXEMPT_FILE) -> set[str]:
    """Return the modules named in a committed exemption list."""
    if not exempt_file.exists():
        return set()
    lines = exempt_file.read_text(encoding="utf-8").splitlines()
    return {line.strip() for line in lines if line.strip() and not line.startswith("#")}


def _write_exempt(modules: set[str], exempt_file: Path = EXEMPT_FILE, header: str = _HEADER) -> None:
    """Rewrite an exemption list from a fresh measurement."""
    heading = header.format(platforms=", ".join(PLATFORMS), count=len(modules))
    body = "".join(f"{module}\n" for module in sorted(modules))
    exempt_file.write_text(f"{heading}\n{body}", encoding="utf-8")


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
    parser.add_argument(
        "--extras",
        action="store_true",
        help="check against the real PySide6 / aiortc / av types (they must be installed)",
    )
    args = parser.parse_args()

    exempt_file, header = (EXTRAS_EXEMPT_FILE, _EXTRAS_HEADER) if args.extras else (EXEMPT_FILE, _HEADER)
    against = f", against the real {' / '.join(EXTRAS_PACKAGES)} types" if args.extras else ""
    print(f"Type-checking {PACKAGE} (+ {', '.join(EXTRA_MODULES)}) "
          f"for {len(PLATFORMS)} target platforms{against}...")
    with tempfile.TemporaryDirectory(prefix="typing-extras-") as scratch:
        failing = _measure(_extras_config(Path(scratch)) if args.extras else None)

    if args.fix:
        _write_exempt(failing, exempt_file, header)
        print(f"\nWrote {len(failing)} module(s) to {exempt_file.name}. Review the diff.")
        return 0

    exempt = _read_exempt(exempt_file)
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
            "delete these lines: python test/verify/typing_contract_verify.py"
            f"{' --extras' if args.extras else ''} --fix",
        )
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
