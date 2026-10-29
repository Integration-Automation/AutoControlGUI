"""Nested bootstrap frame tests over ordinary pipes; no service or helper is started."""
import os
import struct

import pytest

from je_auto_control.utils.agent_runtime import owner_service_nested as nested
from je_auto_control.utils.agent_runtime.errors import AgentTaskError

CAPABILITY = bytes(range(1, 33))


def frame(magic=nested.BOOTSTRAP_MAGIC, version=nested.BOOTSTRAP_VERSION, record=(0, 3)):
    return struct.pack("<II", magic, version) + struct.pack("<QQ", 142, 1) + struct.pack("<QQ", *record) + CAPABILITY


def piped(data):
    read_end, write_end = os.pipe()
    os.write(write_end, data)
    os.close(write_end)
    return read_end


def test_frame_layout_matches_the_native_record():
    assert nested._FRAME.size == 72


def test_valid_frame_is_read_once_and_its_descriptor_closed():
    fd = piped(frame())
    grant = nested.read_nested_bootstrap(fd)
    assert grant.parent == ((142, 1), (0, 3)) and grant.capability == CAPABILITY
    with pytest.raises(OSError):
        os.fstat(fd)
    assert "capability=<32 bytes>" in repr(grant) and str(CAPABILITY[0]) not in repr(grant).split("capability")[1]


def test_absent_descriptor_means_not_nested():
    read_end, write_end = os.pipe()
    os.close(read_end)
    os.close(write_end)
    assert nested.read_nested_bootstrap(read_end) is None


@pytest.mark.parametrize("data", [
    frame()[:40],
    frame() + b"x",
    frame(magic=0x12345678),
    frame(version=2),
    frame(record=(0, 0)),
    b"",
])
def test_malformed_frames_refuse_and_still_close(data):
    fd = piped(data)
    with pytest.raises(AgentTaskError):
        nested.read_nested_bootstrap(fd)
    with pytest.raises(OSError):
        os.fstat(fd)
