"""Message blocks of the Anthropic computer-use conversation.

Reading a response (block type and attributes, truncation, the final answer)
and building what goes back (the first user turn, a ``tool_result``). Shared
by both request shapes of :mod:`.anthropic_computer_use`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from je_auto_control.utils.agent.agent_loop import AgentStep
from je_auto_control.utils.agent.backends.base import (
    AgentBackendError, encode_screenshot_b64,
)


def _final_answer(response: Any, content: List[Any]) -> Dict[str, Any]:
    """A turn without tool calls: the final answer (a truncated turn was refused earlier)."""
    text_parts: List[str] = [
        _attr(b, "text") or ""
        for b in content if _block_type(b) == "text"
    ]
    return {"stop": True, "message": "\n".join(text_parts).strip()}


_TRUNCATION_STOP_REASONS = frozenset({"max_tokens", "refusal"})


def _raise_if_truncated(response: Any) -> None:
    """Reject an incomplete turn instead of treating it as a final answer."""
    stop_reason = _attr(response, "stop_reason")
    if stop_reason in _TRUNCATION_STOP_REASONS:
        raise AgentBackendError(
            "anthropic computer-use response was incomplete "
            f"(stop_reason={stop_reason!r})",
        )


def _block_type(block: Any) -> Optional[str]:
    if isinstance(block, dict):
        return block.get("type")
    return getattr(block, "type", None)


def _attr(block: Any, name: str) -> Any:
    if isinstance(block, dict):
        return block.get(name)
    return getattr(block, name, None)


def _initial_user_content(goal: str,
                           screenshot: Optional[bytes]) -> List[Dict[str, Any]]:
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
    blocks.append({"type": "text", "text": goal})
    return blocks


def _tool_result_content(step: AgentStep, screenshot: Optional[bytes],
                         scale: Tuple[float, float] = (1.0, 1.0)) -> List[Dict[str, Any]]:
    """Build a ``tool_result`` content payload for the last ``AC_*`` call.

    Anthropic's spec expects the screenshot tool to return the image
    *itself* — text-only results just describe what happened. The cursor
    position is given in the screenshot's pixels, where the model works:
    in screen pixels it named a point off the image it was shown.
    """
    if not step.error and step.tool == "AC_get_mouse_position":
        return [{"type": "text", "text": _scaled_point(step.result, scale)}]
    if step.error:
        return [{"type": "text", "text": f"error: {step.error}"}]
    if step.tool == "AC_screenshot":
        encoded = encode_screenshot_b64(screenshot)
        if encoded:
            return [{
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": "image/png",
                    "data": encoded,
                },
            }]
    text = repr(step.result) if step.result is not None else "ok"
    return [{"type": "text", "text": text[:4000]}]


def _scaled_point(point: Any, scale: Tuple[float, float]) -> str:
    """A screen point in screenshot pixels, as text; anything else as it came."""
    if (isinstance(point, (list, tuple)) and len(point) == 2
            and all(isinstance(v, (int, float)) and not isinstance(v, bool) for v in point)):
        return repr((int(round(point[0] * scale[0])), int(round(point[1] * scale[1]))))
    return repr(point)
