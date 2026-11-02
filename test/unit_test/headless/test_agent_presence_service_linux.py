"""The Linux presence chain: an owned worker reports its fresh endpoint, and the broker connects only to it."""
import json
import os
from pathlib import Path
import secrets
import sys

import pytest

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.presence_pipe_linux import (
    LinuxPresencePipe, endpoint_from_wire, endpoint_to_wire,
)

ROOT = Path(__file__).resolve().parents[3]
linux = pytest.mark.skipif(not sys.platform.startswith('linux'), reason='actual Linux socket integration')


def _wire(**changes):
    value = {"directory": "/run/user/1000/je-presence-abc", "socket_name": "presence.sock",
             "directory_identity": {"device": 1, "inode": 2, "owner": 1000, "mode": 0o40700},
             "socket_identity": {"device": 1, "inode": 3, "owner": 1000, "mode": 0o140600},
             "listener_process": {"pid": 42, "uid": 1000, "gid": 1000, "birth": 99,
                                  "user_namespace": "user:[4026531837]", "pid_namespace": "pid:[4026531836]"}}
    value.update(changes)
    return value


@linux
def test_an_endpoint_round_trips_through_its_wire_form():
    endpoint = endpoint_from_wire(_wire())
    assert endpoint_to_wire(endpoint) == _wire()


@pytest.mark.parametrize("change", [
    {"extra": 1},
    {"directory": "relative/path"},
    {"socket_name": "../escape"},
    {"socket_name": ""},
    {"directory_identity": {"device": 1, "inode": 2, "owner": 1000}},
    {"socket_identity": {"device": -1, "inode": 3, "owner": 1000, "mode": 1}},
    {"listener_process": {"pid": True, "uid": 1000, "gid": 1000, "birth": 99, "user_namespace": "n",
                          "pid_namespace": "p"}},
    {"listener_process": {"pid": 42, "uid": 1000, "gid": 1000, "birth": 99, "user_namespace": "",
                          "pid_namespace": "p"}},
    {"listener_process": {"pid": 42, "uid": 1000, "gid": 1000, "birth": 99, "user_namespace": "n"}},
])
def test_a_malformed_endpoint_is_refused_before_any_connection(change):
    malformed = _wire(**change)
    with pytest.raises(AgentTaskError):
        endpoint_from_wire(malformed)


def test_the_wire_form_names_every_field_of_the_endpoint_types():
    from dataclasses import fields
    from je_auto_control.utils.agent_runtime import presence_pipe_linux as wire
    from je_auto_control.utils.agent_runtime.presence_endpoint_linux import FileIdentity, LinuxEndpoint
    from je_auto_control.utils.agent_runtime.presence_peer_linux import LinuxPeerIdentity
    assert wire._PEER_FIELDS == tuple(item.name for item in fields(LinuxPeerIdentity))
    assert wire._FILE_FIELDS == tuple(item.name for item in fields(FileIdentity))
    assert wire._ENDPOINT_FIELDS == {item.name for item in fields(LinuxEndpoint)}


def test_without_an_owned_launch_there_is_nothing_to_connect_to():
    pipe = LinuxPresencePipe(runtime_directory="/run/user/1000")
    assert pipe.connect_if_present() is None
    with pytest.raises(AgentTaskError, match="does not exist"):
        pipe.connect()


def test_listening_needs_a_private_runtime_directory():
    pipe = LinuxPresencePipe(runtime_directory="")
    with pytest.raises(AgentTaskError, match="XDG_RUNTIME_DIR"):
        pipe.listen()


def _broker_script(clock):
    source = f'''
import sys
from pathlib import Path
sys.path.insert(0, {str(ROOT / 'test/unit_test/headless')!r})
from presence_test_support import Source
from je_auto_control.utils.agent_runtime import presence_worker

class ControlledSource(Source):
    def __init__(self):
        super().__init__()
        self.base = float(Path({str(clock)!r}).read_text())
    def request(self, operation, body):
        age = float(Path({str(clock)!r}).read_text()) - self.base
        self.advance(max(0.0, age - self.now))
        return super().request(operation, body)

presence_worker.run(sys.stdin.buffer, sys.stdout.buffer, source_factory=ControlledSource)
'''
    namespace = secrets.token_hex(16)
    return f'''
import sys
from je_auto_control.utils.agent_runtime.native_channel import OwnedChannel
from je_auto_control.utils.agent_runtime.presence_worker import SourceProcess
from je_auto_control.utils.agent_runtime.presence_broker import PresenceBroker, run

def source_channel(_fixed_argv):
    return OwnedChannel([sys.executable, '-u', '-c', {source!r}])

broker = PresenceBroker(namespace={namespace!r},
    launch=lambda: SourceProcess({namespace!r}, channel_factory=source_channel))
run(sys.stdin.buffer, sys.stdout.buffer, broker)
'''


@linux
def test_an_owned_worker_hands_its_endpoint_to_the_broker_and_serves_presence(tmp_path, monkeypatch):
    from je_auto_control.utils.agent_runtime.native_channel import OwnedChannel
    runtime = tmp_path / 'runtime'
    runtime.mkdir(mode=0o700)
    os.chmod(runtime, 0o700)
    monkeypatch.setenv('XDG_RUNTIME_DIR', str(runtime))
    clock = tmp_path / 'clock.txt'
    clock.write_text('0', encoding='utf-8')
    broker = OwnedChannel([sys.executable, '-u', '-c', _broker_script(clock)])
    try:
        ready = broker.request('bootstrap', {}, timeout=15)
        assert ready['ready'] is True, json.dumps(ready)
        assert len(ready['generation']) == 32, json.dumps(ready)
        assert broker.request('acquire', {}, timeout=3)['status'] == 'busy'
        clock.write_text('60', encoding='utf-8')
        lease = broker.request('acquire', {}, timeout=3)['result']
        assert lease['generation'] == ready['generation']
        assert broker.request('check', lease, timeout=3)['status'] == 'ok'
        assert broker.request('inspect', {}, timeout=3)['result']['generation'] == ready['generation']
    finally:
        broker.close()
    assert broker.retired
