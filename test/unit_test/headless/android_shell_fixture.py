"""Execute reviewed Android command scripts against test-owned POSIX functions and files only."""
import os
from pathlib import Path
import shutil
import subprocess
import threading
import time

import pytest

_HARNESS = '''
fixture_read_file() {
    if [ -n "${BASH_VERSION-}" ] && [ -f "$1" ] && [ -r "$1" ]; then
        local fixture_chunk
        while IFS= read -r -d '' fixture_chunk; do
            printf '%s\\000' "$fixture_chunk" || return
        done < "$1" || return
        printf '%s' "$fixture_chunk"
    else
        command cat "$1"
    fi
}
fixture_getprop() { fixture_read_file "$FIXTURE_DIR/device"; }
fixture_cat() { fixture_read_file "$FIXTURE_DIR/boot"; }
fixture_dumpsys() {
    if [ "$1" = input ]; then fixture_read_file "$FIXTURE_DIR/input";
    elif [ "$2" = policy ]; then fixture_read_file "$FIXTURE_DIR/policy";
    else fixture_read_file "$FIXTURE_DIR/wm"; fi
}
fixture_input() {
    printf '%s\\n' "$@" >> "$FIXTURE_DIR/actions"
    for field in device boot; do
        if [ -f "$FIXTURE_DIR/after-$field" ]; then
            command cat "$FIXTURE_DIR/after-$field" > "$FIXTURE_DIR/$field"
        fi
    done
    if [ -f "$FIXTURE_DIR/after" ]; then command cat "$FIXTURE_DIR/after" > "$FIXTURE_DIR/wm"; fi
    if [ -f "$FIXTURE_DIR/after_hierarchy.xml" ]; then
        command cat "$FIXTURE_DIR/after_hierarchy.xml" > "$FIXTURE_DIR/hierarchy.xml"
    fi
    if [ -f "$FIXTURE_DIR/fail" ]; then return 1; fi
}
'''


class AndroidShellFixture:
    """An installed sh runs compiled scripts while every Android executable is replaced by a fixture."""

    def __init__(self, directory, snapshot):
        self.directory = directory
        self._timings = []
        self._timing_lock = threading.Lock()
        self.shell = shutil.which('sh')
        if self.shell is None and os.name == 'nt' and (git := shutil.which('git')):
            candidate = Path(git).parent.parent / 'bin/sh.exe'
            self.shell = str(candidate) if candidate.is_file() else None
        if self.shell is None:
            pytest.skip('actual shell contract needs an installed POSIX sh')
        wm = f'  mTopFocusedDisplayId=0\n  mCurrentFocus={snapshot.window}\n  mFocusedApp={snapshot.activity}\n'
        for name, value in (('device', snapshot.physical_id + '\n'), ('boot', snapshot.boot_id + '\n'), ('wm', wm)):
            (directory / name).write_text(value, encoding='utf-8', newline='')

    def run(self, script):
        phase = ('action' if '/system/bin/input -d 0 ' in script else
                 'input_probe' if '__JE_ANDROID_INPUT_V1__' in script else 'identity')
        for tool in ('getprop', 'cat', 'dumpsys', 'input'):
            script = script.replace('/system/bin/' + tool, 'fixture_' + tool)
        for tool in ('printf', 'sed', 'cut'):
            script = script.replace('/system/bin/' + tool, tool)
        # macOS ships shasum, not sha256sum; both print "<hex>  -".
        digest = 'sha256sum' if shutil.which('sha256sum') or not shutil.which('shasum') else 'shasum -a 256'
        script = script.replace('/system/bin/sha256sum', digest)
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
        started = time.monotonic()
        event = {'phase': phase, 'started': started, 'outcome': 'running'}
        with self._timing_lock:
            self._timings.append(event)
        try:
            result = subprocess.run([self.shell, '-c', _HARNESS + script], capture_output=True, timeout=5,
                                    env={**os.environ, 'FIXTURE_DIR': self.directory.as_posix()}, cwd=self.directory,
                                    creationflags=flags, check=False)
        except subprocess.TimeoutExpired:
            self._settle(event, 'timeout')
            raise AssertionError(f'Android fixture {phase} shell exceeded its five-second deadline') from None
        except OSError:
            self._settle(event, 'launch_error')
            raise
        self._settle(event, 'returned', result.returncode)
        return result

    def _settle(self, event, outcome, returncode=None):
        with self._timing_lock:
            event.update(outcome=outcome, seconds=round(time.monotonic() - event['started'], 3), returncode=returncode)

    def diagnostics(self):
        """Return bounded phase/timing/status only, never paths, commands, arguments or output."""
        with self._timing_lock:
            return [{key: value for key, value in event.items() if key != 'started'} |
                    {'seconds': event.get('seconds', round(time.monotonic() - event['started'], 3))}
                    for event in self._timings[-8:]]
