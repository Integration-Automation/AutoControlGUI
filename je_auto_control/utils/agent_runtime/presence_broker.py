"""Private bounded-RPC presence broker; source ownership is chosen internally, never by task fields."""
from __future__ import annotations

from contextlib import ExitStack
from dataclasses import dataclass
import sys
import threading
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.presence_frames import (
    decode_frame, encode_frame, identifier, presence_body, validate_response,
)
from je_auto_control.utils.agent_runtime.presence_handshake import client_handshake
from je_auto_control.utils.agent_runtime.presence_owner import read_request, send_error, send_result
from je_auto_control.utils.agent_runtime.presence_pipe_windows import WindowsPresencePipe
from je_auto_control.utils.agent_runtime.presence_security_windows import WindowsPresenceSecurity
from je_auto_control.utils.agent_runtime.presence_worker import SourceProcess
from je_auto_control.utils.agent_runtime.parent_watch import start_parent_watch


@dataclass
class _Binding:
    connection: Any = None
    peer: Any = None
    owner: Any = None
    generation: str | None = None
    expected: str | None = None
    sequence: int = 1
    closed: bool = False


def _ready(value: Any) -> str | None:
    if value == {'ready': False, 'occupied': True} and value['ready'] is False and value['occupied'] is True:
        return None
    if isinstance(value, dict) and set(value) == {'ready', 'generation'} and value['ready'] is True:
        return identifier(value['generation'])
    raise AgentTaskError('physical presence source startup response is invalid')


def _available(reply: dict) -> bool:
    if reply['status'] in {'busy', 'lease_lost'}:
        return False
    if reply['status'] != 'ok' or reply['result']['state'] not in {'waiting_idle', 'locked', 'monitoring'}:
        raise AgentTaskError('physical presence source did not become healthy')
    return True


class PresenceBroker:
    """One persistent pipe owner inside an OwnedChannel helper; ordinary busy never kills its source."""

    def __init__(self, *, pipe: Any = None, security: Any = None,
                 launch: Callable[[], Any] | None = None, namespace: str | None = None) -> None:
        self._pipe = pipe if pipe is not None else WindowsPresencePipe(namespace=namespace)
        self._security = security if security is not None else WindowsPresenceSecurity()
        self._launch = launch if launch is not None else self._default_launch
        self._namespace = namespace
        self._binding = _Binding()
        self._mutex = threading.RLock()

    def _default_launch(self) -> Any:
        return SourceProcess(self._namespace)

    def _discover(self) -> Any:
        connection = self._pipe.connect_if_present()
        if connection is not None:
            return connection
        if self._binding.owner is not None:
            raise AgentTaskError('physical presence owned source endpoint disappeared')
        self._binding.owner = self._launch()
        self._binding.expected = _ready(self._binding.owner.start())
        if self._binding.expected is None:
            self._binding.owner.close()
            self._binding.owner = None
        return self._pipe.connect()

    def bootstrap(self) -> dict:
        """Borrow a verified source or launch one missing source after the parent owns this helper."""
        with self._mutex:
            if self._binding.closed:
                raise AgentTaskError('physical presence broker has closed')
            try:
                if self._binding.connection is None:
                    self._binding.connection = self._discover()
                    generation, self._binding.peer = client_handshake(self._binding.connection, self._security)
                    if self._binding.expected is not None and generation != self._binding.expected:
                        raise AgentTaskError('physical presence owned source generation changed')
                    self._binding.generation = generation
                if not _available(self.request('inspect', {})):
                    return {'ready': False, 'status': 'busy'}
                return {'ready': True, 'generation': self._binding.generation}
            except AgentControlBusy:
                return {'ready': False, 'status': 'busy'}
            except BaseException:
                self.close()
                raise

    def request(self, operation: str, body: dict) -> dict:
        """Return closed expected gate results; transport/source loss is fatal and never replayed."""
        with self._mutex:
            if self._binding.closed or self._binding.connection is None or self._binding.generation is None:
                raise AgentTaskError('physical presence broker has no live source binding')
            try:
                body = presence_body(operation, body)
                if not self._binding.peer.alive():
                    raise AgentTaskError('physical presence source process has exited')
                sequence = self._binding.sequence
                self._binding.connection.send_bytes(encode_frame(
                    {'request_id': sequence, 'operation': operation, 'body': body}))
                reply = decode_frame(self._binding.connection.recv_bytes(4096))
                validate_response(reply, operation, sequence, self._binding.generation)
                if not self._binding.peer.alive() or reply['status'] == 'source_lost':
                    raise AgentTaskError('physical presence source has been lost')
                self._binding.sequence += 1
                return reply
            except BaseException:
                self.close()
                raise

    def dispatch(self, operation: str, body: dict) -> dict:
        """The host wire may select only bootstrap or the four closed presence operations."""
        if operation == 'bootstrap':
            if not isinstance(body, dict) or body:
                raise AgentTaskError('physical presence bootstrap takes no task-selected authority')
            return self.bootstrap()
        return self.request(operation, body)

    def close(self) -> None:
        """Close this connection and only an actually owned child; borrowers never stop another source."""
        with self._mutex:
            self._binding.closed = True
            with ExitStack() as cleanup:
                for resource in (self._binding.owner, self._binding.peer, self._binding.connection):
                    if resource is not None:
                        cleanup.callback(resource.close)
            self._binding.connection = self._binding.peer = self._binding.owner = None


def run(source: Any, sink: Any, broker: PresenceBroker | None = None) -> None:
    """Serve fixed host-owned envelopes; launch is impossible before a valid bootstrap is received."""
    broker = broker if broker is not None else PresenceBroker()
    try:
        while True:
            request = read_request(source)
            if request is None:
                return
            try:
                result = broker.dispatch(request['operation'], request['payload'])
            except (OSError, EOFError, ValueError, AgentTaskError) as error:
                send_error(sink, request['id'], error)
                return
            send_result(sink, request['id'], result)
    finally:
        broker.close()


def main() -> None:
    """Run only as the fixed hidden helper of a host-owned presence pool."""
    start_parent_watch()
    run(sys.stdin.buffer, sys.stdout.buffer)


if __name__ == '__main__':
    main()
