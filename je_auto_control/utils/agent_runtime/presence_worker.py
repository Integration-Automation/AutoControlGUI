"""Fixed owned source worker; bootstrap and first-instance ownership precede native observation."""
from __future__ import annotations

import sys
from typing import Any, Callable

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.owned_channel_factory import owned_channel
from je_auto_control.utils.agent_runtime.presence_frames import identifier
from je_auto_control.utils.agent_runtime.presence_owner import read_request, send_error, send_result
from je_auto_control.utils.agent_runtime.presence_pipe_windows import WindowsPresencePipe
from je_auto_control.utils.agent_runtime.presence_server import PresenceServer
from je_auto_control.utils.agent_runtime.presence_windows import WindowsPresenceSource
from je_auto_control.utils.agent_runtime.parent_watch import start_parent_watch


class SourceProcess:
    """Launch once through the owned channel factory; no source starts before its owner bootstrap."""

    def __init__(self, namespace: str | None = None, *,
                 channel_factory: Callable[[list[str]], Any] | None = None) -> None:
        self._namespace = identifier(namespace) if namespace is not None else None
        self._factory = channel_factory if channel_factory is not None else owned_channel
        self._channel: Any = None
        self._started = False

    def start(self) -> dict:
        """The fixed child is contained before it receives the internal source bootstrap."""
        if self._started:
            raise AgentTaskError('physical presence source process cannot restart')
        self._started = True
        try:
            self._channel = self._factory(
                [sys.executable, '-u', '-m', 'je_auto_control.utils.agent_runtime.presence_worker'])
            return self._channel.request('bootstrap', {'namespace': self._namespace}, timeout=15)
        except BaseException:
            self.close()
            raise

    def close(self) -> None:
        """Retire only this actually owned source tree; retain ownership on failed retirement."""
        self._started = True
        if self._channel is not None:
            self._channel.close()
            self._channel = None


def _namespace(payload: dict) -> str | None:
    if set(payload) != {'namespace'}:
        raise AgentTaskError('physical presence source bootstrap fields are invalid')
    value = payload['namespace']
    return identifier(value) if value is not None else None


def run(source: Any, sink: Any, *, source_factory: Callable[[], Any] = WindowsPresenceSource,
        pipe_factory: Callable[..., Any] = WindowsPresencePipe) -> None:
    """Serve the single private source bootstrap; later owner EOF closes only this source."""
    server = None
    try:
        while True:
            request = read_request(source)
            if request is None:
                return
            try:
                if request['operation'] != 'bootstrap' or server is not None:
                    raise AgentTaskError('physical presence source accepts one bootstrap only')
                namespace = _namespace(request['payload'])
                server = PresenceServer(source_factory, pipe=pipe_factory(namespace=namespace))
                result = server.start()
            except (OSError, ValueError, AgentTaskError) as error:
                send_error(sink, request['id'], error)
                return
            send_result(sink, request['id'], result)
            if result['ready'] is not True:
                return
    finally:
        if server is not None:
            server.close()


def main() -> None:
    """Run only as the fixed source child created after its broker is owned."""
    start_parent_watch()
    run(sys.stdin.buffer, sys.stdout.buffer)


if __name__ == '__main__':
    main()
