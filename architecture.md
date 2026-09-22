# AutoControl Architecture

> Short overview for people and agents. Per-module detail lives in [`architecture_explore.md`](architecture_explore.md).
> Last verified: 2026-09-22 against `0e8e25b` on `feat/coverage-to-80`.

## 1. Purpose

AutoControl (`je_auto_control`) is a cross-platform GUI automation framework: mouse and keyboard control,
screen capture, image recognition, OCR, accessibility-tree lookup, action scripting and report generation
behind one headless Python API. Every feature is also reachable from JSON action files (`AC_*` commands),
a CLI, TCP / REST / MCP servers, a pytest plugin and an optional PySide6 GUI. Backends cover Windows,
macOS, Linux X11, Linux Wayland, Android and iOS.

## 2. Layers and directories

Each layer calls only the one below it:
entry points → execution core (`utils/executor/`) → headless capabilities (`utils/`) → `wrapper/` → one OS backend.

| Path | Responsibility |
| --- | --- |
| `je_auto_control/__init__.py` | Facade: re-exports the public API and lists it in `__all__`. Must import without PySide6. |
| `je_auto_control/api/` | Small versioned headless facade (`core.py`); the supported entry for new integrations per `docs/API_LIFECYCLE.md`. |
| `je_auto_control/cli.py`, `__main__.py` | Main CLI and the legacy argparse entry point. |
| `je_auto_control/utils/executor/` | Execution core: `Executor.event_dict` (`AC_*` name → callable) in `action_executor.py`, block commands in `flow_control.py`, validation in `action_schema.py`. |
| `je_auto_control/utils/` | Headless capability layer, one subpackage per feature, zero Qt imports. Grouped by theme in `architecture_explore.md` §5.4. |
| `je_auto_control/utils/{socket_server,rest_api,mcp_server,pytest_plugin}/` | Server and integration surfaces (§3). |
| `je_auto_control/utils/{remote_desktop,usb,usbip}/` | Remote desktop (TCP / WebSocket / WebRTC) and USB passthrough. |
| `je_auto_control/utils/webrunner_bridge/` | Optional bridge that runs WebRunner `WR_*` commands (§6). |
| `je_auto_control/wrapper/` | Platform-neutral API (`auto_control_mouse/keyboard/screen/image/record/window.py`); `platform_wrapper.py` picks the backend; `backend_contract.py` types the seam; `window_backends/`. |
| `je_auto_control/{windows,osx,linux_with_x11,linux_wayland}/` | Desktop OS backends; only the running OS's backend is imported. |
| `je_auto_control/{android,ios}/` | Mobile device control (adb / uiautomator2, WebDriverAgent). |
| `je_auto_control/gui/` | Optional PySide6 GUI (`[gui]` extra): `main_window.py`, tab registry `main_widget.py`, `script_builder/`, `remote_desktop/`, `language_wrapper/`. |
| `autocontrol-lsp/` | Separate distribution: language server for `AC_*` action JSON, plus a `vscode/` client. |
| `test/` | `unit_test/headless/` (CI gate), `unit_test/flow_control/`, `integrated_test/`, `gui_test/`, `manual_test/`, `verify/`. |
| `docs/` | Sphinx docs, `API_LIFECYCLE.md`, `CAPABILITY_MATRIX.md`. |
| `examples/`, `benchmarks/` | Runnable example scripts; latency smoke benchmark. |
| `docker/`, `k8s/helm/`, `ci_templates/` | Container images and backend verification harnesses, Helm chart, GitLab CI template. |
| `browser-extension/`, `AutoControl/`, `exe/`, `autocontrol_driver/` | Manifest v3 companion extension, project-template sample, packaged GUI launcher, driver build script. |

## 3. Entry points and public interfaces

