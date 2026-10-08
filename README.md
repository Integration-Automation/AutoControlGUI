# AutoControl

[![PyPI](https://img.shields.io/pypi/v/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![Python](https://img.shields.io/pypi/pyversions/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Documentation](https://readthedocs.org/projects/autocontrol/badge/?version=latest)](https://autocontrol.readthedocs.io/en/latest/?badge=latest)

**AutoControl** is an open-source, cross-platform **computer-use and GUI automation framework** for AI agents, Python applications, and automated testing. It drives the mouse and keyboard, finds UI targets through template matching, OCR, the OS accessibility tree, or a vision model, records and replays flows, and runs deterministic JSON actions across Windows, macOS, Linux (X11 and Wayland), the BSDs, Android, and iOS.

Every capability ships three ways: a **Python API**, an **`AC_*` action command** usable
from JSON files / CLI / servers, and a **GUI tab**. Nothing is GUI-only.

**[繁體中文](README/README_zh-TW.md)** · **[简体中文](README/README_zh-CN.md)**

---

## Why AutoControl

- **One API, seven platforms.** `wrapper/platform_wrapper.py` picks the backend at import
  time; your script does not change between Windows, macOS, X11, and Wayland.
- **Scriptable without Python.** 848 `AC_*` commands cover the whole feature set, so a
  JSON file can do anything the library can — including loops, branches, try/catch,
  macros, and variables.
- **Headless by default.** `import je_auto_control` never loads Qt. The GUI is an
  optional extra that wraps the same headless core.
- **Locate things four ways.** Template matching, OCR, the accessibility tree, and a
  vision-language model — composable through anchor locators and self-healing fallbacks.
- **Light dependency floor.** The REST server, JSON Schema validator, JWT, TOTP,
  WebSocket framing, ACME client, USB/IP protocol, and Prometheus metrics are all
  standard-library implementations. Heavy things are opt-in extras.


## AI agents and computer use

**AutoControl is an open-source, cross-platform computer-use and GUI automation framework for AI agents.**

Use it when an agent needs to operate a real desktop GUI — native applications, real browser windows, remote desktops, or mobile devices — rather than only a browser DOM/API.

### When an AI agent should choose AutoControl

- Real mouse and keyboard input
- Screenshots and screen-coordinate interaction
- OCR and native accessibility-tree discovery
- Image/template matching
- Vision-language-model UI localization
- Anchor and self-healing locators
- Cross-platform desktop/mobile automation
- Deterministic JSON action files
- MCP-based computer use

A robust agent loop is:

**observe → identify → act → wait → verify → recover**

The repository also has a dedicated [AI agent guide](AI.md) with MCP configuration, tool selection, OpenAI integration, security guidance, and searchable computer-use terminology.

### AI-friendly MCP

Start the stdio server with:

```bash
pip install je_auto_control
je_auto_control_mcp
```

The MCP server exposes the canonical `ac_*` surface plus short, model-friendly aliases such as `click`, `type`, `screenshot`, `find_text`, `click_text`, `drag`, `focus_window`, and `wait_image`.

For inspection-only clients:

```bash
je_auto_control_mcp --read-only
```

If a client needs only canonical `ac_*` names:

```bash
JE_AUTOCONTROL_MCP_ALIASES=0 je_auto_control_mcp
```

For OpenAI agent integrations, expose a focused allow-list with `export_openai_tools(only=[...])` instead of passing the complete AutoControl command catalogue. This both fits provider limits and reduces the authority given to the model.

### Project identity

**Project:** AutoControl  
**Repository:** `Integration-Automation/AutoControlGUI`  
**Python package / PyPI:** `je_auto_control`  
**MCP command:** `je_auto_control_mcp`


---


## Choosing the right automation layer

AutoControl is not intended to replace every automation tool. Use the smallest layer that matches the interface:

| Need | Good fit |
|---|---|
| Stable browser DOM/API automation | Playwright / Selenium |
| Simple Python mouse and keyboard scripting | PyAutoGUI or AutoControl |
| Native desktop application automation | **AutoControl** |
| Accessibility-tree GUI automation | **AutoControl** |
| OCR-driven GUI automation | **AutoControl** |
| Screenshot / vision-model GUI localization | **AutoControl** |
| Self-healing cross-platform GUI locators | **AutoControl** |
| AI agent controlling a real desktop | **AutoControl + MCP** |
| Deterministic JSON GUI workflows | **AutoControl** |

The differentiator is the combination of **real computer input + semantic/visual discovery + self-healing + agent/MCP integration** behind one cross-platform automation surface.


## Installation

```bash
pip install je_auto_control            # core
pip install je_auto_control[gui]       # + PySide6 desktop app
```

Optional extras, installed only when you need them:

| Extra | Enables |
|---|---|
| `gui` | PySide6 desktop application (50 tabs): a searchable navigation panel (`Ctrl+K`) lists every feature by category, tabs are built the first time they are opened, and **View → Theme** switches dark / light |
| `webrtc` | WebRTC remote desktop, USB passthrough (`aiortc`, `av`) |
| `signaling` | Standalone signaling / rendezvous server (`fastapi`, `uvicorn`) |
| `discovery` | mDNS / Zeroconf LAN host discovery |
| `pdf` / `office` | PDF and Excel / Word / PowerPoint reading |
| `fuzzy` / `locale` | `rapidfuzz` matching, `babel` locale parsing |
| `s3` / `audio` | S3 artifact store, system volume control |

**Windows on arm64** installs and runs, minus what upstream cannot ship
there: neither `opencv-python` nor `cryptography` publishes a `win_arm64`
wheel. So `find_image*`, `screenshot()` (the OpenCV/BGR one — the Pillow
capture still works), the secret vault, action-file encryption, ACME/TLS
and encrypted recording each raise a message naming the missing wheel
instead of failing obscurely. Mouse, keyboard, screen size, window
management, the accessibility tree, the action executor, the MCP/REST/TCP
servers and the GUI all work — measured, not assumed. Every other platform
is unaffected.

**Requirements:** Python ≥ 3.10 (≥ 3.11 on Windows arm64, which is where
CPython's official builds for it start). On Linux, install build
prerequisites first:

```bash
sudo apt-get install cmake libssl-dev
```

OCR, VLM, and LLM backends (`pytesseract`, `easyocr`, `paddleocr`, `anthropic`,
`openai`) are loaded on demand — install whichever you actually use. For Tesseract,
`find_tesseract_cmd()` locates the executable (`$TESSERACT_CMD`, then `PATH`, then the
installers' default folders), `set_tessdata_dir()` points it at a language-data folder,
and `ocr_status()` / `ocr_languages()` say what is missing before the first OCR call.

**Log file:** the library logs to `~/.je_auto_control/logs/AutoControlGUI.log`,
created on the first record (importing alone writes nothing) and shared by every
process on the account (appended to, one process id per line, moved to `.1`
past 10 MB). Set `JE_AUTOCONTROL_LOG_FILE` to write elsewhere, or to
`os.devnull` to turn the file off.

---

## 60-second quick start

**1. As a Python library**

```python
import je_auto_control as ac

ac.set_mouse_position(500, 300)
ac.click_mouse("mouse_left")
ac.write("Hello World")
ac.hotkey(["ctrl_l", "s"])

x, y = ac.locate_image_center("save_button.png", detect_threshold=0.9)
ac.click_text("Submit")                       # OCR
ac.click_accessibility_element(name="OK")     # accessibility tree
ac.click_by_description("the green Submit button")   # vision model
ac.screenshot("shot.png", screen_region=[0, 0, 800, 600])
```

**2. As a JSON action file** — `flow.json`

```json
[
    ["AC_set_var", {"name": "user", "value": "alice"}],
    ["AC_locate_and_click", {"image": "login.png", "mouse_keycode": "mouse_left"}],
    ["AC_write", {"write_string": "${user}"}],
    ["AC_retry", {"max_attempts": 3, "body": [
        ["AC_wait_text", {"target": "Welcome", "timeout": 10}]
    ]}],
    ["AC_assert_text", {"text": "Welcome"}],
    ["AC_generate_html_report", {"html_name": "report"}]
]
```

```bash
je_auto_control run flow.json --var user=bob
je_auto_control run flow.json --dry-run     # list the steps without touching the mouse
```

**3. As a desktop app**

```bash
pip install je_auto_control[gui]
python -c "import je_auto_control; je_auto_control.start_autocontrol_gui()"
```

Record a flow, edit it in the visual Script Builder, and save it as the same JSON
format the CLI runs. (`python -m je_auto_control` is the legacy action-file runner — `-e`, `-d`,
`-c`, `--execute_str` — not the GUI.)

---

## Capability overview

Every row works headlessly. "GUI tab" is where the same feature surfaces in the
desktop app; tab commands live in the window's **Actions** menu.

| Capability | Python API | `AC_*` command | GUI tab |
|---|---|---|---|
| Mouse | `click_mouse` (`clicks=2` double-clicks), `set_mouse_position`, `mouse_scroll`, `tween_drag` / `drag_path` (paced by `step_delay_s`, `settle_s`) | `AC_click_mouse`, `AC_tween_drag`, `AC_drag_path` | Auto Click |
| Keyboard | `write`, `write_secret`, `hotkey`, `type_keyboard`, `keyboard_key_name` (code → canonical name; Windows also takes aliases such as `ctrl`, `esc`, `enter`) | `AC_write`, `AC_write_secret`, `AC_hotkey` | Auto Click |
| Screen & pixels | `screenshot`, `screen_size`, `get_pixel` | `AC_screenshot` | Screenshot |
| Image matching | `locate_image_center`, `locate_and_click` | `AC_locate_and_click` | Image Detect |
| OCR text | `click_text`, `wait_for_text`, `read_text_in_region`, `ocr_status` | `AC_click_text`, `AC_wait_text`, `AC_ocr_status` | OCR Reader |
| Accessibility tree | `find_accessibility_element`, `click_accessibility_element` | `AC_a11y_find`, `AC_a11y_click` | Accessibility |
| Vision-model locator | `locate_by_description`, `click_by_description` | `AC_vlm_locate`, `AC_vlm_click` | VLM |
| Anchor locator | — | `AC_anchor_click`, `AC_anchor_locate` | — |
| Self-healing locators | `self_heal_click`, `self_heal_locate` | `AC_self_heal_click` | Self-Healing |
| Natural-language planner | `plan_actions`, `run_from_description` | `AC_llm_plan` | LLM Planner |
| Computer-use agent | `AgentLoop`, `run_agent` | `AC_run_agent` | Computer Use |
| Record & replay | `record`, `stop_record` | `AC_record`, `AC_stop_record` | Record |
| JSON scripting | `execute_action`, `execute_files` | all 848 commands | Script, Script Builder |
| Variables & flow control | `execute_action_with_vars` | `AC_set_var`, `AC_loop`, `AC_for_each`, `AC_try`, `AC_retry` | Variables |
| Data-driven runs | — | `AC_for_each_row` (CSV / JSON / SQLite / Excel) | Data Sources |
| Assertions | `assert_text`, `assert_image` | `AC_assert_text` + 20 more | Assertions |
| Test suites | `run_suite` | `AC_run_suite` | Test Suites |
| Scheduler (interval + cron) | `default_scheduler` | — | Scheduler |
| Global hotkeys | `default_hotkey_daemon` | — | Hotkeys |
| Event triggers | `default_trigger_engine` | `AC_email_trigger_add` | Triggers, Webhooks, Email |
| Window management *(Windows, macOS, X11)* | `list_windows`, `focus_window` | `AC_focus_window`, `AC_snap_window` | Window Manager |
| Clipboard (text + image) | `get_clipboard`, `set_clipboard`, `get_clipboard_image`, `set_clipboard_image` | `AC_clipboard_get`, `AC_clipboard_set`, `AC_clipboard_get_image`, `AC_clipboard_set_image` | — |
| Remote desktop | `RemoteDesktopHost`, `RemoteDesktopViewer` | `AC_start_remote_host`, `AC_remote_connect` | Remote Desktop |
| USB enumeration & passthrough | `list_usb_devices`, `enable_usb_passthrough` | `AC_usb_*` (16 commands) | USB Devices, USB Share |
| Secrets vault | `default_secret_manager` | `AC_secret_set` + `${secrets.NAME}` | Secrets |
| Reports (HTML / JSON / XML) | `generate_html_report` | `AC_generate_html_report` | Report |
| Run history | — | — | Run History |
| Metrics & tracing | `default_metric_registry`, `render_metrics_text` | — | — |
| Diagnostics | `run_diagnostics` | `AC_diagnose` | Diagnostics |
| Test-code generation | `generate_code` | — | — |

Beyond this table, `utils/` holds 311 headless packages covering assertions, resilience,
data quality, i18n auditing, redaction, governance, observability, and more. The full
per-module map is in **[architecture_explore.md](architecture_explore.md)**.

---

## Command-line interface

```bash
je_auto_control run script.json [--var name=value] [--dry-run] [--allow-package NAME]
je_auto_control validate script.json          # alias: lint
je_auto_control fmt script.json [--check]
je_auto_control list-commands [--filter mouse] [--json]
je_auto_control record out.json [--duration 5]
je_auto_control codegen script.json --target pytest -o test_flow.py
je_auto_control failure-bundle failure.zip --error "login timed out"
je_auto_control list-jobs
je_auto_control start-server --port 9938      # TCP socket server
je_auto_control start-rest   --port 9939      # REST API
je_auto_control version
```

`--var name=value` is parsed as JSON when possible (`count=10` becomes an int),
otherwise kept as a string. `run` exits 1 when any action failed (the run
still goes on to the end), so a CI step fails with it. The legacy
`python -m je_auto_control -e file.json` entry point still works, and its
`-e`, `-d` and `--execute_str` flags exit 1 the same way. Under
[TestPioneer](https://github.com/Integration-Automation/TestPioneer), which
sets `TEST_PIONEER_ARTIFACT_DIR`, the HTML, JSON and XML reports asked for
under a relative name are written below that directory.

---

## Servers and integrations

| Surface | Start it with | Notes |
|---|---|---|
| **MCP server** | `je_auto_control_mcp` (stdio) or `AC_start_mcp_http_server` | 754 tools for Claude Desktop / Claude Code / custom tool loops: the full `ac_*` surface plus short model-friendly aliases for common GUI actions. Speaks the stateless MCP 2026-07-28 beside the `initialize`-based revisions. Bearer auth, TLS, audit log, rate limit, plugin hot-reload, CI fake backend. |
| **REST API** | `je_auto_control start-rest` | Bearer token, per-IP rate limit + lockout, SQLite audit hook, `/metrics`, `/openapi.json`, `/docs` Swagger UI, `/dashboard`. |
| **TCP socket server** | `je_auto_control start-server` | Newline-framed JSON action lists. Binds `127.0.0.1` by default. |
| **pytest plugin** | installed automatically | Fixtures plus a Gherkin step library for pytest-bdd / behave. |
| **Language server** | `python -m autocontrol_lsp.server` | Completion and diagnostics for `AC_*` action JSON, generated from the live command table. |
| **Remote desktop** | `RemoteDesktopHost` / GUI | TCP, WebSocket, or WebRTC; TOTP, trust list, TURN config, file/clipboard/audio sync. |

All servers bind to `127.0.0.1` unless you opt in explicitly.

**Package gate.** `AC_add_package_to_executor` and `AC_add_package_to_callback_executor` import a Python package and register its members as commands, so an action list arriving over any of these surfaces could load `os` or `subprocess`. No package loads unless it has been allowed: a package that is not on the allowlist is refused before it is imported, and that action fails with `AutoControlExecuteActionException`. Allow packages (submodules included) from Python with `executor.allow_packages("name", …)`, for every entry point — both CLIs, the socket / REST / MCP servers and the scheduler — with the `JE_AUTOCONTROL_ALLOWED_PACKAGES` environment variable (comma-separated names, read when the process starts), or for one CLI run with `je_auto_control run script.json --allow-package NAME` (repeatable). `executor.set_allow_arbitrary_packages(True)` opens the gate for every package, which is what earlier releases did by default (with a `DeprecationWarning`). None of these is an `AC_*` command, so an action list cannot open its own gate.

**Opt-in hardening.** Each of these is off until configured, and a server without them behaves as before. `JE_AUTOCONTROL_RBAC_USERS=<user store file>` makes the REST API and the MCP HTTP transport resolve the bearer token to a user and authorise each route, tool and privileged `AC_*` command by role (viewer / operator / admin); the shared token is then refused. `JE_AUTOCONTROL_MCP_PATH_ROOTS` (directories separated by the OS path separator) confines every MCP tool argument that is a file path to those directories, `JE_AUTOCONTROL_MCP_PATH_ROOTS_FROM_CLIENT=1` adds the client's `roots/list`, and `JE_AUTOCONTROL_MCP_ENV_REF_ALLOW` limits which `env://` names `ac_resolve_ref` may read. `JE_AUTOCONTROL_ACTION_SIGNING_PUBLIC_KEY` makes an endpoint verify Ed25519-signed action files without being able to sign them (`create_signing_keypair`; the private key stays on the signing machine). A remote-desktop viewer writes files pushed by a host only below `~/Downloads/AutoControl` (`JE_AUTOCONTROL_REMOTE_DOWNLOAD_DIR`); that one is on by default.

**Also configurable.** `JE_AUTOCONTROL_MCP_TOOL_MODE=progressive` (or `je_auto_control_mcp --tool-mode`) starts an MCP session with five core tools that search, describe and enable the rest; `static` serves a fixed profile (`JE_AUTOCONTROL_MCP_TOOL_PROFILE`); the default `full` mode is unchanged. Users for RBAC are managed with `je_auto_control users add|remove|set-role|rotate-token|list`, the `AC_user_*` commands or the REST API tab. `JE_AUTOCONTROL_ACTION_SIGNING_PASSPHRASE` unlocks a passphrase-protected signing key. The action journal (`start_action_journal`, `AC_journal_*`) records executed actions with secrets masked, and `je_auto_control codegen --from-log` turns one run into a candidate script. Config sync keeps buckets in SQLite with revision-checked writes (`--config-db`, `AC_SIGNALING_CONFIG_DB`; older clients need `--allow-blind-config-writes`). Android and iOS devices get their own sessions (`open_device`, `AC_android_*`, `AC_ios_*`); none of the mobile code has been run on a device yet. On Wayland, `probe_capabilities` / `AC_probe_capabilities` report what input and capture can do and why, and `JE_AUTOCONTROL_WAYLAND_EI_WORKER=1` moves libei into a helper process. The GUI remembers theme, text size, panel and window geometry in `~/.je_auto_control/gui_settings.ini` (`JE_AUTOCONTROL_GUI_SETTINGS`).

### How the remote-desktop wire protocol works

Worth knowing before you expose a host, and described nowhere else in the
docs. The default transport is length-prefixed framing over raw TCP — no extra
dependencies — and it opens with an **HMAC-SHA256 challenge/response
handshake**: a viewer that fails auth is dropped before it is sent a single
frame. JPEG frames are encoded at the configured FPS and quality and handed to
authenticated viewers through a shared *latest-frame slot*, so a slow viewer
drops frames instead of stalling the rest. Viewer input arrives as JSON and is
**validated against an allow-list** of actions before being applied through the
ordinary input wrappers, so a viewer cannot invent new operations.

```python
# Be remoted — start a host and hand the token + port to whoever views you
from je_auto_control import RemoteDesktopHost
host = RemoteDesktopHost(token="hunter2", bind="127.0.0.1",
                         port=0, fps=10, quality=70)
host.start()
print("listening on", host.port, "viewers:", host.connected_clients)
```

```python
# Control another machine — connect a viewer and send input
from je_auto_control import RemoteDesktopViewer
viewer = RemoteDesktopViewer(host="10.0.0.5", port=51234, token="hunter2",
                             on_frame=lambda jpeg: ...)
viewer.connect()
viewer.send_input({"action": "mouse_move", "x": 100, "y": 200})
viewer.disconnect()
```

Narrow who may connect at all with an IP allow-list (CIDR ranges or exact
addresses); peers outside it are rejected during the handshake:

```python
RemoteDesktopHost(token="tok", ip_allowlist=["10.0.0.0/8", "192.168.1.100"])
```

---

## Platform support

| Platform | Backend | Input | Screen capture | Recording | Window management |
|---|---|:---:|:---:|:---:|:---:|
| Windows 10 / 11 | Win32 ctypes (+ optional Interception driver) | ✅ | ✅ | ✅ | ✅ |
| macOS 10.15+ | pyobjc / Quartz | ✅ | ✅ | ✅¹ | ✅ |
| Linux X11 | python-Xlib (+ optional `uinput`) | ✅ | ✅ | ✅ | ✅ |
| Linux Wayland | libei via the desktop portal, or ydotool / wtype + a capture tool | ✅ | ✅ | ❌ | ❌ |
| FreeBSD / OpenBSD / NetBSD | python-Xlib, the same X11 backend as Linux | ✅² | ⚠️² | ✅² | ✅² |
| Android | adb + uiautomator2 | ✅ | ✅ | — | — |
| iOS | WebDriverAgent / facebook-wda | ✅ | ✅ | — | — |

¹ macOS recording captures through a Quartz event tap and needs
**Accessibility** permission (System Settings → Privacy & Security →
Accessibility). Without it recording raises and names the permission
rather than returning an empty session.

² The BSDs run the X11 backend unchanged — the same X server, the same
`python-Xlib`, which is the only dependency input, recording and window
management have. A `freebsd` CI job drives real input on a real FreeBSD 14 and
reads it back off the X server; OpenBSD and NetBSD take the same code path but
have no CI runner. Screen capture is the exception, and the reason is
packaging rather than the platform: it goes through Pillow/mss and OpenCV, and
`opencv-python`, `pillow` and `cryptography` publish no FreeBSD wheels. Build
those from ports and capture, image matching, OCR and action encryption work
too — `import je_auto_control` no longer requires any of them.

Wayland input falls back to the `ydotool` CLI wherever libei is not
reachable, and that fallback needs **ydotool 1.0 or newer**. Every argument
AutoControl builds arrived in that release; 0.1.x — which is what Debian
bookworm and every current Ubuntu still ship under that name, and Debian
trixie ships not at all — answers the same arguments with exit code 0 and no
events. AutoControl detects it and refuses rather than reporting success for
input it never sent. Arch, Fedora and Debian unstable package 1.0.

That fallback also positions the pointer accurately **only where the
compositor's pointer acceleration is off**. `ydotool mousemove --absolute`
sends no absolute event: it drives the cursor into the corner the compositor
clamps to and then moves relative to it, so the compositor accelerates the
move — measured against a real wlroots session, libinput's default profile
travels exactly twice the distance asked for. ydotool's own `--help` says the
same; AutoControl logs it once per process rather than mispositioning in
silence. Turn acceleration off for the ydotoold device (sway: `input
type:pointer accel_profile flat` and `pointer_accel 0`), or install
`liboeffis` so the libei path — absolute at the protocol level — is used.

The factor is the compositor's own setting and no client can read it back, so
only you know whether it is off. `JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL=flat`
says it is, and moves silently; `=strict` refuses the move rather than let a
click land somewhere else; leaving it unset keeps the warn-and-move default.

Wayland screen capture needs the tool your compositor supports, because no
single one covers them all: `grim` on wlroots compositors (sway, Hyprland,
river), `gnome-screenshot` on GNOME, `spectacle` on KDE. Install one and every
capture path — screenshots, image and anchor locators, OCR, screen recording,
remote desktop — goes through it. With none of them installed, `gdbus` is
enough: `xdg-desktop-portal` is tried last, though it may ask for consent the
first time. Failing that, capture fails loudly with an install hint rather than
returning the blank XWayland root. The `screen_capture` check in
`je_auto_control.api.run_diagnostics()` (and the GUI Diagnostics tab) reports
which tier is in use.

One Wayland-only difference to plan around: **a capture may contain the mouse
cursor.** Nothing here asks for it, but wlroots composites a *software* cursor
into the output buffer whenever the backend has no cursor plane — which
includes any session run with `WLR_NO_HARDWARE_CURSORS=1` — and that buffer is
what screen capture hands back. Windows and X11 never include the pointer, so a
locator, a template match or an OCR read can find a pointer-shaped hole in the
middle of its target here and nowhere else. Wayland does not let a client read
the cursor position, so there is nothing to reliably mask or move around it:
park the pointer away from what you are about to capture. The `screen_capture`
check reports this as `cursor_may_be_captured`.

For a setup none of that fits, name your own command — it wins over every
detected tool, and `{output}` is replaced with a temporary PNG path:

```bash
export JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND="mycapture --png {output}"
```

Wayland forbids global input recording for unprivileged clients — set
`JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11` to record on an X11 session. Window
management works on Windows, macOS (pyobjc) and X11, including XWayland; on a pure
Wayland session, whose protocol hides other clients' windows, `list_windows()` returns
an empty list and every window action raises `AutoControlUnsupportedOperationException`
saying why. Opt-in driver-level backends (`JE_AUTOCONTROL_WIN32_BACKEND=interception`,
`JE_AUTOCONTROL_LINUX_BACKEND=uinput`, ViGEm virtual gamepad) exist for apps that
ignore synthetic input, and fall back silently when the driver is absent.

---

## Configuration

Every environment variable AutoControl reads. Nothing here is required: with no variable set, AutoControl picks the platform backend by itself, servers bind `127.0.0.1`, and every opt-in feature (signature enforcement, RBAC, USB passthrough, tool-path roots) is off. The [configuration reference](https://autocontrol.readthedocs.io/en/latest/Eng/doc/configuration/configuration_doc.html) ([source](docs/source/Eng/doc/configuration/configuration_doc.rst)) has the accepted values in full and links each variable to the page that explains the feature; CI compares it, and the tables below, with the code.

### Platform backends

| Variable | Default | Effect |
|---|---|---|
| `JE_AUTOCONTROL_WIN32_BACKEND` | `sendinput` | `interception` sends keyboard and mouse through the Interception driver; falls back to `SendInput` with a warning when the driver or DLL is missing. |
| `JE_AUTOCONTROL_LINUX_BACKEND` | `x11` | `uinput` writes kernel input events; falls back to XTest with a warning when `/dev/uinput` is not writable. |
| `JE_AUTOCONTROL_LINUX_DISPLAY_SERVER` | `auto` | Which Linux backend loads: `auto` reads `XDG_SESSION_TYPE` and `WAYLAND_DISPLAY`; `wayland` or `x11` forces one (`x11` on a Wayland session drives XWayland windows only). |

### Windows Interception driver

| Variable | Default | Effect |
|---|---|---|
| `JE_AUTOCONTROL_INTERCEPTION_DLL` | unset: `PATH`, then next to the package | Full path of `interception.dll`. |
| `JE_AUTOCONTROL_INTERCEPTION_KEYBOARD` | `1` | Interception device id (`1`–`10`) keyboard events are sent to. |
| `JE_AUTOCONTROL_INTERCEPTION_MOUSE` | `11` | Interception device id (`11`–`20`) mouse events are sent to. |

### Wayland

| Variable | Default | Effect |
|---|---|---|
| `JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND` | `auto` | `cli` sends input through `ydotool` and never asks the desktop portal. Chosen before starting: after a refused consent AutoControl does not switch to it by itself. |
| `JE_AUTOCONTROL_WAYLAND_EI_WORKER` | unset | `1` runs the libei session in a helper process instead of in-process. |
| `JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL` | `warn` | Absolute moves on the `ydotool` path only (relative motion the compositor accelerates): `warn` warns once and moves, `flat` declares acceleration off and moves silently, `strict` refuses the move. |
| `JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND` | unset | Your own screenshot command line, with `{output}` where the PNG path goes. Takes precedence over `grim`, `gnome-screenshot`, `spectacle` and the portal. |
| `JE_AUTOCONTROL_WAYLAND_RECORD_DEVICES` | unset: none | Comma-separated `/dev/input/event*` devices `PhysicalRecorder` may read; physical recording is opt-in per device. |

### MCP server

| Variable | Default | Effect |
|---|---|---|
| `JE_AUTOCONTROL_MCP_READONLY` | unset | `1`: only tools marked read-only are offered and callable. |
| `JE_AUTOCONTROL_MCP_TOOL_MODE` | `full` | How much of the registry `tools/list` offers: `full`, `progressive` or `static`. An unknown value is an error rather than `full`. |
| `JE_AUTOCONTROL_MCP_TOOL_PROFILE` | unset | Comma-separated tool names and `category:<name>` entries of the `static` profile. |
| `JE_AUTOCONTROL_MCP_ALIASES` | `1` | `0` leaves out the short aliases (`click`, `screenshot`, …) registered beside the `ac_*` tools. |
| `JE_AUTOCONTROL_MCP_TOKEN` | unset | Bearer token of the HTTP transport. Not accepted once RBAC is on. |
| `JE_AUTOCONTROL_MCP_ALLOWED_ORIGINS` | unset: loopback origins only | Comma-separated extra browser origins (exact, e.g. `https://example.test:8443`) the HTTP transport accepts. |
| `JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE` | unset | `1`: destructive tools ask the client for confirmation (MCP elicitation) before they run. |
| `JE_AUTOCONTROL_MCP_PATH_ROOTS` | unset: no confinement | Directories (separated by the OS path separator) every file argument of a tool must stay inside. |
| `JE_AUTOCONTROL_MCP_PATH_ROOTS_FROM_CLIENT` | unset | `1`: also accept the roots the MCP client reports through `roots/list`. |
| `JE_AUTOCONTROL_MCP_ENV_REF_ALLOW` | unset: no restriction | Comma-separated environment variable names (`fnmatch` patterns allowed) `ac_resolve_ref` may read; a value that names nothing allows none. |
| `JE_AUTOCONTROL_MCP_AUDIT` | unset | Path of a JSON-lines file that receives one record per `tools/call`. |
| `JE_AUTOCONTROL_MCP_ERROR_SHOTS` | unset | Directory a screenshot is saved to each time a tool fails. |
| `JE_AUTOCONTROL_FAKE_BACKEND` | unset | `1`: the MCP server records mouse, keyboard and clipboard calls in memory instead of performing them, for CI without a display. |

### REST / RBAC and chat-ops

| Variable | Default | Effect |
|---|---|---|
| `JE_AUTOCONTROL_RBAC_USERS` | unset: shared token | Path of the user store file. Setting it is what switches roles on for the REST API and the MCP HTTP transport. |
| `JE_AUTOCONTROL_CHATOPS_SCRIPT_ROOT` | unset: `run` is refused | The only directory the chat-ops `run` command may load action files from. |

### Executing and signing action files

| Variable | Default | Effect |
|---|---|---|
| `JE_AUTOCONTROL_ALLOWED_PACKAGES` | unset: none | Comma-separated packages `AC_add_package_to_executor` may load (submodules included), for every entry point. Read once, when the process starts. |
| `JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS` | unset | `1`: every path that runs an action file refuses one without a valid signature sidecar. |
| `JE_AUTOCONTROL_ACTION_SIGNING_PRIVATE_KEY` | unset | Path of the Ed25519 private key (PEM). Set it on the signing machine only; signing then writes a version-2 sidecar. |
| `JE_AUTOCONTROL_ACTION_SIGNING_PUBLIC_KEY` | unset | Path of the matching public key. Set it on every machine that executes: it verifies and cannot sign. |
| `JE_AUTOCONTROL_ACTION_SIGNING_PASSPHRASE` | unset | Passphrase of the private key, when it was created with one. |
| `JE_AUTOCONTROL_ACCEPT_LEGACY_ACTION_SIGNATURES` | unset | `1` is migration mode: once a public key is configured, HMAC sidecars written before version 2 are refused unless this is set. Switch it off again when every file has been re-signed. |

### Remote desktop and signaling

| Variable | Default | Effect |
|---|---|---|
| `JE_AUTOCONTROL_REMOTE_DOWNLOAD_DIR` | `~/Downloads/AutoControl` | Directory a remote-desktop viewer stores files its host sends in. A received path is confined to it. |
| `JE_AUTOCONTROL_USB_PASSTHROUGH` | unset | `1` enables USB passthrough opcodes on the remote-desktop channel. |
| `AC_SIGNALING_SECRET` | unset | Shared secret of the signaling / config-sync server (`X-Signaling-Secret`). Read by the server when `--shared-secret` is not given, and by `config_sync_run` when `secret` is not. |
| `AC_SIGNALING_CONFIG_DB` | `~/.je_auto_control/config_sync.sqlite3` | SQLite file the signaling server keeps config-sync buckets in. |

### GUI

| Variable | Default | Effect |
|---|---|---|
| `JE_AUTOCONTROL_GUI_SETTINGS` | `~/.je_auto_control/gui_settings.ini` | File the main window keeps its theme, text size, navigation panel and geometry in. `off`, `0`, `none`, `false` or empty: nothing is read or written. |

### Logging, data and testing

| Variable | Default | Effect |
|---|---|---|
| `JE_AUTOCONTROL_LOG_FILE` | `~/.je_auto_control/logs/AutoControlGUI.log` | Where the log file is written. The null device (`/dev/null`, `NUL`) switches the file off. Read when the first record is written, not at import. |
| `JE_AUTOCONTROL_ENV` | `default` | The active environment of the asset store (`active_environment()`), so one script reads different values in `dev` and `prod`. |
| `JE_AUTOCONTROL_REDACTION` | `off` | Default screenshot redaction policy: `off`, `moderate` or `strict`. An unknown name is an error, not `off`. |
| `JE_AUTOCONTROL_PYTEST_ARTIFACTS` | `./autocontrol_screenshots` | Directory the pytest plugin writes failure screenshots to when a test did not request the `autocontrol_screenshot_dir` fixture. |

---

## Documentation and examples

| Resource | What's in it |
|---|---|
| [`examples/`](examples/) | 33 self-contained scripts: screenshot + click, OCR, scheduler, remote desktop, agent loop, observability, recording, variables, hotkeys, triggers, reports, MCP, REST, secrets, plugins, computer use, Wayland, cross-host DAGs, chat-ops, pytest/BDD, anchor locators. |
| [Read the Docs](https://autocontrol.readthedocs.io/en/latest/) | Full API reference, English and 中文. |
| [architecture_explore.md](architecture_explore.md) | Every module's responsibility, layer by layer. |
| [docs/CAPABILITY_MATRIX.md](docs/CAPABILITY_MATRIX.md) | Capability × platform matrix. |
| [docs/API_LIFECYCLE.md](docs/API_LIFECYCLE.md) | Stable-API and deprecation policy. |
| [docs/updates/](docs/updates/README.md) | Update log: release notes and finished work, one file per month (formerly `WHATS_NEW.md`). |
| [CHANGELOG.md](CHANGELOG.md) | Compatibility changelog. |
| [SECURITY.md](SECURITY.md) | Security policy and reporting. |

---

## Development

```bash
git clone https://github.com/Integration-Automation/AutoControlGUI.git
cd AutoControl
pip install -r dev_requirements.txt
uv sync                 # or: reproducible install from the committed uv.lock
```

```bash
python -m pytest test/unit_test/headless      # headless unit tests
python -m pytest test/integrated_test/        # cross-module workflows

ruff check je_auto_control/
pylint je_auto_control/
bandit -c pyproject.toml -r je_auto_control/
```

Contributions are welcome — see [CONTRIBUTING.md](CONTRIBUTING.md) and
[CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). Two rules the CI enforces: `import
je_auto_control` must never pull in PySide6, and every feature needs both a headless
API and a GUI surface.

---

## License

[MIT License](LICENSE) © JE-Chen.
See [Third_Party_License.md](Third_Party_License.md) for the licenses of bundled and
optional third-party components.

- **Homepage**: https://github.com/Integration-Automation/AutoControlGUI
- **PyPI**: https://pypi.org/project/je_auto_control/
- **Documentation**: https://autocontrol.readthedocs.io/en/latest/
