"""Fresh bounded byte challenges bind presence peers to query-only native process handles."""
from __future__ import annotations

from contextlib import contextmanager
import secrets
from typing import Any, Iterator

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.presence_frames import (
    decode_frame, encode_frame, identifier, unsigned,
)
from je_auto_control.utils.agent_runtime.presence_security_windows import (
    PeerProcess, WindowsPresenceSecurity,
)

_HELLO = {'protocol', 'challenge', 'birth', 'generation'}
_PROOF = {'protocol', 'server_challenge', 'challenge', 'birth'}


def _receive(connection: Any, fields: set[str]) -> dict:
    value = decode_frame(connection.recv_bytes(4096))
    if set(value) != fields or unsigned(value.get('protocol'), 1, 1) != 1:
        raise AgentTaskError('physical presence handshake fields are invalid')
    unsigned(value['birth'], (1 << 64) - 1, 1)
    for name in fields - {'protocol', 'birth'}:
        identifier(value[name])
    return value


def _verify(value: dict, peer: PeerProcess, challenge: str, field: str = 'challenge') -> None:
    if value[field] != challenge or value['birth'] != peer.identity.birth or not peer.alive():
        raise AgentTaskError('physical presence live peer challenge failed')


@contextmanager
def _opened(connection: Any, security: WindowsPresenceSecurity, server: bool) -> Iterator[PeerProcess]:
    peer = None
    try:
        peer = security.peer(connection.fileno(), server=server)
        yield peer
    except BaseException:
        try:
            if peer is not None:
                peer.close()
        finally:
            connection.close()
        raise


def server_handshake(connection: Any, security: WindowsPresenceSecurity, generation: str) -> PeerProcess:
    """Authenticate after opening the actual client object; caller retains its owned query handle."""
    with _opened(connection, security, True) as peer:
        generation = identifier(generation)
        birth = security.current().birth
        challenge = secrets.token_hex(16)
        connection.send_bytes(encode_frame({
            'protocol': 1, 'challenge': challenge, 'birth': birth, 'generation': generation}))
        proof = _receive(connection, _PROOF)
        _verify(proof, peer, challenge, 'server_challenge')
        connection.send_bytes(encode_frame({
            'protocol': 1, 'challenge': proof['challenge'], 'birth': birth, 'generation': generation}))
        return peer


def client_handshake(connection: Any, security: WindowsPresenceSecurity) -> tuple[str, PeerProcess]:
    """Check both fresh echoes, native birth and retained-object liveness before trusting generation."""
    with _opened(connection, security, False) as peer:
        hello = _receive(connection, _HELLO)
        _verify(hello, peer, hello['challenge'])
        challenge = secrets.token_hex(16)
        connection.send_bytes(encode_frame({'protocol': 1, 'server_challenge': hello['challenge'],
            'challenge': challenge, 'birth': security.current().birth}))
        reply = _receive(connection, _HELLO)
        _verify(reply, peer, challenge)
        if reply['generation'] != hello['generation']:
            raise AgentTaskError('physical presence handshake source generation changed')
        return reply['generation'], peer
