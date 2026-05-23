"""Shared helpers used by the Anthropic + OpenAI agent backends."""
from __future__ import annotations

import base64
from typing import Optional


class AgentBackendError(RuntimeError):
    """Raised when the vendor SDK is missing or the API call fails."""


_DEFAULT_SYSTEM_PROMPT = (
    "You are AutoControl, a Computer-Use agent. You drive a desktop "
    "by issuing AC_* tool calls (mouse, keyboard, screenshot, "
    "scripting, image-detection, accessibility, vision). You will "
    "receive a screenshot of the current screen each turn. Decide "
    "which AC_* tool to call next, with what arguments, to make "
    "measurable progress toward the user's goal.\n"
    "Rules:\n"
    "  * Call ONE tool per turn and wait for its result before "
    "deciding the next action.\n"
    "  * Use AC_screenshot only when you need a fresh view — the "
    "host already attached the latest screenshot to this turn.\n"
    "  * When the goal is met, stop without calling another tool "
    "and produce a short final message.\n"
    "  * Prefer accessibility-tree / VLM tools (AC_a11y_*, AC_vlm_*) "
    "for clicks where they apply; absolute coordinates are brittle.\n"
)


def build_default_system_prompt(goal: str) -> str:
    """Wrap the canonical system prompt around the operator's goal."""
    return f"{_DEFAULT_SYSTEM_PROMPT}\nGoal: {goal.strip()}"


def encode_screenshot_b64(screenshot: Optional[bytes]) -> Optional[str]:
    """Base64-encode a PNG screenshot for transport in a vendor payload."""
    if not screenshot:
        return None
    return base64.b64encode(screenshot).decode("ascii")


__all__ = [
    "AgentBackendError", "build_default_system_prompt",
    "encode_screenshot_b64",
]
