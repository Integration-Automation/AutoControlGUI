"""Run a CI test process under gdb/lldb, retaining native frames and its actual exit status."""
from __future__ import annotations

import argparse
import importlib.metadata
import json
import math
import os
from pathlib import Path
import platform
import shutil
import signal
import subprocess  # nosec B404  # reason: explicit CI test/debugger argv, never a shell command.
import sys
from typing import Optional, Sequence

_MAX_LOG_BYTES = 64 * 1024 * 1024


def _gdb_script(status: Path) -> str:
    return f'''set pagination off
set confirm off
set print thread-events off
set detach-on-fork on
handle SIGPIPE nostop noprint pass
run
python
import gdb
code = gdb.parse_and_eval("$_exitcode")
if code.type.code == gdb.TYPE_CODE_VOID:
    gdb.execute("thread apply all bt 50")
    gdb.execute("info sharedlibrary")
    try:
        native_signal = int(gdb.parse_and_eval("$_siginfo.si_signo"))
    except gdb.error:
        native_signal = 11
    code = 128 + native_signal
    gdb.execute("continue")
else:
    code = int(code)
with open({str(status)!r}, "w", encoding="ascii") as report:
    report.write(str(code))
gdb.execute("quit " + str(code))
end
'''


def _lldb_script(status: Path) -> str:
    return f'''settings set target.disable-aslr false
settings set target.process.stop-on-exec false
settings set stop-disassembly-count 0
settings set auto-confirm true
process handle SIGPIPE -n false -p true -s false
run
script process = lldb.debugger.GetSelectedTarget().GetProcess()
script exited = process.GetState() == lldb.eStateExited
script thread = process.GetSelectedThread()
script fatal_stop = thread.GetStopReason() in (lldb.eStopReasonSignal, lldb.eStopReasonException)
script native_signal = thread.GetStopReasonDataAtIndex(0) if thread.GetStopReason() == lldb.eStopReasonSignal else 11
script code = process.GetExitStatus() if exited else (128 + native_signal if fatal_stop else None)
script lldb.debugger.HandleCommand("thread backtrace all") if not exited else None
script lldb.debugger.HandleCommand("image list") if not exited else None
script report = open({str(status)!r}, "w", encoding="ascii") if code is not None else None
script report.write(str(code)) if report is not None else None
script report.close() if report is not None else None
script process.Kill() if not exited else None
quit
'''


def _debugger_command(command: Sequence[str], output: Path, target_platform: str) -> list[str]:
    name = 'gdb' if target_platform == 'linux' else 'lldb'
    executable = shutil.which(name)
    if executable is None:
        raise RuntimeError(f'{name} is required for native CI diagnostics')
    script = output / (name + '.commands')
    status = output / 'target-exit.txt'
    script.write_text(_gdb_script(status) if name == 'gdb' else _lldb_script(status), encoding='utf-8')
    if name == 'gdb':
        return [executable, '-nx', '--batch', '-x', str(script), '--args', *command]
    return [executable, '--no-lldbinit', '--batch', '--source', str(script), '--', *command]


def _terminate(process: subprocess.Popen[bytes]) -> None:
    if os.name == 'posix':
        os.killpg(process.pid, signal.SIGTERM)  # pylint: disable=no-member  # POSIX-only branch.
    else:
        process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        if os.name == 'posix':
            os.killpg(process.pid, signal.SIGKILL)  # pylint: disable=no-member  # POSIX-only branch.
        else:
            process.kill()
        process.wait(timeout=5)


def _trim_log(path: Path) -> None:
    if path.stat().st_size <= _MAX_LOG_BYTES:
        return
    with path.open('rb') as source:
        source.seek(-_MAX_LOG_BYTES, os.SEEK_END)
        tail = source.read()
    path.write_bytes(b'[native diagnostic log truncated; retained final 64 MiB]\n' + tail)


def _target_exit(path: Path) -> Optional[int]:
    try:
        with path.open('rb') as report:
            value = report.read(129)
        code = int(value)
    except (OSError, ValueError):
        return None
    return code if len(value) <= 128 and 0 <= code <= 255 else None


def _versions() -> dict[str, str]:
    versions = {}
    for package in ('PySide6', 'shiboken6', 'pytest', 'coverage'):
        try:
            versions[package] = importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:
            versions[package] = 'absent'
    return versions


def _write_report(output: Path, command: Sequence[str], state: str,
                  target_exit: Optional[int], debugger_exit: int, result: int) -> None:
    metadata = {'state': state, 'target_exit': target_exit, 'debugger_exit': debugger_exit,
                'result': result, 'command': list(command), 'python': sys.version,
                'platform': platform.platform(), 'versions': _versions()}
    (output / 'run.json').write_text(json.dumps(metadata, indent=2), encoding='utf-8')
    log = output / 'native-debugger.log'
    with log.open('rb') as transcript:
        transcript.seek(max(0, log.stat().st_size - 32768))
        print(transcript.read().decode('utf-8', errors='replace'))


def run_diagnostic(command: Sequence[str], output: Path, *, target_platform: str,
                   timeout_s: float = 1800) -> int:
    """Preserve target failure, reject missing exit evidence and bound debugger execution."""
    if target_platform not in ('linux', 'darwin') or not command:
        raise ValueError('native diagnostics require a Linux/macOS target and a command')
    if not math.isfinite(timeout_s) or not 0 < timeout_s <= 3600:
        raise ValueError('native diagnostic timeout must be within (0, 3600] seconds')
    output = output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    status = output / 'target-exit.txt'
    status.unlink(missing_ok=True)
    argv = _debugger_command(command, output, target_platform)
    log = output / 'native-debugger.log'
    state = 'complete'
    with log.open('wb') as transcript:
        # reason: explicit CI debugger/test argv, shell=False; this tool intentionally runs the supplied target.
        with subprocess.Popen(argv, stdout=transcript, stderr=subprocess.STDOUT,  # nosec B603
                              env={**os.environ, 'PYTHONFAULTHANDLER': '1'},
                              start_new_session=os.name == 'posix') as process:
            try:
                debugger_exit = process.wait(timeout=timeout_s)
            except subprocess.TimeoutExpired:
                _terminate(process)
                debugger_exit, state = 124, 'timeout'
    _trim_log(log)
    target_exit = _target_exit(status)
    if state == 'timeout':
        result = 124
    elif target_exit is None:
        result, state = 1, 'debugger_error'
    else:
        result = target_exit if target_exit else debugger_exit
    _write_report(output, command, state, target_exit, debugger_exit, result)
    return result


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Wrap the unchanged coverage/pytest command and retain native diagnostic artifacts."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=Path('native-diagnostics'))
    parser.add_argument('--timeout', type=float, default=1800)
    parser.add_argument('command', nargs=argparse.REMAINDER)
    args = parser.parse_args(argv)
    command = args.command[1:] if args.command[:1] == ['--'] else args.command
    return run_diagnostic(command, args.output, target_platform=sys.platform, timeout_s=args.timeout)


if __name__ == '__main__':
    raise SystemExit(main())