| Surface | Exact name | Notes |
| --- | --- | --- |
| Python facade | `import je_auto_control` | Broad historical surface (`__all__`). |
| Stable API | `je_auto_control.api` → `api/core.py` | `execute_action`, `execute_action_with_vars`, `generate_code`, `run_diagnostics`, `create_failure_bundle`, `failure_bundle_on_error`, `FailureBundleOptions`. |
| Main CLI | `je_auto_control` → `je_auto_control.cli:main` | Subcommands `run` (`--var`, `--dry-run`), `validate` / `lint`, `fmt`, `list-commands`, `record`, `codegen`, `failure-bundle`, `list-jobs`, `start-server`, `start-rest`, `version`. |
| Legacy CLI | `python -m je_auto_control` (`__main__.py`) | `-e/--execute_file FILE`, `-d/--execute_dir DIR`, `-c/--create_project PATH`, `--execute_str JSON`. `--execute_str` also accepts a double-encoded JSON string. |
| MCP server | `je_auto_control_mcp` → `utils/mcp_server/__main__.py:main` | stdio; `start_mcp_stdio_server()`; HTTP transport via the `AC_start_mcp_http_server` command. |
| REST API | `je_auto_control start-rest`, `python -m je_auto_control.utils.rest_api`, `start_rest_api_server()` | Default `127.0.0.1:9939`, bearer token + rate limit. |
| TCP server | `je_auto_control start-server`, `start_autocontrol_socket_server()` | `utils/socket_server/auto_control_socket_server.py`, default `127.0.0.1:9938`, JSON action lists. |
| pytest plugin | `pytest11` entry point `je_auto_control.utils.pytest_plugin.plugin` | Loaded automatically once the package is installed (see coverage rule in §7). |
| LSP | `autocontrol-lsp` → `autocontrol_lsp.server.server:run`; `python -m autocontrol_lsp.server` | Command list is read from the live executor. |
| GUI | `start_autocontrol_gui()` in `gui/__init__.py`; `exe/start_autocontrol_gui.py` | Needs `pip install je_auto_control[gui]`; PySide6 is imported only under `gui/`. |
| Action lint | `python -m je_auto_control.utils.action_lint` | Used by `.github/workflows/action-json-lint.yml`. |

## 4. Main flows

**A. JSON action script (primary path)**

```
action.json → utils/json/json_file.read_action_json
  → Executor.execute_action                       (utils/executor/action_executor.py)
      → action_schema.validate_actions            (unknown AC_* names rejected before anything runs)
      → _execute_event → flow_control.BLOCK_COMMANDS  (AC_loop / AC_if_* / AC_try / AC_retry …)
                       | event_dict[name](**args)     (${var} / ${secrets.*} interpolated via utils/script_vars)
  → wrapper/auto_control_*.py → wrapper/platform_wrapper.py → windows/ | osx/ | linux_with_x11/ | linux_wayland/
  → record dict {"execute: [...]": result or repr(error)}
```

Errors of the `AutoControlException` family are recorded, not raised (unless `raise_on_error=True`);
`AutoControlAssertionException` always propagates. `execute_files` first calls `require_signed_actions`
(`utils/action_signing/`).

**B. Remote and external drivers** all feed the single global `executor`:

```
TCP socket_server | REST rest_api | MCP mcp_server | utils/scheduler | utils/triggers | utils/chatops
  → execute_action → same Executor instance → flow A
AC_web_run / AC_web_run_actions → utils/webrunner_bridge/bridge.py
  → je_web_runner.utils.executor.action_executor.executor.event_dict["WR_*"]
```

**C. Record → edit → generate code**

```
wrapper/auto_control_record.record → OS listener (e.g. windows/record/win32_input_hook.py)
  → stop_record / record_to_json → action list
  → utils/recording_edit (trim / filter / rescale) | utils/semantic_recording (anchors for cross-machine replay)
  → utils/codegen (pytest / python / robot)
```

## 5. Extension points

**New feature or `AC_*` command**, in this order (CLAUDE.md › Feature Delivery Rules):

1. Headless implementation in `je_auto_control/utils/<feature>/` (or `wrapper/`); no PySide6; optional deps imported lazily.
2. Re-export public names in `je_auto_control/__init__.py` and its `__all__`.
3. Register the `AC_*` name in `Executor.event_dict` (`utils/executor/action_executor.py`); commands with nested
   action bodies go in `BLOCK_COMMANDS` (`utils/executor/flow_control.py`).
