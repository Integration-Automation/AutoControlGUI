"""Retain CI child output and Linux native backtraces while preserving failing exits."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from importlib import metadata
import json
import os
from pathlib import Path
import shutil
import subprocess  # nosec B404  # reason: intentional child-process CI runner
import sys
import time
from typing import Sequence


def _debugger_command(command: Sequence[str], debugger: str) -> list[str]:
    """Use batch GDB without user initialization; ordinary child exits remain failures."""
    return [debugger, '-nx', '-batch', '-return-child-result',
            '-ex', 'set print thread-events off',
            '-ex', 'set startup-with-shell off',
            '-ex', 'handle SIGPIPE nostop noprint pass',
            '-ex', 'run', '-ex', 'thread apply all bt', '--args', *command]


def _versions() -> dict[str, str]:
    packages = {}
    for name in ('PySide6', 'shiboken6', 'av', 'aiortc', 'pytest', 'coverage'):
        try:
            packages[name] = metadata.version(name)
        except metadata.PackageNotFoundError:
            packages[name] = 'not installed'
    return packages


def run(command: Sequence[str], directory: Path, *, native: bool = False) -> int:
    """Stream merged child output to CI and a retained file; never convert failure into success."""
    directory.mkdir(parents=True, exist_ok=True)
    debugger = shutil.which('gdb') if native else None
    if native and debugger is None:
        raise RuntimeError('native diagnostics requires gdb; install it before running the suite')
    actual = _debugger_command(command, debugger) if debugger else list(command)
    record: dict[str, object] = {
        'command': list(command), 'python': sys.version, 'platform': sys.platform,
        'packages': _versions(), 'debugger': debugger,
        'started': datetime.now(timezone.utc).isoformat(),
    }
    report = directory / 'runtime.json'
    report.write_text(json.dumps(record, indent=2), encoding='utf-8')
    environment = dict(os.environ, PYTHONFAULTHANDLER='1', PYTHONUNBUFFERED='1')
    started = time.monotonic()
    with (directory / 'process.log').open('w', encoding='utf-8') as output:
        with subprocess.Popen(  # nosec B603  # reason: explicit CI child argv; shell remains disabled
            actual, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            env=environment, text=True, encoding='utf-8', errors='replace',
        ) as child:
            if child.stdout is None:
                raise RuntimeError('child output pipe was not created')
            for line in child.stdout:
                output.write(line)
                output.flush()
                sys.stdout.write(line)
                sys.stdout.flush()
            result = child.wait()
    record.update(returncode=result, elapsed_seconds=round(time.monotonic() - started, 3))
    report.write_text(json.dumps(record, indent=2), encoding='utf-8')
    return result if result >= 0 else 128 - result


def main(argv: Sequence[str] | None = None) -> int:
    """Run the explicitly supplied CI command with optional Linux native diagnostics."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--artifact-dir', type=Path, required=True)
    parser.add_argument('--native', action='store_true')
    parser.add_argument('command', nargs=argparse.REMAINDER)
    options = parser.parse_args(argv)
    command = options.command[1:] if options.command[:1] == ['--'] else options.command
    if not command:
        parser.error('an explicit child command is required after --')
    return run(command, options.artifact_dir, native=options.native)


if __name__ == '__main__':
    raise SystemExit(main())
