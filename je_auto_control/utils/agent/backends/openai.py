"""OpenAI ChatCompletions backend for the AgentLoop."""
from __future__ import annotations

import json
from typing import Any, Dict, List, Optional, Sequence

from je_auto_control.utils.agent.agent_loop import AgentBackend, AgentStep
from je_auto_control.utils.agent.backends.base import (
    REQUEST_TIMEOUT_S, AgentBackendError, build_default_system_prompt,
    encode_screenshot_b64, prune_old_screenshots,
    offered_tool_names, require_offered,
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
        if len(tools) > _MAX_OPENAI_TOOLS:
            # Every request was rejected: AC_run_agent offered all 741 commands.
            raise AgentBackendError(
                f"OpenAI accepts at most {_MAX_OPENAI_TOOLS} tools; got {len(tools)} "
                "(narrow them with only=[...])")
        self._tools = list(tools)
        self._offered = offered_tool_names(self._tools)
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
            # Guardrails is an unrelated content-filter SDK; content safety is
            # applied at the action-executor allowlist and audit layer.
            import openai  # nosemgrep: codacy.python.openai.import-without-guardrails  # reason: see above
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
        if not history:
            # A new run: the last run's system prompt named the last goal.
            self._messages = []
            self._pending_tool_call_id = None
        self._seed_system(goal)
        self._ingest_history(history)
        self._messages.append(
            {"role": "user", "content": _build_user_content(screenshot)},
        )
        prune_old_screenshots(self._messages)
        client = self._resolve_client()
        try:
            response = client.chat.completions.create(
                timeout=REQUEST_TIMEOUT_S,
                model=self._model,
                messages=self._messages,
                tools=self._tools,
                tool_choice="auto",
                # This loop executes and answers only tool_calls[0] each turn,
                # yet the whole assistant message (with every tool_call) is
                # replayed. Parallel calls would leave the rest unanswered and
                # the next request would 400, ending the run.
                parallel_tool_calls=False,
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
        # Capped, as the computer-use backend does: the whole result went
        # into the history and was resent every step.
        body = (str(last.error) if last.error else str(last.result))[:_MAX_RESULT_CHARS]
        self._messages.append({
            "role": "tool",
            "tool_call_id": self._pending_tool_call_id,
            "content": body,
        })
        self._pending_tool_call_id = None

    def _handle_response(self, response: Any) -> Dict[str, Any]:
        choice = next(iter(getattr(response, "choices", None) or ()), None)
        if choice is None:
            raise AgentBackendError("openai returned no choices")
        message = choice.message
        _raise_if_refused(choice)
        tool_calls = getattr(message, "tool_calls", None) or []
        # Persist the assistant message so the next turn can chain a
        # ``role: tool`` message back to the right tool_call_id.
        self._messages.append(_normalize_assistant(message))
        if tool_calls:
            call = tool_calls[0]
            fn = call.function
            name = require_offered(fn.name, self._offered)
            args = _parse_arguments(name, fn.arguments)
            self._pending_tool_call_id = call.id
            return {"tool": name, "input": args}
        # No tool call → final answer, unless the turn was truncated at the
        # token cap: returning a length-cut reply as the final answer would
        # silently end the run mid-plan.
        _raise_if_truncated(choice)
        text = getattr(message, "content", None) or ""
        return {"stop": True, "message": text.strip() if isinstance(text, str) else ""}


#: The Chat Completions API's documented tool limit.
_MAX_OPENAI_TOOLS = 128
#: The longest tool result kept in the conversation.
_MAX_RESULT_CHARS = 4000


def _parse_arguments(name: str, raw: Any) -> Dict[str, Any]:
    """The tool call's JSON arguments, which must be an object.

    Unparsable arguments used to become ``{}`` and the tool still ran -- a
    truncated click became a click wherever the cursor was -- and a JSON
    list or string crashed the run from ``dict()``.
    """
    if not raw:
        return {}
    try:
        args = json.loads(raw)
    except (TypeError, ValueError) as error:
        raise AgentBackendError(f"arguments for {name!r} are not valid JSON") from error
    if not isinstance(args, dict):
        raise AgentBackendError(f"arguments for {name!r} must be a JSON object")
    return args


def _raise_if_refused(choice: Any) -> None:
    """A refusal or a filtered reply is not a final answer: it counted as success."""
    refusal = getattr(choice.message, "refusal", None)
    if refusal:
        raise AgentBackendError(f"openai refused: {refusal}")
    if getattr(choice, "finish_reason", None) == "content_filter":
        raise AgentBackendError("openai response withheld by its content filter")


def _raise_if_truncated(choice: Any) -> None:
    """Reject a length-truncated turn instead of returning it as final."""
    if getattr(choice, "finish_reason", None) == "length":
        raise AgentBackendError(
            "openai response truncated (finish_reason='length')",
        )


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
