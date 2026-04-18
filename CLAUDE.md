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

## Static Analysis Compliance (SonarQube / Codacy / Pylint / Bandit)

All code must satisfy the following rules so automated scanners (SonarQube, Codacy, Pylint, Bandit, Radon, Prospector) report zero new issues.

### Complexity & Size Limits

- **Cyclomatic complexity** per function ≤ 10. Refactor with early returns, extracted helpers, or lookup dicts when exceeded.
- **Cognitive complexity** per function ≤ 15 (SonarQube `python:S3776`).
- **Function length** ≤ 75 lines. Long procedural flows must be split into named helpers.
- **Parameter count** ≤ 7 (`python:S107`). Group related parameters into a dataclass or config object when exceeded.
- **Nesting depth** ≤ 4 (`python:S134`). Flatten with guard clauses.
- **File length** ≤ 750 lines. Split large modules along responsibility lines.
- **Identical branches**: `if`/`elif`/`else` branches must not have identical bodies (`python:S3923`).
- **Duplicated code**: no duplicated blocks ≥ 10 lines across the project (Sonar default). Extract to a shared helper.

### Bug & Correctness Rules

- **No bare `except:`** — always catch a specific exception type (`python:S5754`, Bandit `B001`).
- **No empty `except` blocks** (`python:S2737`). At minimum log the error or re-raise.
- **Preserve exception chain**: inside `except`, raising a new exception must use `raise NewError(...) from exc` (`python:S5655`).
- **No mutable default arguments** (`python:S5727`): never use `def f(x=[])` or `{}`. Use `None` + lazy init.
- **No unused imports, variables, parameters, or assignments** (`python:S1481`, `S1854`, `S1172`). Remove them; do not rename to `_unused`.
- **No dead / unreachable code** (`python:S1763`).
- **No commented-out code blocks** (`python:S125`) — delete instead; git history preserves it.
- **No `TODO`/`FIXME`/`XXX`** without an issue-tracker reference in the same comment (`python:S1135`).
- **No `print()`** in library code (`je_auto_control/` outside `gui/` stdout tooling). Use the project logger.
- **No `assert` for runtime checks** in non-test code (Bandit `B101`) — `assert` is stripped with `-O`. Raise explicit exceptions.
- **String formatting**: prefer f-strings over `%` or `.format()` for readability; never interpolate untrusted data into shell/SQL.
- **Equality with `None`/`True`/`False`**: use `is` / `is not`, never `==` (`python:S2589`).
- **Boolean simplification**: no `if cond: return True else: return False` — return the expression directly (`python:S1126`).
- **Identical expressions on both sides** of `and`/`or`/`==`/`!=` are forbidden (`python:S1764`).

### Security Rules (Bandit / Sonar Security Hotspots)

- **No `eval`, `exec`, `compile`** on any runtime-sourced string (Bandit `B307`, `B102`).
- **No `pickle`, `marshal`, `shelve`, `dill`** on data from disk, network, or user input (Bandit `B301`, `B302`). Use JSON with schema validation.
- **No `subprocess` with `shell=True`** or string-built command lines (Bandit `B602`, `B605`). Pass argv lists and validate against allowlists.
- **No `os.system`, `os.popen`, `commands.*`** (Bandit `B605`, `B607`).
- **No insecure hash** (`md5`, `sha1`) for security purposes (Bandit `B303`, `B324`). Use `hashlib.sha256` or better.
- **No `tempfile.mktemp`** — use `NamedTemporaryFile` / `mkstemp` (Bandit `B306`).
- **No hardcoded passwords, tokens, or secrets** (Bandit `B105`–`B107`, `python:S2068`).
- **No `yaml.load`** without `SafeLoader` (Bandit `B506`).
- **`requests`/`urllib` calls** must set explicit `timeout=` (`python:S5332`, Bandit `B113`).
- **No `ssl._create_unverified_context` / `verify=False`** (Bandit `B501`).
- **Path traversal**: validate and `os.path.realpath` user-supplied paths before I/O.
- **Socket binds** must default to `127.0.0.1`; `0.0.0.0` requires an explicit, documented opt-in.

### Resource & Concurrency

- **Always use `with`** for files, sockets, locks, and OpenCV `VideoCapture`/`VideoWriter` (`python:S5720`). No manual `close()` in normal flow.
- **Release platform resources** (GDI handles, Quartz event sources, X display) in `finally` or `__exit__`.
- **Thread-safety**: shared mutable state between the socket server, recording thread, and callback executor must be guarded by `threading.Lock` / `queue.Queue`.

### Style & Naming

- **snake_case** for functions, methods, variables, modules; **PascalCase** for classes; **UPPER_SNAKE_CASE** for module-level constants (`python:S117`, Pylint `C0103`).
- **Max line length**: 120 chars (`python:S103`).
- **Docstrings** on every public module, class, and function (`python:S1720`, Pylint `C0114`–`C0116`) — one-line summary minimum; type hints replace parameter-type prose.
- **Import order**: stdlib → third-party → first-party, separated by blank lines; no wildcard imports except in `__init__.py` façade (`python:S2208`).
- **No `global`** statements outside module initialization (`python:S2208`).

### Test Hygiene

- Tests must avoid `assert` against object identity of mutable literals and must not depend on execution order (Pylint / Sonar `python:S5914`).
- No `time.sleep` > 1s in unit tests; use fakes / event signals.

### Automated Verification

Run before every commit; fix all new findings:

```bash
pip install ruff pylint bandit radon
ruff check je_auto_control/
pylint je_auto_control/
bandit -r je_auto_control/ -x je_auto_control/test
radon cc je_auto_control/ -a -nc   # flags functions with CC >= C (>10)
```

If a rule must be suppressed, add an inline justification: `# noqa: <code>  # reason: <why>` or `# nosec B404  # reason: <why>`. Blanket suppressions at file/module level are forbidden.
