# CLAUDE.md — AutoControl

## Project Overview

AutoControl (`je_auto_control`) is a cross-platform Python GUI automation framework supporting Windows (Win32 API), macOS (pyobjc/Quartz), and Linux (X11). It provides mouse/keyboard control, image recognition, screen capture, action scripting, and report generation through a unified API.

- **Package name**: `je_auto_control`
- **Python**: >= 3.10
- **License**: MIT
- **Author**: JE-Chen

## Architecture & Design Patterns

### Strategy Pattern — Platform Abstraction

`wrapper/platform_wrapper.py` auto-detects the OS and loads the correct backend. All wrapper modules (`auto_control_mouse.py`, `auto_control_keyboard.py`, etc.) delegate to the platform-specific implementation. New platform support is added by implementing the backend interface — no wrapper changes needed.

### Facade Pattern — Unified API Surface

`je_auto_control/__init__.py` re-exports all public functions from wrapper and utility modules, providing a single entry point. Users import only `je_auto_control` and access all features.

### Command Pattern — JSON Action Executor

`utils/executor/action_executor.py` maps string command names (e.g., `AC_click_mouse`) to callable functions. JSON action files define sequences of commands with parameters, enabling recording, serialization, and replay of automation flows.

### Observer Pattern — Callback Executor

`utils/callback/callback_function_executor.py` allows registering callback functions that fire after automation actions complete, supporting event-driven chaining.

### Template Method — Report Generation

`utils/generate_report/` provides HTML, JSON, and XML report generators sharing a common structure: collect test records, format output, write file. Each format implements its own rendering.

## Directory Structure

```
je_auto_control/
├── wrapper/              # Platform-agnostic API (Strategy consumers)
├── windows/              # Win32 backend (ctypes)
├── osx/                  # macOS backend (pyobjc/Quartz)
├── linux_with_x11/       # Linux X11 backend (python-Xlib)
├── gui/                  # PySide6 GUI application
└── utils/
    ├── executor/         # JSON action executor (Command pattern)
    ├── callback/         # Callback executor (Observer pattern)
    ├── cv2_utils/        # OpenCV: screenshot, template matching, video
    ├── socket_server/    # TCP server for remote automation
    ├── shell_process/    # Shell command manager
    ├── generate_report/  # HTML/JSON/XML report generators
    ├── test_record/      # Test action recording
    ├── json/             # JSON action file I/O
    ├── project/          # Project scaffolding
    ├── package_manager/  # Dynamic package loading
    ├── logging/          # Logging
    └── exception/        # Custom exceptions
```

## Development Commands

```bash
# Install dependencies
pip install -r dev_requirements.txt

# Install with GUI support
pip install -e .[gui]

# Run unit tests
python -m pytest test/unit_test/

# Run integration tests
python -m pytest test/integrated_test/

# Build package
python -m build
```

## Coding Standards

### Security First

- **Input validation**: Validate all external inputs (user input, file content, network data, JSON action commands) at system boundaries. Sanitize file paths to prevent path traversal. Never trust data from TCP socket clients without validation.
- **Injection prevention**: When executing shell commands (`shell_process`), never construct command strings from unsanitized input. Use parameterized approaches or allowlists.
- **Deserialization safety**: JSON action files and socket server payloads must be validated against expected schemas before execution. Reject unknown command names.
- **No secrets in code**: Never commit credentials, API keys, tokens, or `.env` files. Keep secrets out of logs and reports.
- **Principle of least privilege**: Socket server should bind to localhost by default. Document security implications of exposing to network.
- **Dependency awareness**: Pin dependency versions. Review transitive dependencies for known vulnerabilities.

### Performance Best Practices

- **Lazy imports**: Platform-specific backends are loaded only for the current OS — do not import all backends unconditionally.
- **Avoid redundant screenshots**: Image recognition operations should reuse screen captures when performing multiple searches on the same frame.
- **Buffer management**: Screen recording and video capture must properly release resources (file handles, codec buffers) in `finally` blocks or context managers.
- **Thread safety**: Socket server and recording threads must use proper synchronization. Avoid shared mutable state without locks.
- **Minimize allocations in hot paths**: Mouse/keyboard event dispatch should avoid unnecessary object creation per event.

### Software Engineering Principles

- **SOLID**: Each module has a single responsibility. Platform backends are open for extension (new OS) without modifying wrappers. Depend on abstractions (wrapper API), not concrete implementations (Win32/X11/Quartz).
- **DRY**: Common logic belongs in `wrapper/` or `utils/`, not duplicated across platform backends.
- **YAGNI**: Do not add speculative features. Implement what is needed now.
- **Fail fast**: Raise clear, specific exceptions (`AutoControlMouseException`, `AutoControlKeyboardException`, etc.) at the point of failure. Do not silently swallow errors.
- **Immutable data where possible**: Action lists and configuration should be treated as read-only once loaded.

### Code Style

- Follow PEP 8.
- Use type hints for all public function signatures.
- Keep functions focused and short — one function, one task.
- Prefer composition over inheritance for extending functionality.
- Remove dead code immediately — no commented-out blocks, no unused imports, no unreachable branches.

## Commit Conventions

- Write concise commit messages focused on **why**, not what.
- **Do not mention any AI tools, assistants, or models in commit messages** — no "Co-Authored-By" AI attributions, no references to AI-generated code.
- Use imperative mood: "Add feature", "Fix bug", "Remove unused code".
- Examples:
  - `Add image threshold parameter validation`
  - `Fix mouse scroll direction on macOS`
  - `Remove deprecated screen capture fallback`

## Testing

- **Unit tests**: `test/unit_test/` — test individual functions in isolation.
- **Integration tests**: `test/integrated_test/` — test cross-module workflows.
- **Manual tests**: `test/manual_test/` — require human verification (GUI, visual).
- **GUI tests**: `test/gui_test/` — PySide6 interface tests.
- All tests must pass before merging. Ensure cross-platform compatibility.

## Key Conventions

- All public API functions are exported from `je_auto_control/__init__.py` and listed in `__all__`.
- JSON action command names use `AC_` prefix (e.g., `AC_click_mouse`).
- Platform backends follow naming: `{platform}_{function}.py` (e.g., `win32_ctype_mouse_control.py`).
- Virtual key mappings are in `core/utils/*_vk.py` per platform.
