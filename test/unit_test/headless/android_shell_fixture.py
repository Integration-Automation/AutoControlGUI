"""Execute reviewed Android command scripts against test-owned POSIX functions and files only."""
import os
from pathlib import Path
import shutil
import subprocess

import pytest

_HARNESS = '''
fixture_getprop() { command cat "$FIXTURE_DIR/device"; }
fixture_cat() { command cat "$FIXTURE_DIR/boot"; }
fixture_dumpsys() {
    if [ "$1" = input ]; then command cat "$FIXTURE_DIR/input";
    elif [ "$2" = policy ]; then command cat "$FIXTURE_DIR/policy";
    else command cat "$FIXTURE_DIR/wm"; fi
}
fixture_input() {
    printf '%s\\n' "$@" >> "$FIXTURE_DIR/actions"
    for field in device boot; do
        if [ -f "$FIXTURE_DIR/after-$field" ]; then
            command cat "$FIXTURE_DIR/after-$field" > "$FIXTURE_DIR/$field"
        fi
    done
    if [ -f "$FIXTURE_DIR/after" ]; then command cat "$FIXTURE_DIR/after" > "$FIXTURE_DIR/wm"; fi
    if [ -f "$FIXTURE_DIR/fail" ]; then return 1; fi
}
'''


class AndroidShellFixture:
    """An installed sh runs compiled scripts while every Android executable is replaced by a fixture."""

    def __init__(self, directory, snapshot):
        self.directory = directory
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
        for tool in ('getprop', 'cat', 'dumpsys', 'input'):
            script = script.replace('/system/bin/' + tool, 'fixture_' + tool)
        for tool in ('printf', 'sed', 'sha256sum', 'cut'):
            script = script.replace('/system/bin/' + tool, tool)
        flags = getattr(subprocess, 'CREATE_NO_WINDOW', 0) if os.name == 'nt' else 0
        return subprocess.run([self.shell, '-c', _HARNESS + script], capture_output=True, timeout=5,
                              env={**os.environ, 'FIXTURE_DIR': self.directory.as_posix()}, cwd=self.directory,
                              creationflags=flags, check=False)
