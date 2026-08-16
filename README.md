# AutoControl

[![PyPI](https://img.shields.io/pypi/v/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![Python](https://img.shields.io/pypi/pyversions/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Documentation](https://readthedocs.org/projects/autocontrol/badge/?version=latest)](https://autocontrol.readthedocs.io/en/latest/?badge=latest)

**AutoControl** is a cross-platform GUI automation framework for Python. It drives the
mouse and keyboard, finds things on screen (template matching, OCR, the OS accessibility
tree, or a vision model), records and replays flows, and runs them from JSON action
files — on Windows, macOS, Linux (X11 and Wayland), Android, and iOS.

Every capability ships three ways: a **Python API**, an **`AC_*` action command** usable
from JSON files / CLI / servers, and a **GUI tab**. Nothing is GUI-only.

**[繁體中文](README/README_zh-TW.md)** · **[简体中文](README/README_zh-CN.md)**

---

## Why AutoControl

- **One API, six platforms.** `wrapper/platform_wrapper.py` picks the backend at import
  time; your script does not change between Windows, macOS, X11, and Wayland.
- **Scriptable without Python.** 761 `AC_*` commands cover the whole feature set, so a
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
| `gui` | PySide6 desktop application (48 tabs) |
| `webrtc` | WebRTC remote desktop, USB passthrough (`aiortc`, `av`) |
| `signaling` | Standalone signaling / rendezvous server (`fastapi`, `uvicorn`) |
| `discovery` | mDNS / Zeroconf LAN host discovery |
| `pdf` / `office` | PDF and Excel / Word / PowerPoint reading |
| `fuzzy` / `locale` | `rapidfuzz` matching, `babel` locale parsing |
| `s3` / `audio` | S3 artifact store, system volume control |

**Requirements:** Python ≥ 3.10. On Linux, install build prerequisites first:

```bash
sudo apt-get install cmake libssl-dev
```

OCR, VLM, and LLM backends (`pytesseract`, `easyocr`, `paddleocr`, `anthropic`,
`openai`) are loaded on demand — install whichever you actually use.

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
python -m je_auto_control          # or: je_auto_control.start_autocontrol_gui()
```

Record a flow, edit it in the visual Script Builder, and save it as the same JSON
format the CLI runs.

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
| JSON scripting | `execute_action`, `execute_files` | all 761 commands | Script, Script Builder |
| Variables & flow control | `execute_action_with_vars` | `AC_set_var`, `AC_loop`, `AC_for_each`, `AC_try`, `AC_retry` | Variables |
| Data-driven runs | — | `AC_for_each_row` (CSV / JSON / SQLite / Excel) | Data Sources |
| Assertions | `assert_text`, `assert_image` | `AC_assert_text` + 20 more | Assertions |
| Test suites | `run_suite` | `AC_run_suite` | Test Suites |
| Scheduler (interval + cron) | `default_scheduler` | — | Scheduler |
| Global hotkeys | `default_hotkey_daemon` | — | Hotkeys |
| Event triggers | `default_trigger_engine` | `AC_email_trigger_add` | Triggers, Webhooks, Email |
| Window management *(Windows)* | `list_windows`, `focus_window` | `AC_focus_window`, `AC_snap_window` | Window Manager |
| Clipboard | `get_clipboard`, `set_clipboard` | `AC_clipboard_get`, `AC_clipboard_set` | — |
| Remote desktop | `RemoteDesktopHost`, `RemoteDesktopViewer` | `AC_start_remote_host`, `AC_remote_connect` | Remote Desktop |
| USB enumeration & passthrough | `list_usb_devices`, `enable_usb_passthrough` | `AC_usb_*` (16 commands) | USB Devices, USB Share |
| Secrets vault | `default_secret_manager` | `AC_secret_set` + `${secrets.NAME}` | Secrets |
| Reports (HTML / JSON / XML) | `generate_html_report` | `AC_generate_html_report` | Report |
| Run history | — | — | Run History |
| Metrics & tracing | `default_metric_registry`, `render_metrics_text` | — | — |
| Diagnostics | `run_diagnostics` | `AC_diagnose` | Diagnostics |
| Test-code generation | `generate_code` | — | — |

Beyond this table, `utils/` holds 308 headless packages covering assertions, resilience,
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
otherwise kept as a string. The legacy `python -m je_auto_control -e file.json`
entry point still works.

---

## Servers and integrations

| Surface | Start it with | Notes |
|---|---|---|
| **MCP server** | `je_auto_control_mcp` (stdio) or `AC_start_mcp_http_server` | 667 tools for Claude Desktop / Claude Code / custom tool loops. Bearer auth, TLS, audit log, rate limit, plugin hot-reload, CI fake backend. |
| **REST API** | `je_auto_control start-rest` | Bearer token, per-IP rate limit + lockout, SQLite audit hook, `/metrics`, `/openapi.json`, `/docs` Swagger UI, `/dashboard`. |
| **TCP socket server** | `je_auto_control start-server` | Newline-framed JSON action lists. Binds `127.0.0.1` by default. |
| **pytest plugin** | installed automatically | Fixtures plus a Gherkin step library for pytest-bdd / behave. |
| **Language server** | `python -m autocontrol_lsp.server` | Completion and diagnostics for `AC_*` action JSON, generated from the live command table. |
| **Remote desktop** | `RemoteDesktopHost` / GUI | TCP, WebSocket, or WebRTC; TOTP, trust list, TURN config, file/clipboard/audio sync. |

All servers bind to `127.0.0.1` unless you opt in explicitly.

---

## Platform support

| Platform | Backend | Input | Screen capture | Recording | Window management |
|---|---|:---:|:---:|:---:|:---:|
| Windows 10 / 11 | Win32 ctypes (+ optional Interception driver) | ✅ | ✅ | ✅ | ✅ |
| macOS 10.15+ | pyobjc / Quartz | ✅ | ✅ | ❌ | ❌ |
| Linux X11 | python-Xlib (+ optional `uinput`) | ✅ | ✅ | ✅ | ❌ |
| Linux Wayland | libei, or ydotool / wtype / grim | ✅ | ✅ | ❌ | ❌ |
| Android | adb + uiautomator2 | ✅ | ✅ | — | — |
| iOS | WebDriverAgent / facebook-wda | ✅ | ✅ | — | — |

Wayland forbids global input recording for unprivileged clients — set
`JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11` to record on an X11 session. Window
management is currently Windows-only and raises a clear `NotImplementedError`
elsewhere. Opt-in driver-level backends (`JE_AUTOCONTROL_WIN32_BACKEND=interception`,
`JE_AUTOCONTROL_LINUX_BACKEND=uinput`, ViGEm virtual gamepad) exist for apps that
ignore synthetic input, and fall back silently when the driver is absent.

---

## Documentation and examples

| Resource | What's in it |
|---|---|
| [`examples/`](examples/) | 27 self-contained scripts: screenshot + click, OCR, scheduler, remote desktop, agent loop, observability, recording, variables, hotkeys, triggers, reports, MCP, REST, secrets, plugins, computer use, Wayland, cross-host DAGs, chat-ops, pytest/BDD, anchor locators. |
| [Read the Docs](https://autocontrol.readthedocs.io/en/latest/) | Full API reference, English and 中文. |
| [architecture_explore.md](architecture_explore.md) | Every module's responsibility, layer by layer. |
| [docs/CAPABILITY_MATRIX.md](docs/CAPABILITY_MATRIX.md) | Capability × platform matrix. |
| [docs/API_LIFECYCLE.md](docs/API_LIFECYCLE.md) | Stable-API and deprecation policy. |
| [WHATS_NEW.md](WHATS_NEW.md) | Per-release notes. |
| [CHANGELOG.md](CHANGELOG.md) | Compatibility changelog. |
| [SECURITY.md](SECURITY.md) | Security policy and reporting. |

---

## Development

```bash
git clone https://github.com/Intergration-Automation-Testing/AutoControl.git
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

- **Homepage**: https://github.com/Intergration-Automation-Testing/AutoControl
- **PyPI**: https://pypi.org/project/je_auto_control/
- **Documentation**: https://autocontrol.readthedocs.io/en/latest/
