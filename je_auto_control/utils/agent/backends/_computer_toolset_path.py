"""The GA computer-toolset path of the Anthropic computer-use backend.

``computer_toolset_20260801``: no beta, no declared display size, one call
per member name and possibly several per turn, plus ``zoom``. The request
schema and the batch of queued calls live in :mod:`._computer_toolset`; this
is the part of the backend that reads the toolset's responses and builds its
results. The beta path is :mod:`._computer_beta_path`.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

from je_auto_control.utils.agent.agent_loop import AgentStep
from je_auto_control.utils.agent.backends._computer_actions import (
    _ACTION_HANDLERS, _CLICK_ACTIONS, _clamp_decision,
    _decision_from_computer_action,
)
from je_auto_control.utils.agent.backends._computer_messages import (
    _attr, _block_type, _final_answer, _raise_if_truncated, _tool_result_content,
)
from je_auto_control.utils.agent.backends._computer_toolset import (
    ToolsetBatch, fit_screenshot, screen_region, unscale_decision, zoom_image,
)
from je_auto_control.utils.agent.backends.base import AgentBackendError


class ToolsetPath:
    """Reads the toolset's responses and builds the results of its calls."""

    _conversation: List[Dict[str, Any]]
    _scale: Tuple[float, float]
    _tier: Any
    _display: Tuple[int, int]
    #: tool_use id -> the region a queued ``zoom`` asked for, in screenshot pixels.
    _zooms: Dict[str, Tuple[int, int, int, int]]

    def _fit(self, screenshot: Optional[bytes]) -> Optional[bytes]:
        """``screenshot`` within the toolset's image limits; remembers the scale."""
        if not screenshot:
            return screenshot
        fitted, self._scale = fit_screenshot(screenshot, self._tier)
        return fitted

    def _toolset_result_content(self, step: AgentStep, screenshot: Optional[bytes],
                                tool_use_id: str) -> List[Dict[str, Any]]:
        region = self._zooms.pop(tool_use_id, None)
        if step.tool != "AC_screenshot" or not screenshot:
            return _tool_result_content(step, screenshot, self._scale)
        # A zoom is answered from the full-resolution frame; the scale of the
        # full screenshot stays, since later coordinates are still in its space.
        image = (zoom_image(screenshot, region, self._tier) if region is not None
                 else self._fit(screenshot))
        return _tool_result_content(step, image)

    def _handle_toolset_response(self, response: Any,
                                 batch: ToolsetBatch) -> Dict[str, Any]:
        content = list(getattr(response, "content", []) or [])
        self._conversation.append({"role": "assistant", "content": content})
        self._zooms.clear()
        _raise_if_truncated(response)     # before running any call it holds
        calls = [(_attr(block, "id"), self._toolset_decision(block))
                 for block in content if _block_type(block) == "tool_use"]
        if not calls:
            return _final_answer(response, content)
        batch.load(calls)
        return batch.next_decision()

    def _toolset_decision(self, block: Any) -> Dict[str, Any]:
        """A member call as a decision, in screen pixels and on the display."""
        name = str(_attr(block, "name") or "")
        if name == "zoom":
            return self._zoom_decision(block)
        if name not in _CLICK_ACTIONS and name not in _ACTION_HANDLERS:
            raise AgentBackendError(
                f"model called tool {name!r}; only computer toolset members were offered")
        payload = dict(_attr(block, "input") or {})
        payload["action"] = name       # the member name is the action
        decision = unscale_decision(_decision_from_computer_action(payload), self._scale)
        return _clamp_decision(decision, *self._display)

    def _zoom_decision(self, block: Any) -> Dict[str, Any]:
        """A ``zoom`` runs as a screenshot; its region crops the result."""
        payload = _attr(block, "input") or {}
        try:
            region = screen_region(payload.get("region") if isinstance(payload, dict) else None,
                                   self._scale)
        except (TypeError, ValueError) as error:
            raise AgentBackendError(f"model sent an invalid zoom: {error}") from error
        self._zooms[str(_attr(block, "id"))] = region
        return {"tool": "AC_screenshot", "input": {}}
