"""Round-3 regression: the Anthropic *planner* LLM backend must catch
``anthropic.AnthropicError`` and honour the empty-string contract instead of
letting a 429/5xx/timeout escape ``complete``.

The ``anthropic`` SDK is not installed in CI, so a fake module carrying an
``AnthropicError`` base class is injected for the duration of each test.
"""
import sys
import types

from je_auto_control.utils.llm.backends.anthropic_backend import (
    AnthropicLLMBackend,
)


class _FakeAnthropicError(Exception):
    """Stand-in for ``anthropic.AnthropicError`` (a bare Exception)."""


class _FakeRateLimitError(_FakeAnthropicError):
    """Subclass, like the real ``anthropic.RateLimitError``."""


def _install_fake_anthropic(monkeypatch):
    module = types.ModuleType("anthropic")
    module.AnthropicError = _FakeAnthropicError
    monkeypatch.setitem(sys.modules, "anthropic", module)


def _backend(client):
    backend = AnthropicLLMBackend.__new__(AnthropicLLMBackend)
    backend.available = True
    backend._client = client
    return backend


def _client_raising(exc):
    class _Messages:
        def create(self, **kwargs):
            raise exc

    return types.SimpleNamespace(messages=_Messages())


def test_sdk_error_degrades_to_empty_string(monkeypatch):
    _install_fake_anthropic(monkeypatch)
    backend = _backend(_client_raising(_FakeRateLimitError("429 rate limited")))
    assert backend.complete("plan the next action") == ""


def test_successful_response_returns_joined_text(monkeypatch):
    _install_fake_anthropic(monkeypatch)
    block = types.SimpleNamespace(type="text", text="planned action")

    class _Messages:
        def create(self, **kwargs):
            return types.SimpleNamespace(content=[block])

    client = types.SimpleNamespace(messages=_Messages())
    assert _backend(client).complete("plan the next action") == "planned action"
