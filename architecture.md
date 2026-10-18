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

Fixed-frame self-healing evaluation is a separate headless flow in `utils/self_healing/`:
bounded manifest/PNG inputs → immutable samples → explicit locator strategies →
quality/latency/provenance report → optional atomic JSON/HTML export. It performs
no capture or input. Python VLM comparisons require an explicit backend; local
manifest commands never choose one. API, AC, MCP and a cancellable GUI worker use
the same evaluator. Live self-healing binds a lazy `cv2_utils/locator_frame.py`
owner around the existing image/VLM seams. The owner captures once in logical
coordinates, retains clipped geometry or a capture failure, and releases pixels
on exit. `runtime_evidence.py` snapshots source/version/frame/strategy metadata
without taking a screenshot. One schema-v2 audit row settles after any requested
click; input dispatch and operation verification remain distinct. Existing result
and call signatures remain compatible, and unbound locator calls stay unbound.

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
| `je_auto_control/gui/` | Optional PySide6 GUI (`[gui]` extra): `main_window.py` (menus, navigation dock, theme), `main_widget.py` (the tabbed workspace), `workspace.py` (scroll containers preserving original page identity, vector close buttons), `workspace_settings.py` (validated per-user QSettings, injectable in tests), the Qt-free `TabRegistry` in `tab_registry.py` (open caches panels; close detaches and schedules owned panels for destruction, retaining metadata and legacy forms), `navigation.py`, `theme.py`, `script_builder/`, `remote_desktop/`, `language_wrapper/`. |
| `autocontrol-lsp/` | Separate distribution: language server for `AC_*` action JSON, plus a `vscode/` client. |
| `test/` | `unit_test/headless/` (CI gate), `unit_test/flow_control/`, `integrated_test/`, `gui_test/`, `manual_test/`, `verify/`. |
| `docs/` | Sphinx docs, `API_LIFECYCLE.md`, `CAPABILITY_MATRIX.md`. |
| `examples/`, `benchmarks/` | Runnable example scripts; latency smoke benchmark. |
| `docker/`, `k8s/helm/`, `ci_templates/` | Container images and backend verification harnesses, Helm chart, GitLab CI template. |
| `browser-extension/`, `AutoControl/`, `exe/`, `autocontrol_driver/` | Manifest v3 companion extension, project-template sample, packaged GUI launcher, driver build script. |
| `scripts/` | Release tooling, not shipped: `dev_release.py` numbers and gates the dev-channel package (§3). |

## 3. Entry points and public interfaces

| Surface | Exact name | Notes |
| --- | --- | --- |
| Python facade | `import je_auto_control` | Broad historical surface (`__all__`). |
| Stable API | `je_auto_control.api` → `api/core.py` | `execute_action`, `execute_action_with_vars`, `generate_code`, `run_diagnostics`, `create_failure_bundle`, `failure_bundle_on_error`, `FailureBundleOptions`. |
| Main CLI | `je_auto_control` → `je_auto_control.cli:main` | Subcommands `run` (`--var`, `--dry-run`), `validate` / `lint`, `fmt`, `list-commands`, `record`, `codegen`, `failure-bundle`, `list-jobs`, `start-server`, `start-rest`, `version`. |
| Legacy CLI | `python -m je_auto_control` (`__main__.py`) | Private `_main()` owns dispatch and error conversion. `-e/--execute_file FILE`, `-d/--execute_dir DIR`, `-c/--create_project PATH`, `--execute_str JSON`. `--execute_str` also accepts a double-encoded JSON string. Any error exits 1 with a log line rather than a traceback, and a `-d` path that is not a directory is an error. |
| MCP server | `je_auto_control_mcp` → `utils/mcp_server/__main__.py:main` | stdio; `start_mcp_stdio_server()`; HTTP transport via the `AC_start_mcp_http_server` command. |
| REST API | `je_auto_control start-rest`, `python -m je_auto_control.utils.rest_api`, `start_rest_api_server()` | Default `127.0.0.1:9939`, bearer token + rate limit. |
| TCP server | `je_auto_control start-server`, `start_autocontrol_socket_server()` | `utils/socket_server/auto_control_socket_server.py`, default `127.0.0.1:9938`, JSON action lists. |
| pytest plugin | `pytest11` entry point `je_auto_control_pytest` (top-level module, imports only pytest; `je_auto_control.utils.pytest_plugin` re-exports it) | Loaded automatically once the package is installed, without importing the package (see coverage rule in §7). |
| LSP | `autocontrol-lsp` → `autocontrol_lsp.server.server:run`; `python -m autocontrol_lsp.server` | Command list is read from the live executor. |
| GUI | `start_autocontrol_gui()` in `gui/__init__.py`; `exe/start_autocontrol_gui.py` | Needs `pip install je_auto_control[gui]`; PySide6 is imported only under `gui/`. |
| Action lint | `python -m je_auto_control.utils.action_lint` | Used by `.github/workflows/action-json-lint.yml`. |
| PyPI packages | `je_auto_control` (stable), `je_auto_control_dev` (dev channel) | Both ship the same `je_auto_control` import package. Stable: a push to `main` runs the `publish` job of `stable.yml`, which bumps `pyproject.toml`, uploads and tags. Dev: the `publish-dev` job of `dev.yml` runs after the headless suite on a push to `dev`, builds from `dev.toml` and uploads when the commit is still the tip of `dev` and the wheel differs from the newest published one; `scripts/dev_release.py` takes the version from PyPI (newest release plus one patch), so nothing is committed back. `dev.toml` declares what `pyproject.toml` declares (`test_dev_toml_parity.py`). Both jobs hold the PyPI token and install nothing but the hash-locked `.github/requirements/publish.txt` (`build`, `twine` and the `setuptools` backend, generated from `publish.in` beside it), then build with `python -m build --no-isolation`, so the backend is the locked one (`test_publish_tooling_lock.py`). |

