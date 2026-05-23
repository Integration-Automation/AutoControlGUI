"""Anthropic Claude backend for the AgentLoop."""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Sequence

from je_auto_control.utils.agent.agent_loop import AgentBackend, AgentStep
from je_auto_control.utils.agent.backends.base import (
    AgentBackendError, build_default_system_prompt, encode_screenshot_b64,
)


_DEFAULT_MODEL = "claude-opus-4-7"


class AnthropicAgentBackend(AgentBackend):
    """Drive the agent loop with Anthropic's Messages API + tool use.

    The vendor SDK (``pip install anthropic``) is lazy-imported. Both
    ``api_key`` and ``client`` are optional — pass a pre-built client
    for tests, or let the backend construct one from the ``api_key``
    (or ``ANTHROPIC_API_KEY`` env var) at first use.
    """

    def __init__(self,
                 *, tools: Sequence[Dict[str, Any]],
                 client: Optional[Any] = None,
                 api_key: Optional[str] = None,
                 model: str = _DEFAULT_MODEL,
                 max_tokens: int = 1024,
                 system_prompt_builder: Optional[Any] = None) -> None:
        if not tools:
            raise AgentBackendError(
                "AnthropicAgentBackend requires a non-empty tool list "
                "(see export_anthropic_tools()).",
            )
        self._tools = list(tools)
        self._client = client
        self._api_key = api_key
        self._model = model
        self._max_tokens = int(max_tokens)
        self._build_system = system_prompt_builder or build_default_system_prompt
        self._conversation: List[Dict[str, Any]] = []

    def _resolve_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import anthropic
        except ImportError as exc:
            raise AgentBackendError(
                "anthropic SDK not installed (pip install anthropic).",
            ) from exc
        self._client = anthropic.Anthropic(api_key=self._api_key)
        return self._client

    def decide_next_action(self, goal: str,
                           screenshot: Optional[bytes],
                           history: Sequence[AgentStep],
                           ) -> Dict[str, Any]:
        # Track the previous turn's tool_result, if any.
        self._ingest_history(history)
        # Always attach the latest screenshot so the model has fresh
        # state — text-only context drifts quickly during a long run.
        user_content = _build_user_content(screenshot)
        self._conversation.append({"role": "user", "content": user_content})
        client = self._resolve_client()
        try:
            response = client.messages.create(
                model=self._model,
                system=self._build_system(goal),
                tools=self._tools,
                messages=self._conversation,
                max_tokens=self._max_tokens,
            )
        except Exception as exc:  # noqa: BLE001  rewrap to a clear backend error
            raise AgentBackendError(
                f"anthropic call failed: {exc}",
            ) from exc
        return self._handle_response(response)

    # --- response parsing -------------------------------------------

    def _handle_response(self, response: Any) -> Dict[str, Any]:
        """Pull the first tool_use / final text out of a Messages reply."""
        content = list(getattr(response, "content", []) or [])
        self._conversation.append({"role": "assistant", "content": content})
        for block in content:
            block_type = (
                block.get("type") if isinstance(block, dict)
                else getattr(block, "type", None)
            )
            if block_type == "tool_use":
                return {
                    "tool": _attr(block, "name"),
                    "input": _attr(block, "input") or {},
                    "_tool_use_id": _attr(block, "id"),
                }
        # No tool_use — interpret the text as a final answer + stop.
        text_parts: List[str] = []
        for block in content:
            block_type = (
                block.get("type") if isinstance(block, dict)
                else getattr(block, "type", None)
            )
            if block_type == "text":
                text_parts.append(_attr(block, "text") or "")
        return {"stop": True, "message": "\n".join(text_parts).strip()}

    def _ingest_history(self, history: Sequence[AgentStep]) -> None:
        """Append last tool's result to the running conversation."""
        if not history:
            return
        last = history[-1]
        if last.tool is None:
            return
        # The previous turn's _handle_response stored an assistant
        # message with the tool_use id; we now append the user-side
        # tool_result block keyed by that id so Anthropic threads the
        # result back to the matching call.
        tool_use_id = _last_tool_use_id(self._conversation)
        if tool_use_id is None:
            return
        result_content = (
            str(last.error) if last.error else str(last.result),
        )
        self._conversation.append({
            "role": "user",
            "content": [{
                "type": "tool_result",
                "tool_use_id": tool_use_id,
                "content": result_content[0],
                "is_error": bool(last.error),
            }],
        })


def _build_user_content(screenshot: Optional[bytes]) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    encoded = encode_screenshot_b64(screenshot)
    if encoded:
        blocks.append({
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": "image/png",
                "data": encoded,
            },
        })
    blocks.append({
        "type": "text",
        "text": "Latest screenshot above. Pick the next AC_* tool to call.",
    })
    return blocks


def _attr(block: Any, name: str) -> Any:
    if isinstance(block, dict):
        return block.get(name)
    return getattr(block, name, None)


def _last_tool_use_id(conversation: Sequence[Dict[str, Any]]) -> Optional[str]:
    """Walk the conversation backwards for the most recent tool_use id."""
    for msg in reversed(conversation):
        if msg.get("role") != "assistant":
            continue
        for block in msg.get("content") or []:
            block_type = (
                block.get("type") if isinstance(block, dict)
                else getattr(block, "type", None)
            )
            if block_type == "tool_use":
                return _attr(block, "id")
    return None


__all__ = ["AnthropicAgentBackend"]
