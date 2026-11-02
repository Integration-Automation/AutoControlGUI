"""Launch only an explicitly owned background transfer fixture and retire that exact process."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import subprocess
import sys
import time


@contextmanager
def owned_transfer_process(directory, module, configuration):
    directory.mkdir()
    environment = os.environ.copy()
    project = Path(__file__).resolve().parents[3]
    environment['PYTHONPATH'] = os.pathsep.join([str(project), str(project / 'test/unit_test')])
    with (directory / 'process.log').open('w', encoding='utf-8') as output:
        process = subprocess.Popen([sys.executable, '-m', module], stdin=subprocess.PIPE,
            stdout=output, stderr=subprocess.STDOUT, text=True, env=environment, cwd=project,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        try:
            process.stdin.write(json.dumps({'directory': str(directory), **configuration}))
            process.stdin.close()
            deadline = time.monotonic() + 10
            while not (directory / 'ready.json').is_file():
                assert process.poll() is None, 'owned transfer fixture failed; inspect its private process.log'
                assert time.monotonic() < deadline, 'owned transfer startup exceeded its original budget'
                time.sleep(0.05)
            metadata = json.loads((directory / 'ready.json').read_text(encoding='utf-8'))
            # Windows venv launchers can remain as the direct parent of the actual Python interpreter.
            assert process.pid in {metadata['pid'], metadata.get('parent_pid')}
            yield metadata
        finally:
            (directory / 'stop').touch()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.terminate()
                process.wait(timeout=5)
            assert process.returncode == 0, 'owned transfer shutdown failed; inspect its private process.log'
