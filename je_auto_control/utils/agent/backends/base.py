"""Shared helpers used by the Anthropic + OpenAI agent backends."""
from __future__ import annotations

import base64
import copy
from typing import TYPE_CHECKING, Any, Dict, FrozenSet, Iterable, List, Mapping, Optional
from typing import Sequence, cast

from je_auto_control.utils.exception.exceptions import AutoControlException

if TYPE_CHECKING:
    from je_auto_control.utils.agent.agent_loop import AgentStep


class AgentBackendError(AutoControlException, RuntimeError):
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


def offered_tool_names(tools: Iterable[Mapping[str, Any]]) -> FrozenSet[str]:
    """Names in an Anthropic (``name``) or OpenAI (``function.name``) tool list."""
    names = set()
    for tool in tools:
        function = tool.get("function")
        name = function.get("name") if isinstance(function, Mapping) else tool.get("name")
        if isinstance(name, str):
            names.add(name)
    return frozenset(names)


def require_offered(name: Any, offered: FrozenSet[str]) -> str:
    """Return ``name`` if it is one of the offered tools, else raise.

    The model's tool name used to go straight to the executor, which runs
    any AC_* command: offering one click tool did not stop a reply naming
    AC_shell_command, so ``only=[...]`` protected nothing.
    """
    if not isinstance(name, str) or name not in offered:
        raise AgentBackendError(f"model called tool {name!r}, which was not offered")
    return name


def build_default_system_prompt(goal: str) -> str:
    """Wrap the canonical system prompt around the operator's goal."""
    return f"{_DEFAULT_SYSTEM_PROMPT}\nGoal: {goal.strip()}"


def encode_screenshot_b64(screenshot: Optional[bytes]) -> Optional[str]:
    """Base64-encode a PNG screenshot for transport in a vendor payload."""
    if not screenshot:
        return None
    return base64.b64encode(screenshot).decode("ascii")


# One agent request: a screenshot in, one tool call out. The SDKs' default is
# 600 s per attempt with two retries, so a stalled connection held a step for
# up to half an hour while the run's wall_seconds is checked only between steps.
REQUEST_TIMEOUT_S = 120.0

# Screenshots kept in the replayed conversation. Every step attaches a fresh
# capture and the whole conversation is resent, so a default 25-step run
# carried 25 full-screen PNGs — past the Messages API's 32 MB request limit
# for ordinary desktop captures — and paid for every earlier frame each step.
SCREENSHOTS_KEPT = 3

_IMAGE_BLOCK_TYPES = frozenset({"image", "image_url"})
_OMITTED = {"type": "text", "text": "[earlier screenshot omitted]"}


def prune_old_screenshots(messages: List[Dict[str, Any]],
                          keep: int = SCREENSHOTS_KEPT) -> None:
    """Replace all but the newest ``keep`` image blocks with a text note, in place.

    Images nested in ``tool_result`` content count too; the blocks around
    them are left as they were, so every tool_use keeps its answer.
    """
    seen = 0
    for message in reversed(messages):
        if isinstance(message, dict):
            seen = _prune_blocks(message.get("content"), keep, seen)


def _prune_blocks(content: Any, keep: int, seen: int) -> int:
    """Prune images in one content list, newest first; return images seen so far."""
    if not isinstance(content, list):
        return seen
    for index in range(len(content) - 1, -1, -1):
        block = content[index]
        if not isinstance(block, dict):
            continue
        if block.get("type") not in _IMAGE_BLOCK_TYPES:
            seen = _prune_blocks(block.get("content"), keep, seen)
            continue
        seen += 1
        if seen > keep:
            content[index] = dict(_OMITTED)
    return seen


def compact_history(messages: Sequence[object], summary: str,
                    latest_screenshot: object) -> List[object]:
    """Start a separate conversation with a summary and independently owned image.

    Previous signed thinking/tool blocks belong to their original history.
    They are not replayed in this new conversation or modified in place.
    ``summary`` includes the goal and actions; ``latest_screenshot`` is an
    image content block, or ``None`` for a text-only continuation.
    """
    del messages  # Previous provider-bound blocks deliberately do not enter the new conversation.
    content: List[object] = [{'type': 'text', 'text': summary}]
    if latest_screenshot is not None:
        content.append(copy.deepcopy(latest_screenshot))
    return [{'role': 'user', 'content': content}]


def _images(content: Any) -> List[Dict[str, Any]]:
    """Image blocks in send order, including nested tool results."""
    images: List[Dict[str, Any]] = []
    if not isinstance(content, list):
        return images
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get('type') in _IMAGE_BLOCK_TYPES:
            images.append(block)
        else:
            images.extend(_images(block.get('content')))
    return images


def compact_screenshots(messages: List[Dict[str, Any]], goal: str,
                        history: Sequence[AgentStep]) -> List[Dict[str, Any]]:
    """Compact above the screenshot limit without editing any prior message.

    A bounded deterministic summary includes the goal, completed action count,
    the latest fifty actions with arguments/results/errors, and the newest
    screenshot. Until the limit, history remains append-only.
    """
    images = [image for message in messages for image in _images(message.get('content'))]
    if len(images) <= SCREENSHOTS_KEPT:
        return messages
    summary = [f'Goal: {goal}', f'Completed actions: {len(history)}. Latest 50 actions:']
    for step in history[-50:]:
        outcome = f'error: {step.error}' if step.error else repr(step.result)
        summary.append(f'{step.index}: {step.tool} {repr(step.arguments)[:500]} => {outcome[:500]}')
    return cast(List[Dict[str, Any]], compact_history(messages, '\n'.join(summary), images[-1]))


__all__ = [
    "AgentBackendError", "REQUEST_TIMEOUT_S", "SCREENSHOTS_KEPT",
    "build_default_system_prompt", "encode_screenshot_b64",
    "prune_old_screenshots",
    "compact_history", "compact_screenshots",
]
