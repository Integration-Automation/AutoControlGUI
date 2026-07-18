"""Round-3 regression (lower): live-screen and subscribe hardening.

``LiveScreenProvider`` reused a single stop event and ``.clear()``-ed it, so a
quick unsubscribe -> subscribe could restart a second broadcast thread while
the first was still looping (double notifications). ``resources/subscribe``
checked membership and subscribed under separate lock windows, a TOCTOU that
could create and leak a duplicate provider handle. The first test is a real
regression on the fresh-event fix; the second guards the subscribe contract.
"""
import json
from typing import Any, Callable, Dict, List, Optional

from je_auto_control.utils.mcp_server.resources import (
    LiveScreenProvider, MCPResource, ResourceProvider,
)
from je_auto_control.utils.mcp_server.server import MCPServer


def test_resubscribe_uses_a_fresh_stop_event():
    provider = LiveScreenProvider(poll_seconds=1.0)
    handle = provider.subscribe(provider.URI, lambda: None)
    old_stop = provider._stop
    provider.unsubscribe(provider.URI, handle)
    # Emptying the subscriber set must tell the old thread to exit.
    assert old_stop.is_set()

    second = provider.subscribe(provider.URI, lambda: None)
    try:
        # A reused-and-cleared event would leave the old thread running; the
        # fix binds each thread to its own event instead.
        assert provider._stop is not old_stop
        assert not provider._stop.is_set()
    finally:
        provider.unsubscribe(provider.URI, second)


class _CountingProvider(ResourceProvider):
    URI = "test://sub"

    def __init__(self) -> None:
        self.subscribe_calls = 0

    def list(self) -> List[MCPResource]:
        return [MCPResource(uri=self.URI, name="sub")]

    def read(self, uri: str) -> Optional[Dict[str, Any]]:
        return None

    def subscribe(self, uri: str,
                  on_update: Callable[[], None]) -> Optional[Any]:
        if uri != self.URI:
            return None
        self.subscribe_calls += 1
        return object()


def _subscribe(server: MCPServer, uri: str) -> Dict[str, Any]:
    return json.loads(server.handle_line(json.dumps({
        "jsonrpc": "2.0", "id": 1, "method": "resources/subscribe",
        "params": {"uri": uri},
    })))


def test_duplicate_subscribe_creates_a_single_provider_handle():
    provider = _CountingProvider()
    server = MCPServer(tools=[], resource_provider=provider)
    assert "error" not in _subscribe(server, provider.URI)
    assert "error" not in _subscribe(server, provider.URI)
    # Second subscribe for a live uri must be a no-op, not a new handle.
    assert provider.subscribe_calls == 1
