# AutoControl Architecture

> Short overview for people and agents. Per-module detail lives in [`architecture_explore.md`](architecture_explore.md).
> Last verified: 2026-10-03 on `feat/platform-gui-modernization`.

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
| `je_auto_control/api/` | Versioned headless facade (`core.py`) and Beta structured journals (`journal.py`); the supported entry for new integrations per `docs/API_LIFECYCLE.md`. |
| `wrapper/device_context.py` | Lazy mobile sessions with frozen identities, owned backend adapters, cancellation and passive metadata; Beta `api/mobile.py` mirrors the public models/services. |
| `je_auto_control/cli.py`, `__main__.py` | Main CLI and legacy argparse entry point; both exit 1 for recorded action failures. |
| `je_auto_control/utils/executor/` | Execution core with ContextVar public-run scopes and copied parallel/DAG variables: `Executor.event_dict` (`AC_*` name → callable) in `action_executor.py`, block commands in `flow_control.py`, validation in `action_schema.py`. |
| `je_auto_control/utils/` | Headless capability layer, one subpackage per feature, zero Qt imports. Grouped by theme in `architecture_explore.md` §5.4. |
| `je_auto_control/utils/{socket_server,rest_api,mcp_server,pytest_plugin}/` | Server and integration surfaces (§3). |
| `je_auto_control/utils/{remote_desktop,usb,usbip}/` | Remote desktop (TCP / WebSocket / WebRTC) and USB passthrough with request-ID correlation and safe legacy-timeout reconnect. |
| `je_auto_control/utils/webrunner_bridge/` | Optional bridge that runs WebRunner `WR_*` commands (§6). |
| `je_auto_control/wrapper/` | Platform-neutral API (`auto_control_mouse/keyboard/screen/image/record/window.py`); `platform_wrapper.py` picks the backend; `backend_contract.py` types the seam; `window_backends/`. |
| `je_auto_control/{windows,osx,linux_with_x11,linux_wayland}/` | Desktop OS backends; only the running OS's backend is imported. |
| `je_auto_control/{android,ios}/` | Mobile device control (adb / uiautomator2, WebDriverAgent). |
| `je_auto_control/gui/` | Optional PySide6 GUI (`[gui]` extra): `main_window.py`, lazy registry `tab_registry.py`, compatible `main_widget.py`, `script_builder/`, `remote_desktop/`, `language_wrapper/`. |
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
| Legacy CLI | `python -m je_auto_control` (`__main__.py`) | `-e/--execute_file FILE`, `-d/--execute_dir DIR`, `-c/--create_project PATH`, `--execute_str JSON`. `--execute_str` also accepts a double-encoded JSON string. Any error exits 1 with a log line rather than a traceback, and a `-d` path that is not a directory is an error. |
| MCP server | `je_auto_control_mcp` → `utils/mcp_server/__main__.py:main` | stdio; `start_mcp_stdio_server()`; HTTP transport via the `AC_start_mcp_http_server` command. |
| REST API | `je_auto_control start-rest`, `python -m je_auto_control.utils.rest_api`, `start_rest_api_server()` | Default `127.0.0.1:9939`, bearer token + rate limit. |
| TCP server | `je_auto_control start-server`, `start_autocontrol_socket_server()` | `utils/socket_server/auto_control_socket_server.py`, default `127.0.0.1:9938`, JSON action lists. |
| pytest plugin | `pytest11` entry point `je_auto_control_pytest` (standalone module) | Loaded automatically once the package is installed (see coverage rule in §7). |
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
`AutoControlAssertionException` always propagates. Every path that runs an action file from disk (`execute_files`,
the CLI, the scheduler, triggers, hotkeys, webhooks, the MCP run tool, the GUI) loads it with
`read_executable_action_json`, which reads it once and verifies those bytes against the `.sig` sidecar when
`JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS` is set (`utils/action_signing/`).

**B. Remote and external drivers** bind request scopes before executor dispatch:

