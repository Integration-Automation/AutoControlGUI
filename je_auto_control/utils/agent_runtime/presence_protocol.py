"""Per-connection presence sequences and token ownership; source lifetime remains separate."""
from __future__ import annotations

import threading
from typing import Any

from je_auto_control.utils.agent_runtime.errors import AgentControlBusy, AgentTaskError
from je_auto_control.utils.agent_runtime.presence_frames import (
    identifier, validate_request, validate_response,
)


class PresenceProtocol:
    """Track only issued presence tokens; disconnect never stops a shared physical source."""

    def __init__(self, source: Any) -> None:
        self._source = source
        self._generation = identifier(source.status()['generation'])
        self._sequence = 1
        self._issued: dict[str, str] = {}
        self._closed = False
        self._mutex = threading.RLock()

    @property
    def generation(self) -> str:
        """Return only the source generation needed by the authenticated pipe handshake."""
        return self._generation

    def _outcome(self) -> str:
        status = self._source.status()
        live = {'monitoring', 'waiting_idle', 'locked'}
        return 'lease_lost' if isinstance(status, dict) and status.get('state') in live else 'source_lost'

    def _operation(self, operation: str, body: dict) -> dict:
        if operation == 'release':
            if self._issued.get(body['lease_id']) != body['generation']:
                raise AgentTaskError('physical presence token is not owned by this connection')
            self._source.release(**body)
            del self._issued[body['lease_id']]
            return {'released': True}
        return self._source.request(operation, body)

    def request(self, value: dict) -> dict:
        """Dispatch one sequential closed request, returning expected gate outcomes as normal data."""
        with self._mutex:
            if self._closed:
                raise AgentTaskError('physical presence connection has closed')
            try:
                sequence, operation, body = validate_request(value)
                if sequence != self._sequence:
                    raise AgentTaskError('physical presence connection sequence is stale')
            except AgentTaskError:
                self.close()
                raise
            self._sequence += 1
            try:
                result = self._operation(operation, body)
                reply = {'request_id': sequence, 'status': 'ok', 'result': result}
                validate_response(reply, operation, sequence, self._generation)
                if operation == 'acquire':
                    self._issued[result['lease_id']] = result['generation']
                return reply
            except AgentControlBusy:
                return {'request_id': sequence, 'status': 'busy', 'result': None}
            except AgentTaskError:
                return {'request_id': sequence, 'status': self._outcome(), 'result': None}

    def close(self) -> None:
        """Revoke only this connection's presence leases, without native input or source shutdown."""
        with self._mutex:
            self._closed = True
            for lease_id, generation in list(self._issued.items()):
                self._source.release(generation=generation, lease_id=lease_id)
                del self._issued[lease_id]
