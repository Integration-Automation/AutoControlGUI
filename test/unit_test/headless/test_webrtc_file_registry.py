"""Weak channel cleanup must survive synchronous garbage collection while registry operations hold their lock."""
from pathlib import Path
import subprocess
import sys

import pytest


@pytest.mark.parametrize('replacement', [False, True])
def test_cyclic_binding_collection_reenters_the_registry_without_deadlock(replacement):
    program = '''
import gc
import weakref
from types import SimpleNamespace
from je_auto_control.utils.remote_desktop import webrtc_file_commit as protocol
gc.disable()
channel = SimpleNamespace()
old = protocol.bind_commit_channel(channel, lambda: True)
old.cycle = old
reference = weakref.ref(old)
replacement = protocol.bind_commit_channel(channel, lambda: True) if REPLACE else None
identifier = id(channel)
del old
with protocol._bindings_lock:
    gc.collect()
    assert reference() is None
    if replacement is None:
        assert identifier not in protocol._bindings
    else:
        assert protocol._bindings[identifier]() is replacement
        assert protocol._find_binding(channel) is replacement
'''.replace('REPLACE', repr(replacement))
    try:
        result = subprocess.run([sys.executable, '-c', program], cwd=Path(__file__).resolve().parents[3],
                                capture_output=True, text=True, encoding='utf-8', timeout=10, check=False)
    except subprocess.TimeoutExpired:
        pytest.fail('garbage collection reentered the held registry lock and deadlocked')
    assert result.returncode == 0, result.stderr
