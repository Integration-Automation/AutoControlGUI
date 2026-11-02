"""Exact live SDK retirement descriptions; serialized context IDs never grant authority."""
from __future__ import annotations

import re
from typing import Any, NoReturn

from je_auto_control.utils.agent_runtime.errors import AgentTaskError


def retirement_proof(value: Any, context_id: str | None = None) -> dict:
    """Validate a closed proof from the already owned helper, optionally pinning its actual context."""
    fields = {"contract", "input_supported", "network_retired", "context_id"}
    if not isinstance(value, dict) or set(value) != fields:
        raise AgentTaskError("browser retirement is unconfirmed")
    # pylint: disable-next=unidiomatic-typecheck  # reason: protocol integers must exclude boolean versions
    if type(value["contract"]) is not int or value["contract"] != 1:
        raise AgentTaskError("browser retirement is unconfirmed")
    if value["input_supported"] is not False or value["network_retired"] is not True:
        raise AgentTaskError("browser retirement is unconfirmed")
    _require_context(value["context_id"], context_id)
    return dict(value)


def _require_context(identity: Any, context_id: str | None) -> None:
    if (not isinstance(identity, str) or re.fullmatch(r"[0-9a-f]{32}", identity) is None
            or (context_id is not None and identity != context_id)):
        raise AgentTaskError("browser retirement context is unconfirmed")


def refuse_browser_input(_event: dict) -> NoReturn:
    """Fail before the owned channel can acknowledge any unexpected native input event."""
    raise AgentTaskError("read-only browser cannot acknowledge input")


def refuse_browser_tool(_name: str, _arguments: Any) -> NoReturn:
    """Resource cleanup cannot create an executable or ambient-read tool scope."""
    raise AgentTaskError("read-only browser cleanup cannot dispatch tools")


def supports_browser_retirement(value: Any) -> bool:
    """Inspect additive helper API availability; this metadata is never a retirement proof."""
    if not isinstance(value, dict):
        raise AgentTaskError("browser helper bootstrap protocol is incompatible")
    # pylint: disable-next=unidiomatic-typecheck  # reason: exact protocol integers exclude boolean versions
    if type(value.get("protocol")) is not int or value["protocol"] != 1:
        raise AgentTaskError("browser helper bootstrap protocol is incompatible")
    marker = value.get("browser_readonly")
    # pylint: disable-next=unidiomatic-typecheck  # reason: optional helper API versions also exclude booleans
    return type(marker) is int and marker == 1
