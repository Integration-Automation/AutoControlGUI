"""Version-three causal HTTP transport reuses the existing bounded egress and redirect protections."""
from __future__ import annotations

import json
import math
from typing import NoReturn, Optional, cast

from je_auto_control.utils.config_sync.client import ConfigSyncClient
from je_auto_control.utils.config_sync.contract import ConfigRevisionConflict, ConfigSyncError, _identifier, _revision
from je_auto_control.utils.exception.control_signals import raise_caused_run_interruption
from je_auto_control.utils.config_sync.outbox_models import normalize_sync_endpoint
from je_auto_control.utils.config_sync.peers import FullResyncRequired
from je_auto_control.utils.logging.secret_scope import scrub_secret_text


class CausalWire(ConfigSyncClient):
    """Internal transport only; the public causal client composes it rather than overriding plain bucket APIs."""

    def __init__(self, endpoint: str, user_id: str, secret: Optional[str], timeout_s: float) -> None:
        _identifier(user_id, "user_id")
        if isinstance(timeout_s, bool) or not isinstance(timeout_s, (int, float)):
            raise ConfigSyncError("causal timeout must be a finite positive number up to 300 seconds")
        if not 0 < timeout_s <= 300 or not math.isfinite(timeout_s):
            raise ConfigSyncError("causal timeout must be a finite positive number up to 300 seconds")
        if secret is not None and (not isinstance(secret, str) or not secret or not secret.isprintable()):
            raise ConfigSyncError("causal shared secret must be nonempty printable text")
        super().__init__(normalize_sync_endpoint(endpoint), user_id=user_id, secret=secret, timeout_s=timeout_s)

    def _request_endpoint(self, method: str) -> str:
        return self._endpoint("/causal")

    def _conflict(self, text: str) -> NoReturn:
        _causal_conflict(text)

    def request(self, method: str, body: Optional[dict[str, object]] = None) -> dict[str, object]:
        """Reject unsupported old routes and malformed JSON, while preserving explicit interruption signals."""
        try:
            reply = self._request(method, body=body)
        except ConfigSyncError as error:
            raise_caused_run_interruption(error)
            raise ConfigSyncError(scrub_secret_text(str(error))) from None
        if not isinstance(reply, dict) or not _version_three(reply.get("version")):
            raise ConfigSyncError("server did not confirm the dedicated version-three causal protocol")
        return cast(dict[str, object], reply)


def _version_three(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value == 3


def _causal_conflict(text: str) -> NoReturn:
    try:
        detail = json.loads(text)["detail"]
        if not isinstance(detail, dict):
            raise ValueError("invalid conflict detail")
        code = detail.get("code")
        if code == "full_resync_required":
            raise FullResyncRequired("server requires explicit full synchronization")
        if code not in {"stale_revision", "operation_id_conflict", "causal_protocol_required"}:
            raise ValueError("unknown conflict reason")
        revision = detail["revision"]
        _revision(revision)
    except (KeyError, TypeError, ValueError, RecursionError, ConfigSyncError):
        raise ConfigSyncError("config sync: invalid causal conflict reply") from None
    raise ConfigRevisionConflict(revision, code=code)
