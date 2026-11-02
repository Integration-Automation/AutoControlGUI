"""Pure browser text and URL bounds shared without loading SDK or command dispatch."""
from __future__ import annotations

from typing import Any
from urllib.parse import urlsplit

from je_auto_control.utils.agent_runtime.errors import AgentTaskError


def bounded(value: Any, name: str, maximum: int, *, empty: bool = False) -> None:
    """Require complete valid Unicode within the SDK's UTF-16 text bound."""
    if not isinstance(value, str) or len(value) > maximum or (not value and not empty):
        raise AgentTaskError(f"browser {name} must be bounded text")
    try:
        units = len(value.encode("utf-16-le")) // 2
    except UnicodeError:
        raise AgentTaskError("browser text contains invalid Unicode") from None
    if units > maximum:
        raise AgentTaskError(f"browser {name} exceeds its UTF-16 text limit")


def browser_url_origin(url: str) -> str:
    """Normalize HTTP(S) authority while preserving a caller's SPA fragment separately."""
    try:
        parsed = urlsplit(url)
        if parsed.username is not None or parsed.port == 0:
            raise AgentTaskError("browser URL credentials or port zero are not supported")
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise AgentTaskError("browser URL requires an explicit HTTP(S) origin")
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        hostname = parsed.hostname.lower()
        hostname = f"[{hostname}]" if ":" in hostname else hostname
        return f"{parsed.scheme}://{hostname}:{port}"
    except ValueError:
        raise AgentTaskError("browser URL authority is invalid") from None