## 4. Main flows

Executor runs use a `utils/logging/secret_scope.py` mask for vault values resolved
by interpolation. CLI/REST/MCP and scheduled/triggered/hotkey/email owners keep
the mask alive through error handling and persistent diagnostics. A logger
filter sanitizes records before handlers; audit, history and report snapshots
mask text before storage. Joined local parallel/DAG workers share the mask;
independent requests isolate it, and the owner clears it on exit. API outcomes
retain their values; CLI error output is sanitized. Watchdog/observer rules and
callback-executor invocations own their complete diagnostic scope; nested
invocations reuse the enclosing run mask. DAG calls also own a mask; each
node worker binds it through runner execution, error handling and final timing,
including custom local runners. Returned error payloads retain their values.

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
`AutoControlAssertionException` always propagates. Every path that runs an action file from disk (`execute_files`,
the CLI, the scheduler, triggers, hotkeys, webhooks, the MCP run tool, the GUI) loads it with
`read_executable_action_json`, which reads it once and verifies those bytes against the `.sig` sidecar when
`JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS` is set (`utils/action_signing/`).

**B. Remote and external drivers** all feed the single global `executor`:

```
TCP socket_server | REST rest_api | MCP mcp_server | utils/scheduler | utils/triggers | utils/chatops
  → execute_action → same Executor instance → flow A
AC_web_run / AC_web_run_actions → utils/webrunner_bridge/bridge.py
  → je_web_runner.utils.executor.action_executor.execute_one(["WR_*", params])
    (event_dict["WR_*"] on a WebRunner without execute_one); a failure → WebRunnerBridgeError
```

REST gate adaptation preserves check-only custom gates under shared-token auth;
store-backed servers require an authenticated user context even from replacement
gates. Registry status exposes `rbac_enabled` and omits the inactive shared token
so the GUI presents the authentication mode that the server actually accepts.
MCP role decisions also apply explicit sensitive-read overrides independently
of read-only hints; clipboard, local data, credential, external service and
microphone operations require operator authority at both listing and dispatch.

Delayed work captures registration authority through `utils/rbac/deferred.py`.
Schedulers, triggers, hotkeys, watchdogs, webhooks, e-mail watchers and observers
bind that owner at dispatch, independently of the worker's ambient context.
`resolve_token` attaches the source store path to `AuthorizationContext`; dispatch
re-reads that store for current roles and revocations, without retaining bearer
tokens. Trusted local registrations bind no RBAC identity. Observer/watchdog
callbacks also use script jobs' fresh variables and per-run failure deltas,
preserving any earlier failures recorded by the caller.
CLI runs and previews seed a fresh variable scope even without `--var`.
Top-level LLM planner and FSM runs also open a scope; nested invocations reuse
an existing one so their actions and states share run-local values. Explicit
`Executor()` objects retain their own variables; FSM `context` is separate.

