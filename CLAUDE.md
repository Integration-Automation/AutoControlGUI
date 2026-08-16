# CLAUDE.md — AutoControl

## Project Overview

AutoControl (`je_auto_control`) is a cross-platform GUI automation framework: mouse and keyboard control, image recognition, OCR, accessibility-tree and VLM element location, action scripting, and report generation behind one API. Backends: Windows (Win32 ctypes), macOS (pyobjc/Quartz), Linux X11 (python-Xlib), Linux Wayland (libei / ydotool), Android (adb), iOS (WebDriverAgent).

- **Package**: `je_auto_control` · **Python** ≥ 3.10 · **License**: MIT · **Author**: JE-Chen
- **[architecture_explore.md](architecture_explore.md)** is the per-module map — read it before changing structure; it lists all 306 `utils/` subpackages, every GUI tab, and file-level tables for the large subsystems.

## Architecture

| Pattern | Where | Contract |
| --- | --- | --- |
| Strategy | `wrapper/platform_wrapper.py` | Detects the OS and imports exactly one backend. New platform = new backend package, no wrapper change. |
| Facade | `je_auto_control/__init__.py` | Re-exports every public name. `api/core.py` is the small versioned façade for new integrations. |
| Command | `utils/executor/action_executor.py` | `event_dict` maps `AC_*` names to callables; `flow_control.py` adds block commands (loop / branch / try / macro / variables). |
| Observer | `utils/callback/`, `utils/observer/`, `utils/triggers/` | Post-action callbacks; screen- and event-driven firing. |
| Template Method | `utils/generate_report/` | HTML / JSON / XML share collect → format → write. |
| Backend seam | `backends/` under `accessibility`, `ocr`, `vision`, `llm`, `agent`, `hotkey`, `usb`, `usbip` | Abstract base + concrete impls + null fallback, so dependency-free environments still import. |

Layering: entry points (`cli.py`, `gui/`, socket / REST / MCP servers) → executor → `utils/` (306 headless subpackages) → `wrapper/` → per-OS backend.

## Development Commands

```bash
pip install -r dev_requirements.txt         # dev deps
pip install -e .[gui]                       # + GUI extra
python -m pytest test/unit_test/headless    # headless unit tests
python -m pytest test/integrated_test/      # cross-module workflows
python -m build                             # build
```

`pyproject.toml` pins `python_files = ["test_*.py"]` on purpose: the `*_test.py` files under `test/unit_test/` are manual demo scripts whose module bodies drive the real mouse and keyboard on import. Never loosen that setting.

## Feature Delivery Rules

### Every feature ships both a headless API and a GUI surface

No feature is complete unless it can be driven entirely without the GUI **and** has a GUI affordance:

- **Headless core in `utils/` or `wrapper/`** — all business logic in a module with zero `PySide6` imports.
- **Re-export from the facade** — add public names to `je_auto_control/__init__.py` and its `__all__`.
- **Executor command** — wire an `AC_*` command into `utils/executor/action_executor.py`, so the feature works from JSON action files, the socket server, the scheduler, and the script builder without Python glue.
- **GUI tab is a thin wrapper** — the Qt widget only translates user input into calls on the headless core; no business logic that would be unreachable headlessly.
- **Tab commands live in the Actions menu, not in-tab buttons** — a tab keeps only inputs, tables, and result views. Core tabs declare `(label_key, handler)` pairs at registration in `gui/main_widget.py`; feature tabs expose `menu_actions()` returning the same shape. Script Builder and Remote Desktop are exempt (interactive panels). `test/unit_test/headless/test_actions_menu_gui.py` fails CI for a tab without either hook.
- **The top-level package stays Qt-free** — `import je_auto_control` MUST NOT import `PySide6`; the GUI loads lazily inside `start_autocontrol_gui()`. Verify: `import sys, je_auto_control; assert not any("PySide6" in m for m in sys.modules)`.
- **Tests cover the headless path** — at least one test in `test/unit_test/` exercising the non-GUI API with no Qt imports.