4. Describe its parameters in `gui/script_builder/command_schema.py` (Script Builder form).
5. Optional MCP tool: factory in `utils/mcp_server/tools/_factories.py`, adapter in `utils/mcp_server/tools/_handlers.py` (QA-theme adapters — assertions, suites, reports — in `_handlers_qa.py`).
6. GUI: thin widget in `gui/`, registered in `gui/main_widget.py` (`_add_tab`) with commands exposed through
   `menu_actions()`; strings in every `gui/language_wrapper/*.py` catalogue.
7. Headless test in `test/unit_test/headless/`.
8. Update `architecture_explore.md` (and `README.md` + `README/` translations if a quoted count changes), then run
   `python test/unit_test/headless/test_doc_line_counts.py --fix`. Regenerate the typed stub with
   `python -m je_auto_control.utils.stubs.generator je_auto_control/actions.pyi`.

**Other seams**

- Runtime commands without touching core: `add_command_to_executor({"AC_x": fn})`, `utils/plugin_loader/`
  (directory scan) or `utils/plugin_sdk/` (package entry points).
- New OS backend: package `je_auto_control/<platform>/` + assembly module `wrapper/_platform_<name>.py` satisfying
  `wrapper/backend_contract.py` + one branch in `wrapper/platform_wrapper.py`; window management in `wrapper/window_backends/`.
- New accessibility / OCR / vision / llm / agent / hotkey backend: implement the base class in that subpackage's
  `backends/` directory; a null fallback keeps imports dependency-free.
- New report format: add a generator beside `utils/generate_report/generate_{html,json,xml}_report.py`.

## 6. Cross-project boundaries

| Consumer | How it uses this repo | What it relies on |
| --- | --- | --- |
| Jeffrey_RPA | Editable install of **this working tree**: uncommitted changes here reach it immediately. Single facade `JeffreyRPA/_gui_control.py`. | Top-level names (e.g. `click_mouse`, `hotkey`, `write`, `screen_size`, `get_pixel`, `post_click_to_window`) and internal paths `je_auto_control.wrapper.auto_control_window`, `je_auto_control.wrapper.auto_control_keyboard.WRITE_CONTROL_KEYS`, `je_auto_control.utils.monitor_layout` (`logical_virtual_rect`, `enumerate_monitors`). |
| PyBreeze | Subprocess `python -m je_auto_control --execute_str <json>` / `--execute_file <path>`; on Windows the JSON string arrives double-encoded. | Legacy CLI flags; also embeds `je_auto_control.gui.main_widget.AutoControlGUIWidget` and calls `record` / `stop_record` in-process. |
| TestPioneer | Optional extra `gui = ["je_auto_control"]`; `parallel_run` starts `python -m je_auto_control --execute_file <path>`. | `execute_action`, `execute_files`, `RecordingThread`; the `--execute_file` flag. |

