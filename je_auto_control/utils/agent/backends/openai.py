"""OpenAI ChatCompletions backend for the AgentLoop."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

from je_auto_control.utils.agent.agent_loop import AgentBackend, AgentStep
from je_auto_control.utils.agent.backends.base import (
    AgentBackendError, build_default_system_prompt, encode_screenshot_b64,
)


_DEFAULT_MODEL = "gpt-4o"


class OpenAIAgentBackend(AgentBackend):
    """Drive the agent loop with OpenAI Chat Completions + function calling.

    Tools should be in OpenAI ``functions`` format — Phase 7.8's
    :func:`export_openai_tools` produces that shape directly. The
    SDK (``pip install openai``) is lazy-imported.
    """

    def __init__(self,
                 *, tools: Sequence[Dict[str, Any]],
                 client: Optional[Any] = None,
                 api_key: Optional[str] = None,
                 model: str = _DEFAULT_MODEL,
                 system_prompt_builder: Optional[Any] = None) -> None:
        if not tools:
            raise AgentBackendError(
                "OpenAIAgentBackend requires a non-empty tool list "
                "(see export_openai_tools()).",
            )
        self._tools = list(tools)
        self._client = client
        self._api_key = api_key
        self._model = model
        self._build_system = system_prompt_builder or build_default_system_prompt
        self._messages: List[Dict[str, Any]] = []
        self._pending_tool_call_id: Optional[str] = None

    def _resolve_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import openai  # nosemgrep: codacy.python.openai.import-without-guardrails  # reason: Guardrails is an unrelated content-filter SDK; we apply content safety at the action-executor allowlist + audit layer
        except ImportError as exc:
            raise AgentBackendError(
                "openai SDK not installed (pip install openai).",
            ) from exc
        self._client = openai.OpenAI(api_key=self._api_key)
        return self._client

    def decide_next_action(self, goal: str,
                           screenshot: Optional[bytes],
                           history: Sequence[AgentStep],
                           ) -> Dict[str, Any]:
        self._seed_system(goal)
        self._ingest_history(history)
        self._messages.append(
            {"role": "user", "content": _build_user_content(screenshot)},
        )
        client = self._resolve_client()
        try:
            response = client.chat.completions.create(
                model=self._model,
                messages=self._messages,
                tools=self._tools,
                tool_choice="auto",
            )
        except Exception as exc:  # noqa: BLE001  rewrap to a clear backend error
            raise AgentBackendError(
                f"openai call failed: {exc}",
            ) from exc
        return self._handle_response(response)

    # --- helpers -----------------------------------------------------

    def _seed_system(self, goal: str) -> None:
        if not self._messages:
            self._messages.append({
                "role": "system",
                "content": self._build_system(goal),
            })

    def _ingest_history(self, history: Sequence[AgentStep]) -> None:
        if not history or self._pending_tool_call_id is None:
            return
        last = history[-1]
        if last.tool is None:
            return
        body = str(last.error) if last.error else str(last.result)
        self._messages.append({
            "role": "tool",
            "tool_call_id": self._pending_tool_call_id,
            "content": body,
        })
        self._pending_tool_call_id = None

    def _handle_response(self, response: Any) -> Dict[str, Any]:
        choice = response.choices[0]
        message = choice.message
        tool_calls = getattr(message, "tool_calls", None) or []
        # Persist the assistant message so the next turn can chain a
        # ``role: tool`` message back to the right tool_call_id.
        self._messages.append(_normalize_assistant(message))
        if tool_calls:
            call = tool_calls[0]
            fn = call.function
            try:
                args = json.loads(fn.arguments) if fn.arguments else {}
            except json.JSONDecodeError:
                args = {}
            self._pending_tool_call_id = call.id
            return {"tool": fn.name, "input": args}
        # No tool call → final answer.
        text = getattr(message, "content", None) or ""
        return {"stop": True, "message": text.strip() if isinstance(text, str) else ""}


def _build_user_content(screenshot: Optional[bytes]) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    encoded = encode_screenshot_b64(screenshot)
    if encoded:
        blocks.append({
            "type": "image_url",
            "image_url": {
                "url": f"data:image/png;base64,{encoded}",
            },
        })
    blocks.append({
        "type": "text",
        "text": "Latest screenshot above. Pick the next AC_* tool to call.",
    })
    return blocks


def _normalize_assistant(message: Any) -> Dict[str, Any]:
    """Convert an OpenAI assistant Message object into a dict for replay."""
    out: Dict[str, Any] = {"role": "assistant"}
    content = getattr(message, "content", None)
    if content:
        out["content"] = content
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        out["tool_calls"] = [{
            "id": call.id,
            "type": "function",
            "function": {
                "name": call.function.name,
                "arguments": call.function.arguments or "{}",
            },
        } for call in tool_calls]
    return out


__all__ = ["OpenAIAgentBackend"]