Inherently interactive features (region picking, template cropping) may stay GUI-only, but must accept programmatic equivalents (e.g. `screenshot(screen_region=[...])`) so scripts replay the same effect headlessly.

### `architecture_explore.md` is updated with every change

The map is only useful while it matches the tree, so **update it in the same change that moves the code**. Required when you add / remove / rename / move a module or subpackage, change what a module is responsible for (the map quotes the docstring's first line — update both), or add or remove an `AC_*` command, GUI tab, platform backend, entry point, extension point, server surface, or `__all__` name.

- **Measure, never estimate** — every count in the document is measured. Re-run rather than adjust by hand:

  ```bash
  python -c "from je_auto_control.utils.executor.action_executor import executor as e; print(len(e.known_commands()))"  # AC_* commands
  python -c "import je_auto_control as ac; print(len(ac.__all__))"                                                      # public API
  python -c "from je_auto_control.utils.mcp_server.tools import build_default_tool_registry as b; print(len(b()))"      # MCP tools
  ```

  Module and line counts come from walking the tree with `ast`; recompute §1, the affected §5.4 theme totals, and the §8 size appendix together so they stay consistent.

- A new `utils/` subpackage needs a row in **exactly one** §5.4 theme table — the tables partition all 306 subpackages; appearing twice or not at all is a defect.
- A new subsystem over ~1,000 lines also needs a file-level table in §5.4.17.
- Keep the header's scan date, version, and branch current.
- `README.md` and both translations under `README/` cite the same figures (command / subpackage / tab / MCP-tool / example counts) — update all three alongside the map.

### Outstanding work goes in `Progress.md`

Anything agreed but not done — deferred follow-ups, known gaps, half-delivered features, decisions waiting on the maintainer — is recorded in [Progress.md](Progress.md), not left in chat history or buried in a commit message.

- **Write the entry when you defer the work**, in the same change that created the gap. Each entry states its status (`TODO` / `WIP` / `BLOCKED` / `DECIDE`), what is missing, and where in the tree.
- **Open items only.** Delete the entry when the work lands; shipped work is described in `WHATS_NEW.md` and compatibility changes in `CHANGELOG.md`. `Progress.md` is not a changelog.
- A feature that reaches only some of the delivery surfaces above belongs here until the rest land.

## Coding Standards

### Project-specific rules

- **Exception hierarchy is flat by design** — every framework error derives from `AutoControlException` so containment boundaries (executor, background poll loops, request handlers, GUI slots) can catch the family in one `except`. Never add a sibling inheriting `Exception` directly; it silently escapes every boundary. Assertion failures (`AutoControlAssertionException`) must keep propagating through `raise_on_error=False`.
- **Fail fast** — raise the specific typed exception at the point of failure; do not swallow errors.
- **Validate at boundaries** — user input, file content, network data, and JSON action commands. Reject unknown command names; `realpath` and bound user-supplied paths.
- **Least privilege** — servers bind `127.0.0.1` by default; `0.0.0.0` needs an explicit, documented opt-in.
- **No `print()` in library code** (`je_auto_control/` outside `gui/` stdout tooling) — use `autocontrol_logger`.
- **No `assert` for runtime checks** outside tests — it is stripped under `-O`.
- **Lazy imports for optional and platform-specific dependencies** — never import all backends unconditionally.
- **Release platform resources** (GDI handles, Quartz event sources, X display, OpenCV writers) in `finally` / `__exit__`; use `with` everywhere it applies.
- **Thread safety** — state shared between the socket server, recording threads, and the callback executor is guarded by `threading.Lock` / `queue.Queue`.
- **Reuse screen captures** when running several searches against the same frame; avoid per-event allocations in mouse/keyboard dispatch.
- **Action lists and loaded config are read-only** once loaded.
- **Pin dependency versions**, including transitive ones that can change return shapes (`opencv-python` is bounded `<6` for exactly this reason). Review new dependencies for known vulnerabilities.
- Common logic belongs in `wrapper/` or `utils/`, never duplicated across platform backends.

### Limits enforced by CI

Cyclomatic complexity ≤ 10 · cognitive complexity ≤ 15 · function ≤ 75 lines · parameters ≤ 7 · nesting ≤ 4 · file ≤ 750 lines · line ≤ 120 chars · no duplicated block ≥ 10 lines.

Docstrings on every public module, class, and function (one-line summary minimum; type hints replace parameter-type prose). Type hints on all public signatures. Import order stdlib → third-party → first-party; no wildcard imports outside the `__init__.py` façade.

### Automated verification

Run before every commit and fix all new findings:

```bash
pip install ruff pylint bandit radon
ruff check je_auto_control/
pylint je_auto_control/
bandit -c pyproject.toml -r je_auto_control/   # uses [tool.bandit] excludes/skips
radon cc je_auto_control/ -a -nc               # flags functions with CC >= C (>10)
```

These tools own the generic rules (bare `except`, mutable defaults, unused names, dead code, `eval`/`exec`, `shell=True`, `pickle` on untrusted data, weak hashes, missing `timeout=`, hardcoded secrets, naming). Fix what they report rather than restating them here.

Suppressions need an inline justification — `# noqa: <code>  # reason: <why>` or `# nosec B404  # reason: <why>`. Blanket file- or module-level suppressions are forbidden.

## Commit Conventions

- Concise messages focused on **why**, not what. Imperative mood: `Add image threshold parameter validation`, `Fix mouse scroll direction on macOS`, `Remove deprecated screen capture fallback`.
- **No AI attribution anywhere.** Not in commit messages, pull request titles or bodies, issue and review comments, release notes, code comments, or documentation. Specifically forbidden: `Co-Authored-By:` lines naming an assistant, "Generated with …" / "Created by …" footers, tool badges, links to assistant products, emoji markers standing in for the same thing, and any statement that code was AI-generated. Everything published under this repo reads as the author's own work.

## Testing

- `test/unit_test/headless/` — headless unit tests, the CI gate. `test/unit_test/flow_control/` — executor flow control.
- `test/integrated_test/` — cross-module workflows. `test/gui_test/` — PySide6 interface. `test/manual_test/` — human verification.
- No `time.sleep` > 1s in unit tests; use fakes or event signals. Tests must not depend on execution order.
- All tests pass before merging; keep cross-platform compatibility.
- **A Qt test that calls `deleteLater()` MUST flush it before the test ends**
  (`QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)`, then
  `processEvents()`). `deleteLater()` is a no-op until an event loop runs, and
  most GUI test modules never run one — so the widget, plus any helper thread
  or timer it started at construction, survives until some *later* test pumps
  events and is destroyed inside that unrelated test. This is not theoretical:
  `test_admin_console_thumbnails_gui.py` leaked seven `AdminConsoleTab`s this
  way, and they detonated inside the nested modal `exec()` of
  `test_usb_acl_prompt.py`, killing the interpreter with rc 3221226505
  (0xC0000409) — a `__fastfail`, so no traceback, no faulthandler output, and
  nothing after it in the suite ran. Note the failure is invisible to CI:
  `test_usb_acl_prompt.py` needs the optional `webrtc` extra (`av`, `aiortc`),
  which CI does not install, so CI skips it and only developers with that
  extra installed see the crash.

## Key Conventions

- Public API is exported from `je_auto_control/__init__.py` and listed in `__all__`.
- JSON action command names use the `AC_` prefix (e.g. `AC_click_mouse`); MCP tools use `ac_`.
- Platform backends are named `{platform}_{function}.py` (e.g. `win32_ctype_mouse_control.py`).
- Virtual key mappings live in `core/utils/*_vk.py` per platform.