Structured action provenance is being built separately in `utils/action_journal/`.
Its storage foundation uses frozen schema-v1 lifecycle snapshots, pre-write
redaction, interprocess append sequencing and fsync. Readers preserve incomplete
steps and ignore bounded uncommitted tails; opaque outcomes/errors are redacted.
Explicit `journal_scope` capture wraps each executor dispatch; loop bodies keep
their step parent and local parallel/DAG workers rebind the same run metadata.
`execute_action_with_journal` opens a fresh variable scope and returns a typed
run summary. Journal types, capture/read helpers and `JournalLink` are exported
from the Qt-free facade. CLI `run --journal` retains the original record/exit
contract; `journal` validates a full file then emits a bounded, sanitized snapshot
selection. Both new CLI paths use the existing allowed-root guard and create no
history row or database implicitly. Capture starts are durable before effects;
failed actions, handled loop signals, cancellation and dry-runs receive distinct
completion statuses.
`AC_journal_capture` uses `action_journal/commands.py` to validate its nested
body and run it on the current executor, retaining variables, strictness and
loop/cancellation signals. The command opens a new capture root and restores any
outer journal. `inspection.py::inspect_journal` shares default-root confinement,
full-file validation and bounded sanitized snapshots across the facade, CLI and
`AC_journal_read`. Both commands have Script Builder forms and require
`drive_input` under RBAC. Linting walks body-bearing ordinary commands as well
as blocks. A plain outer dry-run previews the capture command without opening
a journal; Python/CLI run-level capture can record individual dry-run steps.
`action_journal/run.py` supplies frozen `JournalRunOptions` and the isolated
`execute_journal_run` service; the seven-parameter convenience API delegates to
it. Bindings retain observer/policy tuples through nested roots and local workers.
Policies intersect and are checked before linking and at each append; observers
run before a start and after durable completion, preserving pending failures.
The reader owns a closing generator and invokes count observers outside storage
error translation. MCP journal adapters use these hooks for progress/cancellation
and receive the server's live policy through `ToolCallContext`. This confines
nested journal operations; general nested action argument policies remain pending.
`MCPToolResult` keeps failure metadata outside its JSON dictionary fields. The
server sets `isError` and audit status from this explicit type while preserving
structured payloads; ordinary dictionaries cannot set protocol flags.
`gui/journal_browser.py` embeds read-only snapshot inspection in Run History.
Its worker copies the submission context, refreshes deferred authority before
file I/O and uses the shared inspector. Counts are queued to GUI slots;
request generations reject old results after a target change. Closing the view
or destroying its owner requests cooperative cancellation. The existing daemon
worker relay drops callbacks after owner destruction. Selecting history links
loads metadata only; neither inspection nor link selection creates a history row.
`run_history/manual.py` creates explicitly requested manual owners around an
existing execution. It binds both an ambient journal and captures opened later,
retains caller variables/results, counts only the current counter delta and
keeps normal loop signals distinct from failures. Original signals survive a
failed finish; labels are scrubbed before insertion. The named-body command
adapter stays on the owning executor. CLI opt-in and the shared GUI
`ManualRunControls` wrap existing run paths; only a CLI-owned custom store is
closed by the CLI. Default and journal-only paths open no history database.
`utils/run_history/context.py` binds an existing history row to execution.
Scheduler/trigger/hotkey/webhook/email owners bind their own row; local parallel
and DAG workers carry it explicitly. `journal_scope` attaches an idempotent
non-owning path/run-ID link before dispatch. `run_journals` cascades metadata
when rows are pruned/cleared; external journal files are never deleted by history.
`run_history/run_outcome.py` shares interruption classification and finalization.
Cancellation bypasses ordinary executor recovery/retry and callback guards;
parallel/DAG workers preserve the original signal. History settles interrupted
attempts as `error`, without a snapshot; a failed completion preserves a pending
hard signal and leaves the history row unfinished. Explicit script `finally`
branches retain their cleanup contract. Already-started parallel branches are
joined before propagation; this is not forcible interruption of native I/O.
Facade/command/CLI/MCP/GUI and manual-run history controls remain pending.

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
5. Optional MCP tool: factory in `utils/mcp_server/tools/_factories.py`, adapter in the themed handler module —
   `_handlers_input.py`, `_handlers_screen.py`, `_handlers_system.py`, `_handlers_runs.py`,
   `_handlers_scheduling.py`, `_handlers_remote.py`, `_handlers_locators.py`, `_handlers_operations.py`,
   `_handlers_qa.py`, `_handlers_executor_bridge.py` (a three-line delegation to an executor function), or
   `_handlers.py` for data, text and the WebRunner bridge.
