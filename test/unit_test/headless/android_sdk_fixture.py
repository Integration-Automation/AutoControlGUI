"""Owned smart-socket ADB server runs finite commands in an isolated Android shell fixture."""
import json
import socketserver
import struct
import threading

from .android_shell_fixture import AndroidShellFixture


def _read(stream, size):
    data = bytearray()
    while len(data) < size:
        chunk = stream.recv(size - len(data))
        if not chunk:
            raise EOFError('fixture stream closed')
        data.extend(chunk)
    return bytes(data)


def _request(stream):
    return _read(stream, int(_read(stream, 4), 16))


class AndroidSdkFixture:
    """Only loopback/test-owned files; input is a recording shell function, never a real device."""

    def __init__(self, directory, snapshot, input_dump, policy_dump):
        self.directory, self.snapshot = directory, snapshot
        self.shell = AndroidShellFixture(directory, snapshot)
        (directory / 'input').write_bytes(input_dump)
        (directory / 'policy').write_bytes(policy_dump)
        self.services, self.errors = [], []
        self.mode = ''
        self._lock = threading.Lock()
        fixture = self

        class Handler(socketserver.BaseRequestHandler):
            def handle(self):
                self.request.settimeout(8)
                try:
                    fixture.handle(self.request)
                except (OSError, ValueError, AssertionError, EOFError) as error:
                    fixture.errors.append(type(error).__name__)

        self.server = socketserver.ThreadingTCPServer(('127.0.0.1', 0), Handler)
        self.server.daemon_threads = True
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *_args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(2)

    @property
    def port(self):
        return self.server.server_address[1]

    def handle(self, stream):
        first = _request(stream)
        if first == b'host:devices-l':
            data = b'reviewed-endpoint device product:fixture transport_id:42\n'
            stream.sendall(b'OKAY' + f'{len(data):04x}'.encode() + data)
            return
        assert first == b'host:transport-id:42'
        stream.sendall(b'OKAY')
        service = _request(stream)
        assert service.startswith(b'shell,v2,raw:')
        stream.sendall(b'OKAY')
        assert _read(stream, 5) == struct.pack('<BI', 4, 0)
        command = service[len(b'shell,v2,raw:'):].decode('utf-8')
        with self._lock:
            self.services.append(command)
            result, effect = self._execute(command)
        for kind, data in ((1, result.stdout), (2, result.stderr)):
            if data:
                stream.sendall(struct.pack('<BI', kind, len(data)) + data)
        if self.mode != 'drop_exit' or not effect:
            stream.sendall(struct.pack('<BI', 3, 1) + bytes([result.returncode]))

    def _execute(self, command):
        effect = '/system/bin/input -d 0 ' in command
        fence = None
        if effect:
            fence = json.loads((self.directory / 'fence.json').read_text())
            assert fence['active'] is True
            self._settlement(fence, False)
        result = self.shell.run(command)
        if effect:
            # The owned fixture writer has exited and has no held input or queued subprocess work.
            self._settlement(fence, True)
        return result, effect

    def _settlement(self, fence, empty):
        proof = {'device': {'platform': 'android', 'physical_id': self.snapshot.physical_id},
                 'epoch': 'fixture-epoch', 'boot_id': self.snapshot.boot_id, 'request_id': fence['request_id'],
                 'inputs_released': empty, 'queue_empty': empty}
        (self.directory / 'settlement.json').write_text(json.dumps(proof))
