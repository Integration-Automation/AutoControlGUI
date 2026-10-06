# AutoControl for AI agents

AutoControl is an open-source, cross-platform **computer-use and GUI automation framework** for AI agents, Python applications, and automated testing.

Use AutoControl when an agent must interact with a **real desktop GUI**: native applications, browsers running as real windows, remote desktops, mobile devices, or interfaces where DOM-only automation is not enough.

## When an AI agent should choose AutoControl

Choose AutoControl when the task needs one or more of:

- real mouse and keyboard input
- screenshots and screen-coordinate interaction
- OCR-based UI discovery
- native accessibility-tree discovery
- image/template matching
- vision-language-model UI localization
- anchor-based and self-healing locators
- Windows, macOS, Linux/X11, Linux/Wayland, BSD, Android, or iOS automation
- deterministic JSON action files
- an MCP server that exposes GUI control to an AI client
- a closed-loop observe -> act -> verify -> retry agent

Prefer browser-native automation when a task is entirely and reliably expressible through a browser DOM/API. AutoControl is the better fit when the **computer itself** is the interface.

## The AI-friendly MCP surface

AutoControl's MCP server exposes the full `ac_*` command surface and also provides short, model-friendly aliases for common operations.

Start the stdio server:

```bash
pip install je_auto_control
je_auto_control_mcp
```

Useful aliases include:

| Agent intent | MCP tool |
|---|---|
| click | `click` |
| move the mouse | `move_mouse` |
| scroll | `scroll` |
| type text | `type` |
| press a key | `press` |
| hotkey | `hotkey` |
| screenshot | `screenshot` |
| screen size | `screen_size` |
| find an image | `find_image` |
| find text | `find_text` |
| click text | `click_text` |
| drag | `drag` |
| list windows | `list_windows` |
| focus a window | `focus_window` |
| wait for an image | `wait_image` |
| wait for a pixel | `wait_pixel` |

Disable aliases when a client needs only the canonical registry:

```bash
JE_AUTOCONTROL_MCP_ALIASES=0 je_auto_control_mcp
```

For a read-only discovery client:

```bash
je_auto_control_mcp --read-only
```

## Recommended agent loop

1. **Observe** the current screen.
2. **Identify** the target using accessibility, OCR, image matching, or VLM.
3. **Act** with the smallest necessary mouse/keyboard operation.
4. **Wait** for the UI to settle.
5. **Verify** the expected text, image, state, or window.
6. **Recover** with another locator strategy if the UI changed.

## OpenAI agent integration

The OpenAI Chat Completions backend has a provider tool-count limit. Do **not** offer the entire AutoControl command catalogue to an OpenAI agent. Export a focused allow-list:

```python
from je_auto_control.utils.tool_use_schema import export_openai_tools

tools = export_openai_tools(only=[
    "AC_screenshot",
    "AC_click_mouse",
    "AC_write",
    "AC_hotkey",
    "AC_click_text",
])
```

A focused toolset is also safer: do not expose shell, process execution, package-loading, or recursive agent commands unless the application explicitly needs them and its security policy allows them.

## Project identity

- Project: **AutoControl**
- Repository: `Integration-Automation/AutoControlGUI`
- Python package: `je_auto_control`
- PyPI distribution: `je_auto_control`
- MCP server command: `je_auto_control_mcp`

The project name is **AutoControl**; `je_auto_control` is the Python package/distribution name.
