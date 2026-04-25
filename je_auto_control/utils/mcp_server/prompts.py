"""MCP prompt catalogue for AutoControl.

Prompts are reusable task templates the MCP client can surface to the
user (typically as slash-command suggestions). The default catalogue
seeds a few common automation flows — recording-and-generalising,
visual-diff comparison, semantic widget targeting — so the model has
a quick path to common requests without re-deriving the recipe.
"""
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional


@dataclass(frozen=True)
class MCPPromptArgument:
    """One argument descriptor on a prompt template."""

    name: str
    description: Optional[str] = None
    required: bool = False

    def to_descriptor(self) -> Dict[str, Any]:
        descriptor: Dict[str, Any] = {"name": self.name,
                                       "required": self.required}
        if self.description is not None:
            descriptor["description"] = self.description
        return descriptor


@dataclass(frozen=True)
class MCPPrompt:
    """A single prompt template: name, args, and a render callback."""

    name: str
    description: str
    arguments: List[MCPPromptArgument] = field(default_factory=list)
    render: Optional[Callable[[Dict[str, Any]], str]] = None

    def to_descriptor(self) -> Dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "arguments": [arg.to_descriptor() for arg in self.arguments],
        }

    def get(self, arguments: Dict[str, Any]) -> Dict[str, Any]:
        """Return the MCP ``prompts/get`` response payload."""
        for arg in self.arguments:
            if arg.required and arg.name not in arguments:
                raise ValueError(
                    f"prompt {self.name!r} requires argument {arg.name!r}"
                )
        text = (self.render(arguments) if self.render is not None
                else self.description)
        return {
            "description": self.description,
            "messages": [{
                "role": "user",
                "content": {"type": "text", "text": text},
            }],
        }


class PromptProvider:
    """Pluggable prompt source. Subclasses override list / get."""

    def list(self) -> List[MCPPrompt]:  # pragma: no cover - abstract
        raise NotImplementedError

    def get(self, name: str,
            arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        raise NotImplementedError


class StaticPromptProvider(PromptProvider):
    """Wraps a fixed list of :class:`MCPPrompt` objects."""

    def __init__(self, prompts: List[MCPPrompt]) -> None:
        self._prompts: Dict[str, MCPPrompt] = {p.name: p for p in prompts}

    def list(self) -> List[MCPPrompt]:
        return list(self._prompts.values())

    def get(self, name: str,
            arguments: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        prompt = self._prompts.get(name)
        if prompt is None:
            return None
        return prompt.get(arguments)


# === Default catalogue ======================================================

def _automate_ui_task(args: Dict[str, Any]) -> str:
    task = args.get("task", "<describe the task>")
    return (
        "You are driving the host machine through AutoControl's MCP "
        "tools.\n\n"
        f"Goal: {task}\n\n"
        "Plan and execute step-by-step. Prefer in this order:\n"
        "1. ac_a11y_find / ac_a11y_click for known widgets\n"
        "2. ac_locate_text / ac_click_text when text is visible on screen\n"
        "3. ac_locate_image_center / ac_locate_and_click for icons\n"
        "4. ac_vlm_locate / ac_vlm_click as a last-resort fallback\n\n"
        "Take a screenshot (ac_screenshot) before destructive actions so "
        "you can verify state. Ask the user to confirm before issuing "
        "irreversible operations (closing a window, executing a script "
        "file, etc.)."
    )


def _record_and_generalize(args: Dict[str, Any]) -> str:
    name = args.get("script_name", "recording.json")
    return (
        "Record a manual demonstration and generalise it into a reusable "
        "script.\n\n"
        "1. Call ac_record_start. Tell the user when recording is live.\n"
        "2. Wait for them to finish, then call ac_record_stop.\n"
        "3. Inspect the captured action list. Replace literal coordinates "
        "with semantic targeting where possible (ac_a11y_find names, "
        "ac_locate_text strings).\n"
        "4. Use ac_adjust_delays / ac_scale_coordinates to make the "
        "script resolution-independent if the user asks.\n"
        f"5. Persist the result with ac_write_action_file file_path={name!r}.\n"
    )


def _compare_screenshots(args: Dict[str, Any]) -> str:
    label = args.get("label", "before / after")
    return (
        f"Compare two screenshots ({label}). Use ac_screenshot to grab "
        "both frames so you can see them, describe each panel's layout, "
        "and call out every change you can identify (text, controls, "
        "highlighted state, error dialogs). Finish with a one-paragraph "
        "summary of what changed."
    )


def _find_widget(args: Dict[str, Any]) -> str:
    widget = args.get("description", "<the widget>")
    return (
        f"Locate {widget} on screen. Try the cheapest, most reliable "
        "approach first:\n"
        f"1. ac_a11y_find with name and/or role matching {widget}.\n"
        "2. ac_locate_text if the widget has visible label text.\n"
        "3. ac_locate_image_center against a saved template if you have one.\n"
        "4. ac_vlm_locate as a last resort.\n"
        "Report the screen coordinates and the strategy that worked, "
        "or say which strategies failed if nothing matches."
    )


def _explain_action_file(args: Dict[str, Any]) -> str:
    path = args.get("file_path", "<the file>")
    return (
        f"Read the action JSON at {path!r} via ac_read_action_file, then "
        "explain in plain language what running it would do. Group steps "
        "into intent-level bullets ('open the start menu', 'type the "
        "username') rather than translating each AC_* command literally."
    )


def default_prompt_catalogue() -> List[MCPPrompt]:
    """Return the bundled prompt templates."""
    return [
        MCPPrompt(
            name="automate_ui_task",
            description="Plan and execute a desktop automation task end-to-end.",
            arguments=[MCPPromptArgument(
                "task", "Natural-language description of what to accomplish.",
                required=True,
            )],
            render=_automate_ui_task,
        ),
        MCPPrompt(
            name="record_and_generalize",
            description="Capture a manual demo and turn it into a reusable script.",
            arguments=[MCPPromptArgument(
                "script_name", "Where to save the generalised script.",
            )],
            render=_record_and_generalize,
        ),
        MCPPrompt(
            name="compare_screenshots",
            description="Take two screenshots and explain the visual diff.",
            arguments=[MCPPromptArgument(
                "label", "Optional label for the comparison (e.g. 'before/after').",
            )],
            render=_compare_screenshots,
        ),
        MCPPrompt(
            name="find_widget",
            description="Locate a UI widget using the cheapest reliable strategy.",
            arguments=[MCPPromptArgument(
                "description", "Natural-language description of the widget.",
                required=True,
            )],
            render=_find_widget,
        ),
        MCPPrompt(
            name="explain_action_file",
            description="Read an action JSON file and summarise it in plain language.",
            arguments=[MCPPromptArgument(
                "file_path", "Absolute or relative path to the action JSON.",
                required=True,
            )],
            render=_explain_action_file,
        ),
    ]


def default_prompt_provider() -> PromptProvider:
    """Return the bundled prompt provider used by the default MCP server."""
    return StaticPromptProvider(default_prompt_catalogue())


__all__ = [
    "MCPPrompt", "MCPPromptArgument", "PromptProvider",
    "StaticPromptProvider", "default_prompt_catalogue",
    "default_prompt_provider",
]
