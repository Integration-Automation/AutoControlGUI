"""Bounded source reads and management replies use an injected adapter without foreign task authority."""
from __future__ import annotations

import base64
from dataclasses import dataclass
from hashlib import sha256
import time
from typing import Any, Callable, Mapping

from je_auto_control.utils.agent_runtime.errors import AgentTaskError
from je_auto_control.utils.agent_runtime.transfer_models import (
    TransferManifest, MAX_MANIFEST_BYTES, _canonical, _hex, _object,
)
from je_auto_control.utils.agent_runtime.transfer_management import management_request, management_reply
from je_auto_control.utils.agent_runtime.transfer_evidence_contract import (
    evidence_binding, portable_evidence, request_digest,
)
from je_auto_control.utils.config_sync.blob_models import CHUNK_BYTES
from je_auto_control.utils.exception.cancellation import cancellation_checkpoint
from je_auto_control.utils.rbac.authorization import AuthorizationError


@dataclass(frozen=True)
class TransferPeer:
    """Validate descriptors, chunks and management projections under the host's current registered identity."""

    invoke: Callable[[str, str, str, dict, float], dict]

    def call(self, host: str, binding: str, operation: str, request: Mapping, timeout: float) -> dict:
        """Read an exact source export or content hash with bounded bytes and a fixed local deadline."""
        value = self._request(host, binding, operation, request, timeout)
        deadline = time.monotonic() + timeout
        validate = self._validator(operation, value)
        return self._exchange(host, binding, '/agent/transfer/peer', {'operation': operation, 'request': value},
                              deadline, validate)

    def _validator(self, operation: str, value: dict) -> Callable:
        if operation == 'evidence':
            return lambda reply: self._evidence(reply, value)
        if operation == 'export':
            return lambda reply: self._manifest(reply, value['export_id'])
        return lambda reply: self._chunk(reply, value['sha256'])

    @staticmethod
    def _evidence(reply: dict, request: dict) -> dict:
        result = portable_evidence(reply)
        if result['expires'] <= time.time():
            raise AgentTaskError('portable evidence source retention has expired')
        binding = request['binding']
        if result['grant_id'] != request['grant_id'] or any(
                result[name] != binding[name] for name in ('source_task', 'submitted_spec_digest')):
            raise AgentTaskError('portable evidence reply changed its requested original identity')
        if ('node' in result) != ('batch_id' in binding):
            raise AgentTaskError('portable evidence reply changed its actual DAG binding')
        if 'node' in result and (any(result['node'][name] != binding[name]
                for name in ('batch_id', 'graph_hash', 'node_id')) or
                result['node']['request_digest'] != request_digest(binding)):
            raise AgentTaskError('portable evidence reply changed its actual accepted request')
        return result

    def manage(self, host: str, binding: str, operation: str, request: Mapping, timeout: float) -> dict:
        """Use only closed source management fields and validate the foreign public projection."""
        self._identity(host, binding, timeout)
        value = management_request(operation, request)
        return self._exchange(host, binding, '/agent/transfer', {'operation': operation, 'request': value},
                              time.monotonic() + timeout, lambda reply: management_reply(operation, reply, value))

    def _exchange(self, host: str, binding: str, path: str, body: dict, deadline: float, validate: Callable) -> dict:
        self._checkpoint(deadline)
        try:
            reply = self.invoke(host, binding, path, body, deadline - time.monotonic())
            self._checkpoint(deadline)
            if not isinstance(reply, dict) or len(_canonical(reply)) > MAX_MANIFEST_BYTES:
                raise AgentTaskError('peer reply exceeds its closed one-mebibyte envelope')
            result = validate(reply)
            self._checkpoint(deadline)
            return result
        except AgentTaskError:
            raise
        except (AuthorizationError, OSError, ValueError, TypeError, KeyError, RecursionError) as error:
            raise AgentTaskError('peer transfer is unavailable or its reply is malformed') from error

    @staticmethod
    def _request(host: str, binding: str, operation: str, request: Mapping, timeout: float) -> dict:
        TransferPeer._identity(host, binding, timeout)
        fields = {'export': {'export_id'}, 'chunk': {'export_id', 'sha256'}, 'evidence': {'grant_id', 'binding'}}
        if not isinstance(operation, str) or operation not in fields:
            raise AgentTaskError('peer transfer operation is unavailable')
        value = dict(_object(request, fields[operation]))
        if operation == 'evidence':
            _hex(value['grant_id'], 32)
            value['binding'] = evidence_binding(value['binding'])
            return value
        _hex(value['export_id'], 32)
        if operation == 'chunk':
            _hex(value['sha256'], 64)
        return value

    @staticmethod
    def _identity(host: str, binding: str, timeout: float) -> None:
        if not isinstance(host, str) or not host or host == 'local':
            raise AgentTaskError('peer requires a registered remote host')
        _hex(binding, 64)
        TransferPeer._timeout(timeout)

    @staticmethod
    def _timeout(value: Any) -> None:
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise AgentTaskError('peer timeout must be numeric')
        if not 0 < value <= 30:
            raise AgentTaskError('peer timeout must be finite, positive and at most thirty seconds')

    @staticmethod
    def _checkpoint(deadline: float) -> None:
        cancellation_checkpoint()
        if time.monotonic() >= deadline:
            raise AgentTaskError('peer transfer deadline exhausted')

    @staticmethod
    def _manifest(reply: dict, identifier: str) -> dict:
        manifest = TransferManifest.from_dict(reply)
        if manifest.export_id != identifier or manifest.expires <= time.time():
            raise AgentTaskError('peer export identity changed or its grant is expired')
        return manifest.to_dict()

    @staticmethod
    def _chunk(reply: dict, digest: str) -> dict:
        value = _object(reply, {'contract', 'sha256', 'data'})
        version = value['contract']
        if isinstance(version, bool) or not isinstance(version, int) or version != 1:
            raise AgentTaskError('unsupported peer chunk contract')
        _hex(value['sha256'], 64)
        if value['sha256'] != digest:
            raise AgentTaskError('peer chunk does not match the requested hash')
        TransferPeer._chunk_bytes(value['data'], digest)
        return {'contract': 1, 'sha256': digest, 'data': value['data']}

    @staticmethod
    def _chunk_bytes(data: Any, digest: str) -> None:
        if not isinstance(data, str) or len(data) > 4 * ((CHUNK_BYTES + 2) // 3):
            raise AgentTaskError('peer chunk encoded bytes exceed their bound')
        body = base64.b64decode(data, validate=True)
        if (not 0 < len(body) <= CHUNK_BYTES or base64.b64encode(body).decode('ascii') != data
                or sha256(body).hexdigest() != digest):
            raise AgentTaskError('peer chunk bytes are oversized, noncanonical or differ from their hash')
