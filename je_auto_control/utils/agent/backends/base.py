"""Shared helpers used by the Anthropic + OpenAI agent backends."""
from __future__ import annotations

import base64
import json
from typing import Any, Dict, FrozenSet, Iterable, List, Mapping, Optional, Sequence, Tuple

from je_auto_control.utils.exception.exceptions import AutoControlException


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
# The OpenAI backend drops the older ones in place (prune_old_screenshots);
# the Anthropic backends start a new history instead (compact_history).
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


# --- append-only histories (Anthropic) -------------------------------
#
# prune_old_screenshots edits turns the API has already seen. On the Anthropic
# backends that is not allowed: the prompt cache is a prefix match, so every
# step missed it, and a thinking block is valid only in front of the exact
# conversation that produced it, so the replayed turns were refused with
# HTTP 400 ("bound to a different conversation"). Those backends instead
# leave sent turns alone and, once the screenshots pass the limit, open a new
# history: one summary message plus the current screenshot, nothing replayed.

#: Base64 characters of screenshots a request may carry. The Messages API
#: refuses a request over 32 MB; this leaves the rest of it a wide margin.
MAX_IMAGE_CHARS = 20_000_000

#: The most recent actions a summary lists, and the characters kept of each
#: action's arguments and outcome.
_SUMMARY_STEPS = 60
_SUMMARY_FIELD_CHARS = 240

_SUMMARY_HEAD = (
    "This session continues a task that is already under way. The earlier "
    "conversation is not included; this message is the record of it."
)
_SUMMARY_TAIL = (
    "The attached screenshot shows the whole screen as it is now, after all "
    "of the actions above. Continue toward the goal from this state: do not "
    "repeat an action that already succeeded, and when the goal is met, stop "
    "and say so."
)


def _image_stats(content: Any) -> Tuple[int, int]:
    """``(images, base64 characters)`` in one content list, nested ones included."""
    if not isinstance(content, list):
        return 0, 0
    count = chars = 0
    for block in content:
        if not isinstance(block, dict):
            continue
        if block.get("type") in _IMAGE_BLOCK_TYPES:
            source = block.get("source")
            data = source.get("data") if isinstance(source, dict) else None
            count += 1
            chars += len(data) if isinstance(data, str) else 0
            continue
        nested = _image_stats(block.get("content"))
        count += nested[0]
        chars += nested[1]
    return count, chars


def _history_image_stats(messages: Sequence[Any]) -> Tuple[int, int]:
    count = chars = 0
    for message in messages:
        if isinstance(message, dict):
            found = _image_stats(message.get("content"))
            count += found[0]
            chars += found[1]
    return count, chars


def count_screenshots(messages: Sequence[Any]) -> int:
    """Image blocks in ``messages``, those inside a ``tool_result`` included."""
    return _history_image_stats(messages)[0]


def needs_compaction(messages: Sequence[Any], incoming: Any, *,
                     keep: int = SCREENSHOTS_KEPT,
                     max_image_chars: int = MAX_IMAGE_CHARS) -> bool:
    """Whether appending the content list ``incoming`` passes the screenshot limits.

    Only a turn that brings a screenshot can pass them, so a history is
    never restarted for a text-only turn.
    """
    new_count, new_chars = _image_stats(incoming)
    if not new_count:
        return False
    count, chars = _history_image_stats(messages)
    return count + new_count > keep or chars + new_chars > max_image_chars


def _clip(text: str) -> str:
    if len(text) <= _SUMMARY_FIELD_CHARS:
        return text
    return text[:_SUMMARY_FIELD_CHARS] + "..."


def _step_line(number: int, step: Any) -> str:
    """One executed action: its tool, arguments and outcome, each bounded."""
    try:
        arguments = json.dumps(step.arguments or {}, ensure_ascii=False, default=repr)
    except (TypeError, ValueError):
        arguments = repr(step.arguments)
    if step.error:
        outcome = f"error: {step.error}"
    elif step.result is None:
        outcome = "ok"
    else:
        outcome = str(step.result)
    return f"{number}. {step.tool} {_clip(arguments)} -> {_clip(outcome)}"


def summarise_steps(goal: str, history: Sequence[Any]) -> str:
    """The summary a restarted history opens with: the goal and the actions run so far.

    ``history`` is the loop's ``AgentStep`` list. The newest actions are
    listed in full; a very long run says how many older ones are left out.
    """
    steps = [step for step in history if getattr(step, "tool", None)]
    lines = [_SUMMARY_HEAD, "", f"Goal: {goal.strip()}", ""]
    if not steps:
        lines.append("No action has been executed yet.")
    else:
        skipped = max(0, len(steps) - _SUMMARY_STEPS)
        lines.append("Actions executed so far, oldest first (tool, arguments -> outcome):")
        if skipped:
            lines.append(f"({skipped} earlier actions are not listed.)")
        lines.extend(_step_line(skipped + offset + 1, step)
                     for offset, step in enumerate(steps[skipped:]))
    lines.extend(["", _SUMMARY_TAIL])
    return "\n".join(lines)


def image_block(screenshot: Optional[bytes]) -> Optional[Dict[str, Any]]:
    """A PNG as an Anthropic base64 image block, or ``None`` without one."""
    encoded = encode_screenshot_b64(screenshot)
    if not encoded:
        return None
    return {"type": "image",
            "source": {"type": "base64", "media_type": "image/png", "data": encoded}}


def compact_history(messages: Sequence[Any], summary: str,
                    latest_screenshot: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """A new Anthropic history: one user message with the screenshot and ``summary``.

    Nothing of ``messages`` is carried over and it is not modified: a turn
    replayed behind a summary would bring thinking blocks made in front of a
    different conversation, and a ``tool_result`` whose ``tool_use`` is gone.
    Call it only between tool rounds, with every executed call's outcome in
    ``summary``. ``latest_screenshot`` is an image block (:func:`image_block`).
    """
    del messages    # the old history is deliberately not read
    content: List[Dict[str, Any]] = []
    if latest_screenshot is not None:
        content.append(latest_screenshot)
    content.append({"type": "text", "text": summary})
    return [{"role": "user", "content": content}]


__all__ = [
    "AgentBackendError", "MAX_IMAGE_CHARS", "REQUEST_TIMEOUT_S", "SCREENSHOTS_KEPT",
    "build_default_system_prompt", "compact_history", "count_screenshots",
    "encode_screenshot_b64", "image_block", "needs_compaction",
    "prune_old_screenshots", "summarise_steps",
]