**Guarded by** `test/unit_test/headless/test_cross_project_contracts.py`: every legacy CLI flag (short and long, run as a
real child process, including PyBreeze's double-encoded `--execute_str`), the facade names in the three rows above
(Jeffrey_RPA's list is every `ac.<name>` in `_gui_control.py`), the `auto_control_window` functions Jeffrey_RPA calls,
its three internal imports, and `AutoControlGUIWidget`. The test only knows what this table knows: when a consumer
starts relying on something new, add it to both.

**Outbound (optional):** `utils/webrunner_bridge/bridge.py` imports WebRunner's *internal*
`je_web_runner.utils.executor.action_executor.executor` lazily, for `AC_web_*` commands and `gui/webrunner_tab.py`.
`je_web_runner` is not a declared dependency; when it is missing the bridge raises `WebRunnerBridgeError`.
Moving that WebRunner module breaks the bridge.

**Import-time contracts**

- `import je_auto_control` must not load PySide6; the GUI window is imported only inside `start_autocontrol_gui()`.
  `test/unit_test/headless/test_facade_import_is_light.py` also keeps `cv2`, `numpy`, `PIL`, `cryptography`,
  `je_open_cv` and `mss` off the import path.
- `utils/logging/logging_instance.py` sets the root logger to DEBUG and attaches a file handler at import, but the
  handler opens its file on the first record, and nothing logs during the import: importing writes no file at all.
  The file is `$JE_AUTOCONTROL_LOG_FILE` as read when the file is opened (so a `conftest.py` can still set it after
  the `pytest11` plugin imported the package; a relative path resolves against the cwd then), else
  `~/.je_auto_control/logs/AutoControlGUI.log`, shared by every process: appended to, rotated to `.1` past 10 MB
  only when a process opens it, and swapped for `os.devnull` with one `RuntimeWarning` when it cannot be opened.
  Consumers that must keep the log out of a shared file (a test suite) set the variable before importing;
  changing the working directory no longer redirects it.

**De-facto public:** `docs/API_LIFECYCLE.md` calls `je_auto_control.utils.*` internal, but the internal paths in the
table above are used by sibling repos; treat renaming or removing them as a breaking change and check the consumers
first. `AC_*` command names and the legacy CLI flags are public too (action files live outside this repo).

## 7. Design constraints

- Every feature ships a headless API, a facade export, an `AC_*` command and a thin GUI tab whose commands live in the
  Actions menu (enforced by `test_actions_menu_gui.py`). → CLAUDE.md › Feature Delivery Rules › Every feature ships both a headless API and a GUI surface
- The top-level package stays Qt-free. → same section
- `architecture_explore.md` changes in the same commit as the code; counts are measured, never estimated;
  `test_doc_counts.py` and `test_doc_line_counts.py` fail CI on drift. → CLAUDE.md › Feature Delivery Rules › `architecture_explore.md` is updated with every change
- Agreed-but-unfinished work is recorded in `Progress.md` (open items only). → CLAUDE.md › Feature Delivery Rules › Outstanding work goes in `Progress.md`
- Flat exception hierarchy: every framework error derives from `AutoControlException`; assertion failures keep
  propagating. → CLAUDE.md › Coding Standards › Project-specific rules
- Validate at boundaries and reject unknown command names; servers bind `127.0.0.1` unless explicitly opted in. → same
- No `print()` or runtime `assert` in library code; lazy imports for optional and platform deps; release platform
  resources in `finally` / `with`; guard shared state with locks or queues; pin dependency versions. → same
- Size limits (cyclomatic ≤ 10, cognitive ≤ 15, function ≤ 75 lines, file ≤ 750 lines, line ≤ 120) are a review
  standard; grandfathered over-limit files are listed in `Progress.md`. → CLAUDE.md › Coding Standards › Size and complexity limits
- Run ruff, pylint, bandit and radon before committing; every suppression carries an inline reason. → CLAUDE.md › Coding Standards › Automated verification
- Measure coverage with `python -m coverage run -m pytest`, never `pytest --cov` (the pytest11 plugin imports the
  facade first), with the `[webrtc]` extra installed; never loosen `python_files = ["test_*.py"]`. → CLAUDE.md › Development Commands
- Tests cover the headless path, avoid sleeps over 1 s, are order-independent, and keep the Qt `deleteLater()`
  flush fixture in `test/unit_test/headless/conftest.py`. → CLAUDE.md › Testing
- Commit messages are imperative and explain why; attribution rules apply. → CLAUDE.md › Commit Conventions

## 8. When to update this file

- A top-level package or directory in §2 is added, removed or renamed, or an OS backend is added or dropped.
- An entry point changes: console script, `python -m` module, server surface, pytest or LSP plugin, legacy CLI flag.
- The executor contract changes (action shape, validation, error containment, signing) or the layer order in §2.
- A new extension mechanism appears or the ordered steps in §5 change.
- A sibling repo starts or stops depending on this one, starts using another internal path, the WebRunner bridge
  target moves, or the log file name or location changes.
- A hard rule in CLAUDE.md is added or changed.
- On every edit, refresh the "Last verified" line. Module-level changes belong in `architecture_explore.md`, not here.
