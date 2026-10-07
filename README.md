# AutoControl

[![PyPI](https://img.shields.io/pypi/v/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![Python](https://img.shields.io/pypi/pyversions/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Documentation](https://readthedocs.org/projects/autocontrol/badge/?version=latest)](https://autocontrol.readthedocs.io/en/latest/?badge=latest)

**AutoControl** is a cross-platform GUI automation framework for Python. It drives the
mouse and keyboard, finds things on screen (template matching, OCR, the OS accessibility
tree, or a vision model), records and replays flows, and runs them from JSON action
files — on Windows, macOS, Linux (X11 and Wayland), the BSDs, Android,
and iOS.

Every capability ships three ways: a **Python API**, an **`AC_*` action command** usable
from JSON files / CLI / servers, and a **GUI tab**. Nothing is GUI-only.

**[繁體中文](README/README_zh-TW.md)** · **[简体中文](README/README_zh-CN.md)**

---

## Why AutoControl

- **One API, seven platforms.** `wrapper/platform_wrapper.py` picks the backend at import
  time; your script does not change between Windows, macOS, X11, and Wayland.
- **Scriptable without Python.** 819 `AC_*` commands cover the whole feature set, so a
  JSON file can do anything the library can — including loops, branches, try/catch,
  macros, and variables.
- **Headless by default.** `import je_auto_control` never loads Qt. The GUI is an
  optional extra that wraps the same headless core.
- **Locate things four ways.** Template matching, OCR, the accessibility tree, and a
  vision-language model — composable through anchor locators and self-healing fallbacks.
- **Light dependency floor.** The REST server, JSON Schema validator, JWT, TOTP,
  WebSocket framing, ACME client, USB/IP protocol, and Prometheus metrics are all
  standard-library implementations. Heavy things are opt-in extras.

---

## Installation

```bash
pip install je_auto_control            # core
pip install je_auto_control[gui]       # + PySide6 desktop app
```

Optional extras, installed only when you need them:

| Extra | Enables |
|---|---|
| `gui` | PySide6 desktop application (50 tabs) |
| `webrtc` | WebRTC remote desktop, USB passthrough (`aiortc`, `av`) |
| `signaling` | Standalone signaling / rendezvous server (`fastapi`, `uvicorn`) |
| `discovery` | mDNS / Zeroconf LAN host discovery |
| `pdf` / `office` | PDF and Excel / Word / PowerPoint reading |
| `fuzzy` / `locale` | `rapidfuzz` matching, `babel` locale parsing |
| `s3` / `audio` | S3 artifact store, system volume control |

**Windows on arm64** uses the NumPy/Pillow backend for `find_image*`, BGR
`screenshot()` and fixed-frame healing. Its base install includes NumPy 2.4.6.
Advanced OpenCV processing/video and safe cryptography still lack upstream
wheels; the secret vault, action signing/encryption, ACME/TLS and encrypted
recording remain unavailable. Shared backend dependency errors belong to the
framework exception family. The platform smoke job includes native arm64 image
tests; local fallback tests block OpenCV and preserve the existing contracts.

**Requirements:** Python ≥ 3.10 (≥ 3.11 on Windows arm64, which is where
CPython's official builds for it start). On Linux, install build
prerequisites first:

```bash
sudo apt-get install cmake libssl-dev
```

OCR, VLM, and LLM backends (`pytesseract`, `easyocr`, `paddleocr`, `anthropic`,
`openai`) are loaded on demand — install whichever you actually use.

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
| Mouse | `click_mouse`, `set_mouse_position`, `mouse_scroll` | `AC_click_mouse` | Auto Click |
| Keyboard | `write`, `hotkey`, `type_keyboard` | `AC_write`, `AC_hotkey` | Auto Click |
| Screen & pixels | `screenshot`, `screen_size`, `get_pixel` | `AC_screenshot` | Screenshot |
| Image matching | `locate_image_center`, `locate_and_click` | `AC_locate_and_click` | Image Detect |
| OCR text | `click_text`, `wait_for_text`, `read_text_in_region` | `AC_click_text`, `AC_wait_text` | OCR Reader |
| Accessibility tree | `find_accessibility_element`, `click_accessibility_element` | `AC_a11y_find`, `AC_a11y_click` | Accessibility |
| Vision-model locator | `locate_by_description`, `click_by_description` | `AC_vlm_locate`, `AC_vlm_click` | VLM |
| Anchor locator | — | `AC_anchor_click`, `AC_anchor_locate` | — |
| Self-healing locators | `self_heal_click`, `self_heal_locate` | `AC_self_heal_click` | Self-Healing |
| Natural-language planner | `plan_actions`, `run_from_description` | `AC_llm_plan` | LLM Planner |
| Computer-use agent | `AgentLoop`, `run_agent` | `AC_run_agent` | Computer Use |
| Record & replay | `record`, `stop_record` | `AC_record`, `AC_stop_record` | Record |
| JSON scripting | `execute_action`, `execute_files` | all 819 commands | Script, Script Builder |
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
je_auto_control run script.json [--var name=value] [--dry-run]
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
`python -m je_auto_control -e file.json` entry point still works.

---

## Servers and integrations

| Surface | Start it with | Notes |
|---|---|---|
| **MCP server** | `je_auto_control_mcp` (stdio) or `AC_start_mcp_http_server` | 741 tools for Claude Desktop / Claude Code / custom tool loops. Speaks the stateless MCP 2026-07-28 beside the `initialize`-based revisions. Bearer auth, TLS, audit log, rate limit, plugin hot-reload, CI fake backend. |
| **REST API** | `je_auto_control start-rest` | Bearer token, per-IP rate limit + lockout, SQLite audit hook, `/metrics`, `/openapi.json`, `/docs` Swagger UI, `/dashboard`. |
| **TCP socket server** | `je_auto_control start-server` | Newline-framed JSON action lists. Binds `127.0.0.1` by default. |
| **pytest plugin** | installed automatically | Lightweight `je_auto_control_pytest` entry point; fixtures plus Gherkin steps for pytest-bdd / behave. Reinstall after upgrading editable checkouts; the explicit legacy plugin path remains supported. |
| **Language server** | `python -m autocontrol_lsp.server` | Completion and diagnostics for `AC_*` action JSON, generated from the live command table. |
| **Remote desktop** | `RemoteDesktopHost` / GUI | TCP, WebSocket, or WebRTC; TOTP, trust list, TURN config, file/clipboard/audio sync. |

Legacy `python -m je_auto_control -e/-d/--execute_str` and `je_auto_control run`
return exit code 1 for failed actions and 0 for successful runs. Directory runs
retain failures from earlier files; stderr reports the number of failed actions.

Public action runs isolate variables. To share a run across calls, use
`with je_auto_control.execution_scope({"name": "value"}) as scope:`. Nested
actions share it; parallel branches and DAG nodes copy it. REST/MCP requests
always start their own scope. Explicitly owned `Executor` objects retain their
state outside a public scope.

USB passthrough uses request IDs to match replies, including fragmented data
and errors. Late replies cannot satisfy a retry. After a timeout against a
legacy or unconfirmed host, reconnect with a new client; its handles report
`closed`. New hosts echo IDs while preserving the existing frame header.

All servers bind to `127.0.0.1` unless you opt in explicitly.

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

Beta `je_auto_control.api.mobile` adds frozen `DeviceContext` identities and lazy
`open_device(context)` sessions with `bind()`, `capabilities`, `cancel()` and
idempotent `close()`. Matrix workers use independent owners, including implicit
mobile commands; duplicate configured targets and foreign client overrides are
rejected. Helpers outside a binding retain their compatible defaults. Native
request timeouts are per owner; cancellation rejects late results and reclaims
only that client's started Android helper. `connected` denotes logical lifetime.
`probe_device_contexts`, `AC_probe_mobile_devices` and MCP `ac_probe_mobile_devices`
inspect dependencies without connecting or sending input; remote probing requires
host administration. Device Matrix offers the probe in Actions and runs matrices
in the background; Script Builder shares the command. See the
[mobile guide](docs/source/Eng/doc/mobile/mobile_doc.rst) and
[hardware-free example](examples/mobile_contexts.py). Native device reachability,
authorization, SDK bootstrap deadlines and recovery remain acceptance cases.

`DeviceSession` also provides `capture()`, `perform(Gesture)` and `type_text()`.
`DeviceFrame` holds immutable PNG bytes, native viewport/orientation and
`pixel_to_point()`; `rotated()` preserves that mapping. UIKit points differ from
Retina screenshot pixels; legacy iOS numeric input stays unchanged. Attach `frame=frame` to a Gesture to recheck its owner/geometry before input.
Capture rejects
geometry changes and mismatched aspect ratios instead of guessing a rotation.
Android Unicode uses the SDK IME/clipboard route; `AdbClient.text` and
`AC_android_text` reject non-ASCII before input. The SDK may configure its input
method/clipboard; native restoration remains acceptance work. Frame `ocr()` and
`locate(strategy)` share supplied bytes. Bound `self_heal_locate`/`self_heal_click`
use one device frame and native touch, without desktop fallback; mobile full-frame
search rejects desktop `screen_region` and non-left mouse buttons.
`mobile_capture`, `mobile_gesture`, `mobile_type_text` are mirrored as
`AC_mobile_*`, MCP `ac_mobile_*` and Builder schemas, usable from Device Matrix
Actions. Supply a device object or use the active matrix owner. Remote calls
require host administration; text is masked in action/journal arguments and is
not echoed in the response. WDA pinch requires `/actions` support; failures are
typed. [Frame mapping example](examples/mobile_frame_mapping.py) sends no input.

Image matching and `screenshot()` prefer OpenCV and use a NumPy/Pillow backend
when OpenCV is absent. Windows arm64 installs NumPy 2.4.6 on Python 3.11+.
Normalized grayscale matching, BGR screenshot arrays, file decoding/encoding,
match previews and fixed-frame healing use existing Python/AC/GUI/MCP entry
points. The fallback accepts uint8/float32 arrays and 8-bit image files,
limits frames to 16,777,216 pixels and each tiled FFT to 4,194,304 cells, and
reports a typed error for unsupported budgets or operations. Advanced OpenCV
processing/video and encryption/signing retain their native dependencies.

¹ macOS recording captures through a Quartz event tap and needs
**Accessibility** permission (System Settings → Privacy & Security →
Accessibility). Without it recording raises and names the permission
rather than returning an empty session.

² The BSDs run the X11 backend unchanged — the same X server, the same
`python-Xlib`, which is the only dependency input, recording and window
management have. A `freebsd` CI job drives real input on a real FreeBSD 14 and
reads it back off the X server; OpenBSD and NetBSD take the same code path but
have no CI runner. Screen capture is the exception, and the reason is
packaging rather than the platform: it uses Pillow/mss with OpenCV or NumPy conversion, and
`opencv-python`, `pillow` and `cryptography` publish no FreeBSD wheels. Build
those from ports and capture, image matching, OCR and action encryption work
too — `import je_auto_control` no longer requires any of them.

Wayland input uses libei by default. CLI input requires explicit
`JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=cli` and **ydotool 1.0 or newer**. Every argument
AutoControl builds arrived in that release; 0.1.x — which is what Debian
bookworm and every current Ubuntu still ship under that name, and Debian
trixie ships not at all — answers the same arguments with exit code 0 and no
events. AutoControl detects it and refuses rather than reporting success for
input it never sent. Arch, Fedora and Debian unstable package 1.0.

`probe_capabilities()` (Beta `je_auto_control.api.capabilities`),
`AC_probe_capabilities` and MCP `ac_probe_capabilities` report independent input/capture states (`available`,
`needs_permission`, `needs_dependency`, `unsupported`) without requesting
consent, emitting input, taking screenshots or loading native libraries.
XWayland is explicitly limited to X11 windows; discovered helpers do not
prove compositor support. Canceled, failed or revoked native grants stop input
and never select CLI automatically. The Wayland Diagnostics Actions menu can
stop native control or allow a new authorization attempt; the next explicit
input request prompts again. Restore tokens are unsupported by the current
liboeffis binding and are never persisted.

The default libei session runs in a dedicated helper process. Private JSON
IPC is limited to 64 KiB per message and 128 events per batch. Input requests
have a 3-second budget; startup and authorization have a 38-second total
budget. Timeout, cancellation or helper death ends the connection and requires
explicit authorization retry; uncertain input is never replayed. Normal close
releases held keys/buttons on the same grant. After a crash the compositor
owns revoked-device cleanup. The Diagnostics stop/retry actions use this same
lifecycle. `LibeiBackend` remains the low-level in-process binding for native
verification; direct callers must own its process lifetime.

The GUI and `AC_diagnose` use passive checks; `AC_diagnose include_active=true`
requests capture/cursor checks. Python retains active diagnostics by default:
use `run_diagnostics(include_active=False)` for passive checks. These local
features require no paid API or API key.


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

Executor action journals need no global input hook. The experimental Wayland
`PhysicalRecorder` helper reads explicitly selected physical `/dev/input/event*`
nodes using existing read permissions, excluding kernel virtual/uinput devices.
It returns raw device events, not desktop coordinates or replay actions, and
never changes ACLs. `StopShortcutSession` explicitly requests a portal stop
binding, reports its actual trigger, and closes its own grant; refusal is cached
until explicit close/start. Loss or replacement of the portal owner revokes pending
and active grants; active revocation signals the owned stop callback. Beta `je_auto_control.api.wayland_input` and the legacy facade expose these
helpers and five script operations: `start_physical_recording(devices)`,
`stop_physical_recording()`, `start_wayland_stop_shortcut(preferred_trigger='F7')`,
`stop_wayland_stop_shortcut()` and `wayland_input_status()`. Each has an `AC_*`
command, lowercase MCP tool and Script Builder schema. Raw stop results are
masked in action journals. Remote RBAC requires host administration for all five
operations. Diagnostics provides explicit Actions, JSON device-path input,
preferred trigger, actual binding/status and raw results. Each panel owns its
resources independently from script defaults. The stop binding stops native
input control and sets the owner's cooperative `stop_event`; it does not
interrupt arbitrary Python work. Native desktop acceptance remains in D3/H3.
Stop and explicit reset cancel pending native authorization without waiting for its cache lock; cancelled grants cannot be published later.
The legacy Wayland global recording hook remains unavailable. Window
management works on Windows, macOS (pyobjc) and X11, including XWayland; on a pure
Wayland session, whose protocol hides other clients' windows, `list_windows()` returns
an empty list and every window action raises `AutoControlUnsupportedOperationException`
saying why. Opt-in driver-level backends (`JE_AUTOCONTROL_WIN32_BACKEND=interception`,
`JE_AUTOCONTROL_LINUX_BACKEND=uinput`, ViGEm virtual gamepad) exist for apps that
ignore synthetic input, and fall back silently when the driver is absent.

---

## Documentation and examples

| Resource | What's in it |
|---|---|
| [`examples/`](examples/) | 31 self-contained scripts: screenshot + click, OCR, scheduler, remote desktop, agent loop, observability, recording, variables, hotkeys, triggers, reports, MCP, REST, secrets, plugins, computer use, Wayland, cross-host DAGs, chat-ops, pytest/BDD, anchor locators. |
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

Linux/macOS Python 3.10 quality jobs retain `native-diagnostics` artifacts
from gdb/lldb, including native frames, package versions and target exit status.
The original coverage command and assertions still run; diagnostic collection
does not establish the intermittent USB ACL crash root cause.
LLDB ignores launcher exec stops; other nonfatal stops fail without a fabricated crash exit code.
Both debuggers pass SIGINT to Python so emergency-stop assertions execute normally.
Quality tests install WebRTC/signaling extras and the HTTP test client.
GUI translation registries retain child wrappers and hold their own widget via
a weak proxy, avoiding self-cycles that defer GUI destruction to worker GC.

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

Docker CI accepts the manual `d3-native` scope for the sway, EIS, portal, seat and
uinput checks. The seat/uinput images verify an installed wheel rejects real
ydotool kernel devices before opening them, with no recorded events or leaked
descriptors. Native failure logs remain available for 14 days. See
[Wayland acceptance](docs/WAYLAND_ACCEPTANCE.md) for commands and evidence limits.

Manual `quality.yml` runs accept `verification_scope=native-shortcut` to run
only the installed-wheel/private-bus check; the default runs all quality jobs.

Native shortcut transport verification uses independent GDBus, a private bus
and an installed wheel; it does not establish GNOME/KDE human consent or
physical keyboard-state recovery.

---

## License

[MIT License](LICENSE) © JE-Chen.
See [Third_Party_License.md](Third_Party_License.md) for the licenses of bundled and
optional third-party components.

- **Homepage**: https://github.com/Integration-Automation/AutoControlGUI
- **PyPI**: https://pypi.org/project/je_auto_control/
- **Documentation**: https://autocontrol.readthedocs.io/en/latest/

Action signatures use Ed25519 version-2 JSON sidecars. Create keys with
`je_auto_control signing-keygen --private-key private.pem --public-key public.pem`,
sign with `je_auto_control sign flow.json --private-key private.pem`, and verify
with `je_auto_control verify flow.json --public-key public.pem`. Execution hosts
receive only the public key: set `JE_AUTOCONTROL_SIGNING_PUBLIC_KEY` and
`JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS=1`. Keep private keys on the offline signer.
Verification never creates keys. Legacy HMAC requires explicit migration opt-in;
see the signing deployment example in the English/Chinese Sphinx feature guide.

MCP file arguments use semantic schema metadata: JSONPath, distribution names
and other text stay unchanged. Set `JE_AUTOCONTROL_MCP_ROOTS` to allowed roots
separated by the OS path separator (`;` on Windows, `:` on Unix). Client
`roots/list` narrows these roots by intersection, per connection. An empty root
list denies filesystem arguments; absent configuration preserves file access
until client roots arrive. This does not enable read-only mode automatically.
`env://` references from MCP are denied by default; allow exact names with
`JE_AUTOCONTROL_MCP_ALLOWED_ENV=PUBLIC_SETTING,BUILD_ID`. `file://` references use
the same roots. Local Python reference resolution remains unrestricted unless
you pass `policy=je_auto_control.PathPolicy(...)`.

TCP/WebSocket viewers receive files inside `~/Downloads/AutoControl` by default;
override locally with `JE_AUTOCONTROL_DOWNLOAD_DIR`. Hosts must send relative
destinations such as `reports/result.txt`; absolute, drive/UNC, traversal and
symlink escapes are rejected. An explicit `FileReceiver(base_dir=Path(...))`
selects another bounded root. Host receivers retain their existing behavior.

Screen regions use global input coordinates, including negative monitor origins.
Fresh Windows processes request per-monitor DPI v2 before GUI initialization;
re-record coordinates and templates captured under the old system-DPI policy
on scaled secondary displays. An embedding host retains its existing DPI policy.
macOS captures normalize each display to points before stitching; primary and
region screenshots also use points, including older Pillow releases.
Set-of-Marks legends keep global points and return the captured `origin`.

Anthropic Agent histories stay append-only until the screenshot limit (three).
Above it, a new conversation contains the goal, completed action count, the
latest fifty actions with outcomes, and the newest screenshot. Previously sent
messages and signed thinking blocks are retained unchanged in their original
request. This applies to regular tools, beta computer-use and the GA toolset.
`AC_run_agent` retains its existing default tool export. Paid API validation
requires a configured key and remains tracked in `Progress.md`.


Individual REST/MCP identities are opt-in: create a `UserStore(Path("users.json"))`,
add users with roles `viewer`, `operator` or `admin`, then set
`JE_AUTOCONTROL_USERS` to that file before starting the servers or GUI. Viewers
observe the screen; operators also drive input and sequential action scripts;
admins additionally manage users, hosts, files, signing, audit and background work.
Discovery and calls enforce the same policy, including nested executor commands.
Without this variable, existing shared-token authentication remains available;
an empty or unreadable configured store denies access. HTTP MCP sessions belong
to the authenticated user, and audit entries identify `user_id`.

Admin Console exposes refresh/add/remove/role/token actions in the Actions menu,
using the same store as local servers. The facade exports `rbac_*` adapters and
`UserStore`; JSON/Script Builder commands are `AC_user_add`, `AC_user_list`,
`AC_user_remove`, `AC_user_set_role`, `AC_user_rotate_token` (equivalent lowercase
MCP names). Supply command tokens with `${secrets.USER_TOKEN}`; results contain
metadata only. Local GUI-generated tokens are shown once for saving.


Crypto dependencies require `cryptography>=50.0.0` (lock: 50.0.2). Windows arm64
keeps its optional markers because upstream still offers no compatible safe
wheel; Intel Mac requires a source build. See [the installation matrix](docs/CAPABILITY_MATRIX.md).
Missing crypto features raise facade-exported `CryptoDependencyError`:
`CryptoUnavailableError` retains RuntimeError compatibility and `CryptoImportError`
retains ImportError compatibility. Messages include installation instructions;
noncrypto automation and Qt-free imports remain available.

## Window lifecycle and saved layouts

`focus_window` confirms the actual foreground window and raises
`AutoControlActionException` when focus is refused. `wait_for_window` bounds each
sleep by the remaining timeout, including an infinite poll value. Windows
listing skips DWM-cloaked and empty windows. Printable posted text uses character
messages once; control keys use paired key messages with scan/release flags;
`enter` and `esc` aliases are accepted.

`capture_window` reads visible bounds without moving or restoring the window.
New Windows `save_window_layout` snapshots include native placement and show
state; `restore_window_layout` replays these without border drift, preserving
maximized/minimized state. Legacy geometry-only JSON remains readable; save a
new snapshot to gain placement preservation. Injected geometry/movers retain
their geometry-only contract. Snap/grid/cascade use the primary work area,
including its offset, excluding the taskbar. macOS handle-based restore queries
offscreen windows and still requires Accessibility permission.

## Keyboard correctness and confidential typing

`write("Hi\r\nthere")` preserves case and sends one Enter for CRLF. Windows
prefers Unicode injection for literal characters; explicit `is_shift=True`
holds and releases Shift on Windows/X11 as well as macOS. Keyboard shortcuts
accept Windows OEM names such as `plus`, `minus`, `comma`, `period` and `slash`.
`type_unicode_keys` sends newline/Tab/backspace as control keys. Layout tables
include regional OEM keys and return `None` for an untranslatable Shift half.

Use `ac.write_secret(secret)` or `ac.write(text, secret=True)` for confidential
typing. These calls return `None` and suppress input logs and recordings;
backend failure diagnostics are replaced by a generic typed error. Scripts use
`["AC_write_secret", {"secret": "${secrets.LOGIN}"}]`; MCP exposes
`ac_write_secret(secret=...)`. Script Builder hides the secret field; save a
secret reference because action files still contain the supplied arguments.
Executor callbacks receive a redacted copy, and records redact secret typing
in keyword and positional forms. WebRunner's `WR_ac_basic_auth` already uses
this `secret` parameter contract.

`mouse_scroll` now defaults to `scroll_up`, so positive values scroll up on
every platform. X11 scripts relying on the old downward default should pass
`scroll_direction="scroll_down"`. Coordinate conversion uses `int(round(value))`
and rejects NaN/infinity before moving, including scroll targets. Clipboard
format descriptors normalize a missing name to an empty string.

Other regional keys use physical names `oem_1` through `oem_8` and `oem_102`,
which do not promise a literal character on every layout.

## Image and OCR boundaries

Image matching reads file bytes before decoding, so non-ASCII paths work on
Windows. Two-dimensional arrays and Pillow `L` templates stay grayscale;
decode/matching failures raise `ImageNotFoundException`. Empty/corrupt image
files retain `read_image`'s documented `ValueError` contract. OCR keeps a long
left box when a phrase starts within it and finishes in the next box.

Image and click centres use integer floor division, including negative screen
coordinates. Region captures reject empty/nonfinite rectangles and intersect
the desktop instead of filling outside pixels with black. `grab_logical`
returns the clipped top-left origin; matching and OCR add that actual origin.
Windows, macOS global points and Linux region screenshots share this behavior.
When desktop bounds are unavailable, the captured frame provides the bounds.

Jeffrey_RPA's existing slash rejection test needs the approved new OEM shortcut
contract. The portable test migration is in
`docs/compatibility/jeffrey-rpa-oem-test-migration.patch`; validation uses a copied
test suite against the current consumer code. Apply it when integrating this
branch after the live editable batch stops.

Remote execution uses an explicit server-owned capability catalog. Unknown
commands require admin regardless of provider `readOnly` hints; saving a screenshot
to a file also requires admin access. Nested, loaded and flow-block actions check
declared filesystem paths after interpolation and positional/default binding.
Parallel and deferred work retain the caller's identity and allowed roots;
each remote request and deferred delivery has independent script variables.
Configured signing and encryption keys must also lie within the effective roots,
or use an explicit in-memory key. Local calls without a policy retain existing behavior.
Color/HSV and VLM results use the actual clipped capture origin. Windows restore
accepts a minimized window returning to its previous maximized state.

## Structured action journals (Beta)

Use the typed `je_auto_control.api.journal` entry point to record actions and
read selected runs. The same three operations are available through the facade,
`AC_execute_journaled`, `AC_read_action_journal`, `AC_list_journal_runs`, MCP
and Script Builder. Run History offers recording and read-only preview in Actions.

```python
from je_auto_control.api.journal import execute_journaled, read_action_journal
run = execute_journaled([["AC_sleep", {"seconds": 0}]], "actions.jsonl", run_id="demo")
events = read_action_journal("actions.jsonl", run_id=run["run_id"])
```

Schema version 1 stores separate inputs and outcomes, run/step/parent IDs, source
file paths and step indices. Start and terminal records are appended under a
shared run lock; reads retain start order and materialize each step's latest
status. Interrupted steps remain `incomplete`. Exact `${secrets.NAME}` input
references survive; secret literals are masked before logging or append and
marked non-replayable. Unknown payload objects are omitted with reasons, without
calling their repr/str hooks during journal serialization.

For explicit recording around an executor call, use `with ActionJournal(path).run()`.
Set `JE_AUTOCONTROL_ACTION_JOURNAL` to enable automatic executor recording; without
it, existing calls keep their behavior. Reads and previews never execute actions.
Journal paths and their lock files follow the effective filesystem policy.

## Fixed-frame self-healing comparison (Beta)

Use `je_auto_control.api.healing` to compare locator versions on identical saved
frames with labelled boxes, expected misses, origins and pixel/logical scales.
```python
from je_auto_control.api.healing import compare_healing_versions
report = compare_healing_versions("benchmarks/self_healing/dataset.json", {
    "before": {"template_path": "benchmarks/self_healing/before.png"},
    "after": {"template_path": "benchmarks/self_healing/after.png"}},
    report_path=".test-tmp/healing-report.json")
```

JSON and HTML reports retain frame hashes, expected geometry and original run/step
context. Counts include image hits, VLM attempts, misses, errors and unknown labels.
Accuracy, false-positive and recovery rates include numerators/denominators;
p50/p95 use linear interpolation over all attempts. Costs remain unknown when
unavailable. Unlabelled samples never count as correct; wrong VLM guesses never
count as recovery. Historical operation verification is separate from detection
and is not attributed to a newly compared version.

`create_template_candidate`, `preview_template_candidate`,
`validate_template_candidate`, `accept_template_candidate` and
`revert_template_revision` provide immutable snapshots and explicit review.
Acceptance requires perfect labelled validation with a positive hit and no
errors/false positives, plus an unchanged baseline/candidate hash. Preview never
applies changes; revert checks that the accepted image remains current.

All six operations have matching `AC_*`, MCP and Script Builder entries.
Self-Healing's Actions menu runs comparisons/revision work in a scoped worker;
the panel shows metric/failure tables, original steps and baseline/candidate
thumbnails. Runtime HealEvent schema 2 retains actual capture identities,
strategy timings, backend/model and journal IDs; legacy schema 1 remains readable.
Unavailable evidence remains unknown. The committed synthetic benchmark is
offline evidence; physical-device and paid-model validation remain separate.

## Journal candidate code generation (Beta)

Generate a selected-run candidate through `je_auto_control.api.codegen`:
```python
from pathlib import Path
from je_auto_control.api.codegen import generate_candidate_from_log
candidate = generate_candidate_from_log(Path("benchmarks/journal_codegen/actions.jsonl"), run_id="demo")
print(candidate.code, candidate.manifest, candidate.warnings)
```

Generation validates one journal snapshot and preserves its content hash, all
step/parent/source identities, statuses and observed retry occurrences. Only
completed replayable leaf actions are rendered with the existing code generator.
Failed, interrupted and masked steps remain in the manifest and warnings.
Exact `${secrets.NAME}` references survive; literal secrets and outcomes are not
turned into replay inputs. No input repr is evaluated and no result is executed.

Candidates are explicitly **observed path only** and serial in start order;
they do not reconstruct original branch/loop/retry/parallel semantics. Validate
installed command names, required Python arguments and executor dry-run; Python
targets also pass AST validation. Robot's Python AST result is not applicable.
Review the candidate before executing or extending it.
```powershell
python -m je_auto_control.cli codegen --from-log benchmarks/journal_codegen/actions.jsonl --run-id demo -o .test-tmp/test_observed.py
```

`-o` saves source plus `.manifest.json` and `.actions.json` sidecars; output
cannot replace the input journal. Without it, CLI emits source to stdout and
warnings to stderr. Existing target/style/name/failure-bundle flags remain usable;
journal mode defaults to `actions`, ordinary action-file mode retains `calls`.
`generate_journal_candidate`, `AC_generate_journal_candidate` and
`ac_generate_journal_candidate` return the same structured JSON artifact.

Recording Editor and Script Builder expose candidate review in Actions. Preview
shows a sanitized diff, source and provenance in a readonly view using a scoped
worker. Import is a separate editing operation; export saves the reviewed
candidate and sidecars. Neither preview nor import runs generated actions.
The synthetic `benchmarks/journal_codegen` example is offline contract evidence.

Ordinary `${var}` inputs without recorded resolved bindings are omitted with
a warning; they cannot silently reuse a new executor's variables. Validation
also checks block command objects and required fields. Journal recording binds
positional sensitive parameters, masks sensitive variable getter results and
marks unhandled descendant failures as errors. Successfully caught/retried
failures retain successful container/run status.
Interpolated variable names are conservatively private before recording.
Known private scalar values, including numeric PINs, are masked in result/log copies.

## Persistent config server (Beta)

The signaling service keeps config buckets in SQLite across restarts. Set
`--config-store PATH` or `AC_CONFIG_STORE_PATH`; otherwise the database path
is resolved on first use under `~/.je_auto_control/config_sync.sqlite`.
Importing the API or constructing an app creates no database.

`PUT /config/{user_id}` requires a version-2 envelope with `schema_version: 2`,
`base_revision`, `operation_id` and `bucket`. The server checks and writes in
one transaction. GET reports the committed `revision` and `cas_supported: true`.
Stale writes return HTTP 409; an identical operation retry returns the original
revision without replacing later data. Reusing its ID with different data is an error.
Accounts, shared-secret authentication and body/user limits remain enforced.
Browser preflight supports PUT. Pending WebRTC rendezvous sessions retain their TTL.

`je_auto_control.api.config_sync` exports `ConfigStore`, `ConfigBucket`,
`ConfigSyncError`, `ConfigRevisionConflict` and `ConfigStoreCapacityError`.
ConfigSyncClient defaults to protected causal synchronization and a durable outbox.
Explicit `SyncClientOptions(legacy_writes=True)` also requires the server's
`--allow-legacy-config-writes` migration option. The Config Sync tab uses the shared protected services.

## Causal sync and offline retries (Beta)

Use `causal_upsert`/`causal_remove` with the client's stable `device_id` to edit
definitions. `SyncEntry` carries version vectors, origin and operation ID;
`merge_entries` keeps concurrent alternatives rather than selecting by wall clock.
`ConfigBucket.entries()` excludes unresolved conflicts and tombstones. Explicit
causal edits can resolve a conflict after review. Legacy timestamp helpers remain available.

`ConfigSyncClient.sync()` refetches and merges after a confirmed HTTP 409, with
bounded CAS retries. Its SQLite `SyncOutbox` persists exact envelopes by endpoint
and account; uncertain success retries the original operation ID after restart.
Authentication remains in memory. Pending, conflict and exhausted-retry data is retained.
`retry_pending(cancel=...)` uses bounded backoff and checks cancellation between sends.
`close()` releases the database without losing queued data.

The shared `__sync_devices__` registry records acknowledgements and retirement.
New deletions get a committed revision only in their CAS envelope; collection
requires every known active device to acknowledge that revision, never elapsed days.
Retired or unresolved registration state blocks incremental sync and push;
`full_resync()` explicitly fetches a complete protected snapshot before rejoining.
Pending operations require review before full resync. `retire_device()` is explicit.
Local `SyncOutbox` peer methods preserve retirement across restart.
These are controlled SQLite/HTTP tests; physical multi-machine checks remain pending.

## Definition and asset synchronization (Beta)

The Config Sync tab and six `AC_config_sync_*` / `ac_config_sync_*` tools share
headless services for preview, protected exchange, explicit apply, durable retry,
local status and checked assets. The Script Builder exposes the same operations.
The panel shows committed revision, pending count, retained conflicts, offline
state and CAS protection. Actions menu operations use owned workers; cancellation
checks between operations and closes the client after the current bounded request.

Local definition JSON maps `scripts`, `locators`, `hotkeys`, `triggers` and
`address_book` to identifier/object mappings. Portable adapters retain causal
identities across unchanged snapshots; their optional state mapping must be
persisted when rebuilding an adapter. The file service keeps this state under
an explicit workspace, isolated by account and normalized server endpoint.
Named confidential fields, signature-bound action arguments, known secret echoes,
credential URLs and absolute machine paths become `{"$local": "/field/path"}`
references. Exact `${secrets.NAME}` references stay unresolved for local execution.
Missing destination-local references remain unresolved. Opaque Python/source files
and arbitrary unclassified literals are outside this structured privacy contract.

Preview and exchange preserve all causal alternatives and do not apply local
definitions. Apply requires the original file hash; optional `choices` explicitly
selects an index from each `sync_conflict` array, e.g. `{"locators/button": 0}`.
A resolved edit advances after all known alternatives. Incoming hotkeys/triggers
are disabled before registration and are excluded from active listener snapshots.
Receiving definitions never starts listeners, engines, connections or scripts.

Asset manifests list `path`, `sha256` and `size`. `config_sync_assets` receives
from an explicit source root; Python `sync_assets` supports streaming transports.
Each file is bounded to 256 MiB, rejects traversal, symlinks and Windows redirected
names, and replaces its destination only after exact size/hash verification.
Cancellation, corruption and disconnect remove only owned temporary files;
earlier completed files remain published. Definitions declaring `assets` apply
only after those files verify beneath the definition file's directory. Asset bytes
are stored as data; integrity verification does not classify their contents.

Folder mirroring remains additive: content identities detect edits even with
unchanged mtimes, two consecutive stable observations precede transfer, failed
sends retry, and received identities are not echoed. Stop retains ownership of
a sender still draining. TCP clipboard sessions carry bounded origin/event/hash
deduplication and suppress a received value's next outgoing echo; legacy envelopes
remain readable. Evidence uses controlled HTTP/SQLite, files and offscreen Qt;
physical multi-machine validation remains pending.

## Owned remote connections (Beta)

Each Remote Desktop panel owns independent host/viewer sessions for TCP,
WebSocket and WebRTC. Connecting or closing one panel preserves other panels
and scripts. Callbacks retain request authorization and session generation;
queued frames, status, transfers and signaling results from ended sessions are
dropped. Panel destruction stops owned transports and WebRTC background work;
failed transport cleanup remains in the registry for explicit retry.

All 24 transport commands accept keyword-only `session_id`. Omission selects
the script default for that transport and role; starting a new default replaces
only that default. An explicit ID allocates a fresh named connection without
changing defaults; retained allocated IDs cannot be reused. Existing seven TCP
MCP tools accept the same ID; 17 WebSocket/WebRTC and three lifecycle tools are
also available. Script Builder edits input objects and regions as finite JSON.

`je_auto_control.api.remote_sessions` exports immutable `RemoteSession`,
`SessionStatus` (the same snapshot type), `SessionEvent`, typed errors,
`get_remote_session`, `disconnect_session` and `list_remote_session_events`.
AC/MCP JSON operations are `AC_remote_session_status`,
`AC_remote_disconnect_session`, `AC_remote_session_events` and their lowercase
tool names. Optional `owner` checks identity; remote authorization still requires
`MANAGE_HOSTS`. Events retain at most 1,024 records; closed history retains 256
non-default sessions. Events/status contain no credentials or resource objects.

Session `active` describes successful local allocation; WebRTC peer readiness
uses transport status (`authenticated`, `state`). GUI multi-viewer host status
additionally includes `peers` and `connected_clients`. Sessions/events are
process-local and are not persisted configuration-sync records. Calling
`disconnect_session(id, owner=...)` affects only that connection. Controlled
transport doubles and offscreen Qt verify ownership; physical multi-machine
validation remains pending.

## Sync recovery and delayed Apply (Beta)

Exchange saves unsent local publication intent before its first network request.
Retry first merges a fresh protected snapshot before turning that intent into a
CAS envelope. Preview and requests cancelled before starting do not queue intent.
An uncertain dispatched envelope keeps its exact ID and payload. Explicit Retry
renews exhausted delivery attempts; a server-confirmed HTTP 409 can be causally
rebased and atomically replaced. A tentative deletion receipt from a rejected
write is reassigned to the new CAS revision. Incoming privacy validation runs
again before each fresh rebase. Local status includes `recovery` state counts;
Exchange reports `recovery_required` separately from a network outage.

Exchange and Retry leave local definitions unchanged. Receiving a preview does
not acknowledge applying it: `applied_revision` advances only after explicit
Apply resolves every entry and required asset/reference. The next Exchange
publishes that acknowledgement. Unresolved entries retain deletion obligations,
so delayed Apply cannot revive collected data. Direct causal clients default to
acknowledging the returned snapshot; adapters use
`SyncClientOptions(acknowledge_on_sync=False)` for explicit local application.
Only receipt metadata of the same causal deletion is reconciled; independent
edits and different JSON values still require conflict review.

Quick Connect checks session generation at final frame/error/cursor delivery.
WebRTC video toggles retain the same guard, and stop, replacement or successful
authentication revoke scheduled reconnects. Folder Sync retains a still-draining
sender and delays restart until it stops. Legacy clipboard repetition is
suppressed only across contiguous equal content, allowing A→B→A; modern event
IDs still use bounded deduplication and one received echo is suppressed.
These are controlled SQLite/network-boundary and offscreen Qt regressions;
physical multi-machine checks remain pending.

### Mobile app lifecycle and optional adapters

`launch_app`, `wait_for_app`, `app_state`, `stop_app` and `handle_mobile_alert`
use an explicit session and return observed state, with bounded requests and
cancellable polling. iOS app operations create a WDA session ID and delete only
that ID; deletion can terminate its app. Android connection close leaves apps
running; use `stop_app` explicitly. Failed cleanup remains retryable on `close()`.
`MobileExtensionSpec` configures a lazy factory for one owner using passive
capability metadata. Android includes APK install, push/pull and SDK Unicode
clipboard. iOS install/files/clipboard and recording on either platform require
an owned `MobileExtension`; absence reports `needs_dependency` with recovery.
`mobile_app`, `mobile_alert`, `mobile_extension_action` share AC/MCP/Builder and
Device Matrix Actions. Extension options/results are masked in journals.
[App example](examples/mobile_app_lifecycle.py) is passive until `--run`.
Native emulator/WDA authorization and recovery remain H3 acceptance.

WDA app operations require a dedicated idle endpoint: bounded status preflight rejects an existing/unknown session, and a local lease prevents concurrent owners for the same URL. External clients and endpoint aliases cannot be excluded atomically by WDA; keep this endpoint exclusive.

### Mobile workspace and native smoke

The Mobile devices tab keeps one explicit owner across app, capture and input operations.
Choose platform, serial/WDA URL and timeout, then use Actions → Open device owner.
Inspect dependencies is passive; Check connection / authorization explicitly sends get-state
or WDA GET /status. Run selected operation uses the same 13-operation catalog as
`AC_android_mobile_action` / `AC_ios_mobile_action`, MCP and Builder enums.
Run mobile actions accepts a validated flat device-only batch; Close device owner revokes
input immediately and cleans resources in the background. `mobile_surface_matrix()` inventories
all executor commands and gives device alternatives for host-only operations. Sensitive device
extension results are masked in automatic logs; explicit callers still receive their results.

Install optional SDKs with `python -m pip install uiautomator2==3.7.0 facebook-wda==1.5.4`;
Android also needs Android SDK platform-tools and USB debugging/RSA authorization.
iOS needs a signed WebDriverAgentRunner on an Apple host/device, Developer Mode and
an exclusive idle WDA endpoint. See the [mobile setup guide](docs/MOBILE_SETUP.md).
`python examples/mobile_device_smoke.py --validate` is hardware-free. `--connect` opts
into diagnostics; `--exercise --app-id ...` additionally launches, captures and stops the
named disposable app. Android 14 Docker/KVM configuration and a manual native CI workflow
are included. Configured smoke and controlled tests are distinct from real device evidence.

### Lazy GUI panels

Startup constructs Record, Script Builder and Remote Desktop. The complete 50-tab
catalog stays available through View → Tabs; other features import and construct
only when opened. Actions bind after construction. The legacy `show_tab`, `hide_tab`
and `list_registered_tabs` APIs remain available: hide preserves entered data;
the tab close button and `close_tab` release the panel and its subscriptions.
Reopening a closed panel creates a fresh widget with the same key. Language/engine
refresh only touches constructed panels. Missing optional dependencies show a
recovery view. GUI factories run on the GUI thread; headless registry metadata
imports neither Qt nor feature modules.

### Searchable workspace and themes

The left navigation searches all 50 feature keys, translated titles and English
aliases without opening panels. Ctrl+K focuses search; Enter opens the first match.
The middle workspace retains the legacy tabs and Actions menu. The right execution
details show explicitly reported state/reason/recovery/progress; workspace ready
does not assert native permission. Ctrl+Shift+D or View toggles details. Below
900 logical pixels the details collapse by default; wide content remains accessible
through scrollbars. View → Theme selects light/dark; Text Size and all four
languages preserve search and panel inputs. Themes use system fonts and native Qt
icons. [Qt layout captures](benchmarks/results/gui-workspace-f2/report.json) record
offscreen conditions; they do not establish native device or mixed-DPI behavior.