```
TCP socket_server | REST rest_api | MCP mcp_server | utils/scheduler | utils/triggers | utils/chatops
  → execution_scope → execute_action → isolated script state → flow A
AC_web_run / AC_web_run_actions → utils/webrunner_bridge/bridge.py
  → je_web_runner.utils.executor.action_executor.execute_one(["WR_*", params])
    (event_dict["WR_*"] on a WebRunner without execute_one); a failure → WebRunnerBridgeError
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
5. Optional MCP tool: factory in `utils/mcp_server/tools/_factories.py`, adapter in the themed handler module —
   `_handlers_input.py`, `_handlers_screen.py`, `_handlers_system.py`, `_handlers_runs.py`,
   `_handlers_scheduling.py`, `_handlers_remote.py`, `_handlers_locators.py`, `_handlers_operations.py`,
   `_handlers_qa.py`, `_handlers_executor_bridge.py` (a three-line delegation to an executor function), or
   `_handlers.py` for data, text and the WebRunner bridge.
6. GUI: thin widget in `gui/`, registered in `gui/_tab_catalog.py` with a lazy factory/action metadata with commands exposed through
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
| Jeffrey_RPA | Editable install of **this working tree**: uncommitted changes here reach it immediately. Single facade `JeffreyRPA/_gui_control.py`. | Top-level names (e.g. `click_mouse`, `hotkey`, `write`, `screen_size`, `get_pixel`, `post_click_to_window`) and internal paths `je_auto_control.wrapper.auto_control_window`, `je_auto_control.wrapper.auto_control_keyboard.WRITE_CONTROL_KEYS`, `je_auto_control.utils.monitor_layout` (`logical_virtual_rect`, `enumerate_monitors`), and `wrapper.platform_wrapper.keyboard_keys_table` / `mouse_keys_table` — it validates every key name a user types against the keyboard table and reverse-looks-up recorded virtual keys through it, so a name removed there becomes a rejected hotkey over in that repo. |
| PyBreeze | Subprocess `python -m je_auto_control --execute_str <json>` / `--execute_file <path>`; on Windows the JSON string arrives double-encoded. | Legacy CLI flags; also embeds `je_auto_control.gui.main_widget.AutoControlGUIWidget` and calls `record` / `stop_record` in-process. |
| TestPioneer | Optional extra `gui = ["je_auto_control"]`; `parallel_run` starts `python -m je_auto_control --execute_file <path>`. | `execute_action`, `execute_files`, `RecordingThread`; the `--execute_file` flag. |
| WebRunner | Optional extra `autocontrol = ["je_auto_control>=0.0.224"]`; `je_web_runner/utils/autocontrol_bridge/` (`WR_ac_*`) imports this package only when one of those commands runs. | `je_auto_control.utils.executor.action_executor.executor`: `execute_action(actions, raise_on_error=True)`, whose record values it reads in action order, and `known_commands()`; its native commands send `AC_write` (`write_string`), `AC_write_secret` (`secret`, used by `WR_ac_basic_auth`; returns None and keeps credentials out of logs/records), `AC_type_keyboard` (`keycode`), `AC_get_keyboard_keys_table` (the `enter` or `return` key), `AC_locate_image_center` (`image`, `detect_threshold`) and `AC_click_mouse` (`mouse_keycode`, `x`, `y` in this DPI-aware process's coordinates). It refuses `AC_shell_command`, `AC_execute_process`, `AC_add_package_*`, `AC_execute_action`, `AC_execute_files`, `AC_run_agent` and `AC_web_*` by name, so renaming one of them would let it through WebRunner's bridge. |

**Guarded by** `test/unit_test/headless/test_cross_project_contracts.py`: every legacy CLI flag (short and long, run as a
real child process, including PyBreeze's double-encoded `--execute_str`), the facade names in the rows above
(Jeffrey_RPA's list is every `ac.<name>` in `_gui_control.py`), the `auto_control_window` functions Jeffrey_RPA calls,
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
  an integration imported the package; a relative path resolves against the cwd then), else
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
- No `print()` or runtime `assert` in library code; lazy imports for optional and platform deps; release platform
  resources in `finally` / `with`; guard shared state with locks or queues; pin dependency versions. → same
- Size limits (cyclomatic ≤ 10, cognitive ≤ 15, function ≤ 75 lines, file ≤ 750 lines, line ≤ 120) are a review
  standard; grandfathered over-limit files are listed in `Progress.md`. → CLAUDE.md › Coding Standards › Size and complexity limits
- Run ruff, pylint, bandit and radon before committing; every suppression carries an inline reason. → CLAUDE.md › Coding Standards › Automated verification
- Measure coverage with `python -m coverage run -m pytest`, never `pytest --cov` (coverage starts before
  all plugins, including explicit legacy integrations), with the `[webrtc]` extra installed; never loosen `python_files = ["test_*.py"]`. → CLAUDE.md › Development Commands
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

Screen-coordinate contract: regions and locating results use global input coordinates.
Fresh Windows processes prefer per-monitor v2; Qt scales inside each display.
macOS captures normalize each display to points before stitching. Set-of-Marks
draws relative to the capture origin while keeping global points in its legend.

Anthropic Agent requests append history up to three screenshots, then start
a separate goal/action-summary conversation with the latest image. Completed
toolset batches are summarized after all results are collected; submitted
request snapshots remain immutable. OpenAI and default tool exports are unchanged.

REST/MCP HTTP optionally resolve `JE_AUTOCONTROL_USERS` through the process-wide
`configured_user_store()` cache. Bearer authentication binds an immutable
`AuthorizationContext`; route/tool capability checks and nested executor guards
share it. MCP workers copy the context, discovery uses the same policy as calls,
and HTTP sessions require their authenticated owner. Absent configuration retains
shared-token behavior; configured empty/unreadable stores never fall back.
REST hash-chain records expose `user_id` using their existing actor column, and
MCP JSONL entries include `user_id`. Local Admin Console user actions use the same
store instance; the headless facade, five AC commands, MCP tools and Script Builder
provide equivalent management surfaces.

Window lifecycle: focus verifies foreground ownership; waits bound each sleep.
Windows capture reads visible bounds without mutation, while saved layouts use
native placement/show state and arrangement uses the primary work area. Legacy
geometry snapshots and public command/import names remain compatible.

Image/OCR: template paths decode file bytes; grayscale sources remain 2-D and
cv2 failures become ImageNotFoundException. Regions intersect the desktop before
cropping, returning the actual origin to match/OCR callers; negative centres use
integer floor division. The Jeffrey_RPA OEM test migration is delivered as a
portable patch without changing its live editable source.

The remote boundary uses a server-owned RBAC capability catalog. Executor
dispatch binds positional/default arguments and validates declared file fields
after interpolation, including flow blocks and loaded scripts. RequestBinding
retains registration identity, roots and variable snapshots for deferred work;
thread workers inherit authorization/path contexts and fork execution variables.
Color/HSV and VLM coordinates share capture's actual clipped origin.

Structured journal flow: facade/API, AC/MCP and Run History → scoped executor
→ append-only action_journal JSONL → validated run/event adapters. ContextVars
retain run/parent/source identity through nested and parallel calls; run-history
artifact links refer to the journal. Opt-in environment capture uses the same
boundary. Inputs are sanitized before persistence, outcomes stay separate,
and absent terminal records remain incomplete. Schema version 1 is Beta.
Thin `wire_api` adapters delegate AC/MCP recording to the full journal/history
orchestrator. Sensitive getter outputs and signature-bound positional credentials
are masked before append; unhandled recorded failures propagate to containers.

Self-healing evaluation: `api.healing` -> JSON adapters -> immutable dataset
samples -> frame strategies -> labelled comparison. Strategies receive identical
bytes; reports retain geometry/frame identity and explicit metric populations.
`report_views` provides read-only HTML/GUI metric and failure rows. GUI work runs
through RequestBinding and CallWorker. Revision store snapshots base/candidate
images, persists labelled validation and checks content identities under locks
before accept/revert. Runtime capture observers record consumed bytes only
within an attempt-scoped ContextVar; no additional screenshot is taken for logging.

Journal candidates: capture bytes once -> shared journal schema/order parser ->
observed leaf selection with parent/retry provenance -> installed registry and
argument/dry-run validation -> existing code generator -> Python AST validation
-> CandidateScript (code/actions/manifest/warnings). Export pre-checks all derived
paths and preserves the input journal. Shared headless diff logic masks current
editor literals. Recording Editor and Script Builder use one scoped worker panel
for readonly preview and separate explicit import/export; neither dispatches
candidate actions. Raw outcomes never become replay arguments.
Ordinary runtime references without resolved binding evidence are omitted with
warnings; block object shapes and required keys are validated without dispatch.

Config storage: `utils/config_sync/store.py` atomically checks server revisions, writes buckets and records operation receipts in SQLite. `remote_desktop/signaling_server.py` exposes protected version-2 HTTP envelopes and explicit legacy compatibility; app lifespan closes the connection. The Beta `api/config_sync.py` and historical facade expose the same typed storage API without Qt or database creation at import.

Config synchronization: models.py retains compatible bucket/error aliases, database.py owns shared lazy SQLite lifecycle, versions.py compares causal entries, causal_bucket.py preserves conflict alternatives and the shared device registry, outbox.py persists scoped envelopes/peer acknowledgements, and client.py performs protected HTTP/CAS retries. Authentication is never put in retry envelopes. Only explicit full_resync can reactivate retired/unresolved device registration; received definitions are not executed.

Definition synchronization: definition_privacy binds action signatures and replaces private literals/paths with local references; definition_adapter and runtime_adapters preserve causal heads and register received behaviors disabled. assets/asset_service stream checked files into owned temps. definition_files/service/apply_service keep account+endpoint state, explicit conflict choices, baseline checks and asset readiness. wire_api supplies JSON-only AC/MCP adapters; ConfigSyncTab owns cancellable workers and readonly reports. Folder snapshots and TCP clipboard guards are wired into their actual transports.

Remote session ownership: sessions.py stores immutable identities/generations, separate transport/role script aliases, request bindings and bounded lifecycle events; registry_sessions.py shares lifecycle allocation. session_api.py provides JSON lifecycle commands. PanelSessions owns GUI identity and checks generation at producer and Qt delivery, then cleans its independent resources at destruction. The WebRTC compatibility module re-exports typed panels composing layout/features/transfers/session controllers; shared presentation helpers remove repeated UI contracts.

Config recovery stores local intents separately from exact CAS envelopes; SyncOutbox atomically supersedes only intents/confirmed conflicts. ConfigSyncClient revalidates fresh snapshots and reassigns rejected tentative deletion receipts. Definition adapters acknowledge resolved Apply rather than preview receipt. Qt handlers retain generation through final delivery; reconnect callbacks are revoked and folder sender ownership persists during drain.

Wayland capability diagnostics use `wrapper/capabilities.py`, exposed as the
Beta `api.capabilities` namespace and compatibility facade. Passive snapshots
separate input/capture availability, authorization/dependency recovery and
XWayland scope. `oeffis._Session.poll()` and libei device dispatch validate
existing grants before control; cancellations and connection failures are
cached until explicit retry, and text input observes the same refusal. GUI
Diagnostics and `AC_diagnose` use passive checks; Python keeps its active
default. CLI input requires explicit selection. Stop/retry operations own the
native portal grant; the compositor owns cleanup of revoked devices.

Native EI verification runs independent half-open and live-peer subprocess
sentinels. Exit status plus markers around `ei_unref` distinguish cleanup
results from probe setup failures; a bounded child and faulthandler preserve
crash evidence. The EIS image supplies both probes without a compositor, and
Docker CI retains the EI/Wayland logs even when a verification step fails.

Default native EI sessions are now owned by `linux_wayland/ei_worker.py`;
`ei_transport.py` provides a private bounded JSON channel, request identities,
serialized batches, total deadlines and concurrent cancellation. The parent
only probes symbols; the helper owns context/devices/portal grants. EOF releases
held input on the same grant and closes the native session. Failed/uncertain
requests reap the helper without replay; helper exit reclaims abandoned
half-open contexts. Crash diagnostics retain a bounded faulthandler tail.
`LibeiBackend` is still the direct binding used by native verification.
`docker/ei_worker_verify.py` checks real emission, cleanup, descriptor stability,
crash containment and IPC latency; Docker CI retains its log in the EI artifact.

Image conversion/template/file/healing paths use the lazy `cv2_utils/optional.py`
backend seam. OpenCV remains preferred; `numpy_backend.py` supplies bounded tiled
FFT normalized grayscale matching and Pillow I/O when it is absent. The Windows
arm64 dependency marker installs NumPy without changing other platforms' base
requirements. Strict OpenCV accessors remain separate typed capability refusals.
The platform smoke workflow includes arm64 image tests that never inject input;
headless fallback tests compare outputs against OpenCV on other platforms.

The D3 recording foundation separates raw physical input from executor action
journals: `linux_wayland/input_events.py` opens only explicitly chosen existing
physical Linux nodes, verifies sysfs/device identity and excludes virtual sources.
A bounded worker returns raw device units and fails incomplete capture.
`global_shortcuts.py` owns an asynchronous GlobalShortcuts session on its private
D-Bus connection; bounded polling, pending signals and abort permit cancellation
and cleanup. Refusal is cached until explicit close/start; revocation invokes the
caller-owned stop callback. `wrapper/wayland_input.py` owns separate raw capture
and shortcut lifetimes; Beta `api/wayland_input.py` and the facade expose five
shared AC/MCP/Script Builder operations. Remote access requires MANAGE_HOSTS.
The Diagnostics child panel runs operations through CallWorker, displays actual
portal binding and raw events, and disposes only its own resources. Action
journals mask raw physical results. Native acceptance remains in D3/H3.

Native default authorization uses a separate connection-attempt lock, with
active/pending owners detached under a short cache lock. Stop/reset cancel
pending IPC and stale completion cannot publish its grant; permission polling
also leaves the cache lock free. Tests include controlled workers without
performing desktop input.

Linux/macOS Python 3.10 quality jobs run the unchanged coverage command under
gdb/lldb through `test/verify/native_debugger.py`. Owned debugger process groups
are bounded by a 30-minute deadline. Artifacts retain target/debugger exit codes,
versions, command files and native frames; missing target exit evidence fails
the job. Capturing diagnostics does not establish the USB Qt crash root cause.

StopShortcutSession subscribes to the bus daemon's portal NameOwnerChanged events.
Owner loss/replacement invalidates both pending and active grants without retry;
active revocation signals the owning callback. Independent GI/GDBus native peers
and installed-wheel verification run in quality and the portal Docker CI job,
retaining per-scenario records and logs. Desktop consent/recovery remains D3/H3.

GUI translation registries retain child wrappers but store self/title-tab entries
through weak proxies. This removes the registry's owner-to-self cycle, which
otherwise lets background Python GC destroy parentless widgets off the GUI
thread. Isolated ownership/translation tests preserve live language switching.

Shared D-Bus cancellation detaches the connection and wakes pending I/O. The
last in-flight operation closes its descriptor; read polling checks cancellation
every 100 ms while preserving the original request deadline. Late completion
is rejected, and reconnect is refused until the previous descriptor has drained.

macOS Quartz/AppKit and the recording tap load only for native operations,
so imports and pure CLI file errors do not initialize those frameworks.
Explicit `grab_logical(metrics=...)` selects virtual-frame geometry on every
host; default macOS capture retains per-display Retina normalization. EI helper
cancellation also retains its socket until the transaction exits, polls reads
without shortening the total deadline and rejects completion after cancellation.

D3 Docker verification shares `docker/physical_source_verify.py` between the
uinput and sway/libinput seat images. It independently checks kernel identity,
installed-wheel origin, pre-open exclusion and recorder cleanup, without opening
physical input devices. Docker CI supports a manual D3 native scope and retains
seat/uinput failure output alongside existing EIS/portal/compositor artifacts.

Mobile ownership: wrapper/_mobile_models.py freezes identities/configuration and
validates bounded request timeouts; _mobile_binding.py provides a ContextVar and
minimal Protocol without importing SDK clients. device_context.py owns lazy ADB,
uiautomator2 and WDA adapters. _mobile_client_owner.py uses separate lifecycle
and connection locks, revokes waiters and disposes constructors that finish late.
_mobile_sdk.py guards retained public SDK operations and native request boundaries,
unregistering only this client's Android exit callback and reclaiming only its
started helper. _mobile_adb.py preserves the existing argv-only bounded transport.
Matrix snapshots specs before fan-out and binds each worker's frozen owner.
The Beta mobile API/facade and AC/MCP/Builder/GUI probe share passive metadata;
Device Matrix uses CallWorker, whose relay holds owner-bound callbacks weakly.
SDK bootstrap/retry total deadlines and actual-device recovery remain H3 cases.

E2 adds headless mobile Gesture/DeviceFrame and session capture/input dispatch.
Device frames validate immutable PNG against the observed native viewport,
convert screenshot pixels to UIKit points/Android pixels and preserve mapping
through display rotation. Fixed-frame OCR and template/VLM reuse the same bytes;
bound self-heal chooses device capture and touch before any desktop helper.
JSON services reuse an active matrix owner or open/close an explicit context and
reject foreign specs. Facade, AC, MCP, Builder and Device Matrix Actions share
these services; sensitive text arguments are masked. Legacy iOS values remain
native points. Android ADB input refuses Unicode and names the SDK alternative.
No optional SDK/Qt import occurs during passive mobile imports.

E3 adds observed app lifecycle in wrapper/mobile_apps.py and per-platform apps.py.
_mobile_wda_app.py freezes newly created WDA IDs and uses bounded low-level HTTP
without SDK global locks or automatic input replay. It retains IDs for cleanup
retry, including construction completing after cancellation. Revoked clients
remain retained until their owner is collected, permitting repeated close after
late cleanup failure. Android lifecycle uses explicit owned ADB argv.
_mobile_extension_models.py defines passive factory specs and MobileExtension;
_mobile_extension_owner.py validates paths/options and lazily binds one adapter.
android/extensions.py supplies install/files/SDK clipboard. iOS extensions and
recording require configured adapters. The shared JSON app/alert/extension services
reach AC/MCP/Builder and Device Matrix Actions; remote access requires MANAGE_HOSTS.

_mobile_wda_lease.py reserves exact endpoints before native construction using a short registry lock. Bounded status preflight rejects active/missing ownership metadata before POST/session. WDA creation replaces its active session; dedicated endpoints must remain exclusive against external clients and aliases. Unknown creation replies remain unknown native state; they are not automatically retried.

E4 exposes a persistent MobilePanelOwner through a thin MobileTab. The shared operation
catalog supplies Android/iOS alias enums, MCP/Builder and device-only batch validation.
Setup is passive unless connect is requested; the live executor inventory lists scope
and alternatives. Owner close revokes immediately and cleans on a headless thread;
GUI callbacks reject obsolete generations. Explicit result values remain available
while automatic extension logs are masked. Docker/KVM and remote WDA setup/smoke
configuration live in docs/MOBILE_SETUP.md and examples/mobile_device_smoke.py.

F1 keeps main_widget.py as a compatible import shim to _lazy_widget.py.
_tab_catalog.py contains pure stable keys, import targets and action metadata;
_tab_factories.py resolves only the selected panel. _core_tab_proxy.py descriptors
preserve unbound/bound legacy core handlers without eagerly importing mixins.
TabSpec/TabRegistry are Qt-free metadata with owner-scoped instances; hide retains
state, explicit close releases it, and parent destruction drops cached references.
Only default record/script_builder/remote_desktop factories run at startup.