6. GUI: thin widget in `gui/`, registered by one `TabSpec` row in `gui/tab_registry.py` (module and class name, so
   it is imported only when opened) with commands exposed through `menu_actions()`; strings in every
   `gui/language_wrapper/*.py` catalogue.
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
| Jeffrey_RPA | Editable install of **this working tree**: uncommitted changes here reach it immediately. Single facade `JeffreyRPA/_gui_control.py`. | Top-level names (e.g. `click_mouse`, `hotkey`, `write`, `screen_size`, `get_pixel`, `post_click_to_window`) and internal paths `je_auto_control.wrapper.auto_control_window`, `je_auto_control.wrapper.auto_control_keyboard.WRITE_CONTROL_KEYS`, `je_auto_control.utils.monitor_layout` (`logical_virtual_rect`, `enumerate_monitors`), and `wrapper.platform_wrapper.keyboard_keys_table` / `mouse_keys_table` — it validates every key name a user types against the keyboard table and reverse-looks-up recorded virtual keys through it, so a name removed there becomes a rejected hotkey over in that repo. Added so it can drop its own copies: the Tesseract setup helpers `find_tesseract_cmd`, `set_tessdata_dir`, `ocr_languages` (`None` when the engine cannot be asked, `[]` when it has no language data) and `ocr_status`; `click_mouse(clicks=, interval=)` for a double-click in one call; `tween_drag` / `drag_path` pacing (`step_delay_s`, `settle_s`); `keyboard_key_name` and `wrapper.platform_wrapper.keyboard_key_aliases` for reverse lookups that never answer with an alias, plus the Windows table's OEM keys, `browser_home`, lower-case `launch_app2` and its aliases (`ctrl`, `esc`, `enter`, `win`, `pgup`, `numpad0`, ...), which match the names and codes of its own `KEY_ALIASES` / `_EXTRA_KEY_CODES`. |
| PyBreeze | Subprocess `python -m je_auto_control --execute_str <json>` / `--execute_file <path>`; on Windows the JSON string arrives double-encoded. | Legacy CLI flags; also embeds `je_auto_control.gui.main_widget.AutoControlGUIWidget` and calls `record` / `stop_record` in-process. |
| TestPioneer | Optional extra `gui = ["je_auto_control"]`; `parallel_run` starts `python -m je_auto_control --execute_file <path>`. It sets `TEST_PIONEER_ARTIFACT_DIR` for the runner. | `execute_action`, `execute_files`, `RecordingThread`; the `--execute_file` flag. | The flag's exit status, 1 when an action failed (`recorded_failures()` in `__main__.py`); the `<name>_success.json` / `<name>_failure.json` pair, written below the artifact directory for a relative name (`utils/generate_report/report_path.py`).
| WebRunner | Optional extra `autocontrol = ["je_auto_control>=0.0.224"]`; `je_web_runner/utils/autocontrol_bridge/` (`WR_ac_*`) imports this package only when one of those commands runs. | `je_auto_control.utils.executor.action_executor.executor`: `execute_action(actions, raise_on_error=True)`, whose record values it reads in action order, and `known_commands()`; its native commands send `AC_write` (`write_string`), `AC_write_secret` (`secret`, from `WR_ac_basic_auth`), `AC_type_keyboard` (`keycode`), `AC_get_keyboard_keys_table` (the `enter` or `return` key), `AC_locate_image_center` (`image`, `detect_threshold`) and `AC_click_mouse` (`mouse_keycode`, `x`, `y` in this DPI-aware process's coordinates). It refuses `AC_shell_command`, `AC_execute_process`, `AC_add_package_*`, `AC_execute_action`, `AC_execute_files`, `AC_run_agent` and `AC_web_*` by name, so renaming one of them would let it through WebRunner's bridge. |

**Guarded by** `test/unit_test/headless/test_cross_project_contracts.py`: every legacy CLI flag (short and long, run as a
real child process, including PyBreeze's double-encoded `--execute_str`), the facade names in the rows above
(Jeffrey_RPA's list is every `ac.<name>` in `_gui_control.py`, plus the names and keyword parameters added so it
can drop its own copies), the `auto_control_window` functions Jeffrey_RPA calls,
its three internal imports, the two key tables (shape everywhere, Windows key names on Windows),
`AutoControlGUIWidget`, and the executor API and refused command names WebRunner's bridge relies on. The test only knows what this table knows: when a consumer starts relying on something
new, add it to both.

**Outbound (optional):** `utils/webrunner_bridge/bridge.py` imports WebRunner's supported module
`je_web_runner.utils.executor.action_executor` lazily, for `AC_web_*` commands and `gui/webrunner_tab.py`: `executor`
(its `event_dict` lists and checks the `WR_*` names) and `execute_one`, which runs each command through WebRunner's
gates, retries and failure screenshots; a WebRunner without `execute_one` gets the `event_dict` callable directly.
The helpers send `WR_get_webdriver_manager`, `WR_to_url`, `WR_quit`, `WR_save_screenshot`, `WR_get_current_url`;
WebRunner's `test_public_api.py` guards those names and `execute_one`, and `test_webrunner_contract.py` here checks
them against the installed package. `je_web_runner` is not a declared dependency: `is_webrunner_available` looks it
up with `importlib.util.find_spec`, because importing it writes `WEBRunner.log` into the cwd, and a missing package
raises `WebRunnerBridgeError`. Any error from a `WR_*` command is re-raised as `WebRunnerBridgeError` (an
`AutoControlException`), so the executor records it instead of aborting the script.

**Wire contract between AutoControl versions:** the Admin Console and DAG remote nodes drive other hosts through
REST `POST /execute` (`{"actions": [...], "raise_on_error": bool}`), and those hosts may run an older release.
A new body field must be optional and safe to ignore — an old host drops `raise_on_error` and answers the pre-flag
`{"result": ...}`, which the client still reads as `ok: true`.

**Import-time contracts**

- `import je_auto_control` must not load PySide6; the GUI window is imported only inside `start_autocontrol_gui()`.
  `test/unit_test/headless/test_facade_import_is_light.py` also keeps `cv2`, `numpy`, `PIL`, `cryptography`,
  `je_open_cv` and `mss` off the import path.
- `utils/logging/logging_instance.py` attaches a file handler at import and sets the level of its own logger only
  (never the root logger — that would push every third-party library's DEBUG records into the host's handlers). The
  handler opens its file on the first record, and nothing logs during the import: importing writes no file at all.
  The file is `$JE_AUTOCONTROL_LOG_FILE` as read when the file is opened (so a `conftest.py` can still set it after
  the `pytest11` plugin imported the package; a relative path resolves against the cwd then), else
  `~/.je_auto_control/logs/AutoControlGUI.log`, shared by every process: appended to, rotated to `.1` past 10 MB
  only when a process opens it, and swapped for `os.devnull` with one `RuntimeWarning` when it cannot be opened.
  Consumers that must keep the log out of a shared file (a test suite) set the variable before importing;
  changing the working directory no longer redirects it.
- No module reads the home directory at import; every `~/.je_auto_control/` path is resolved when used, so a
  consumer can redirect `HOME` / `USERPROFILE` after the import (this repo's `test/conftest.py` gives each test run
  a temporary home). `test/unit_test/headless/test_state_paths_follow_home.py` scans the package for violations.

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
- `AC_add_package_to_executor` / `AC_add_package_to_callback_executor` pass the package gate in
  `utils/package_manager/package_manager_class.py` before importing: `executor.allow_packages(...)` and
  `executor.set_allow_arbitrary_packages(...)` are Python-only switches, never `AC_*` commands, so an action list
  cannot open its own gate. Unconfigured, any package loads with a `DeprecationWarning` (workspace X-12).
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
