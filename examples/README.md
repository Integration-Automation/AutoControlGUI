# AutoControl examples

Small, self-contained scripts you can copy-paste and run. Each one
demonstrates a single feature end-to-end so you can see the minimal
glue between AutoControl's public API and your code.

## Core flows

| Script | What it shows |
| --- | --- |
| [`01_screenshot_and_click.py`](01_screenshot_and_click.py) | Take a screenshot, find an image on screen, click its center. |
| [`02_ocr_find_text.py`](02_ocr_find_text.py) | Locate on-screen text via the OCR engine and click it. |
| [`03_scheduler.py`](03_scheduler.py) | Run a recurring job from the headless scheduler. |
| [`04_remote_desktop.py`](04_remote_desktop.py) | Stand up a host and connect a viewer over TCP. |
| [`05_agent_loop.py`](05_agent_loop.py) | Drive a closed-loop AI agent against a deterministic fake backend. |
| [`06_observability.py`](06_observability.py) | Expose `/metrics` for Prometheus and add a span to user code. |
| [`07_json_action_file.py`](07_json_action_file.py) | Execute a JSON action file from Python and from the CLI. |

## Recording, scripting, and triggers

| Script | What it shows |
| --- | --- |
| [`08_record_and_replay.py`](08_record_and_replay.py) | Record real keyboard/mouse input, save it as JSON, replay later. |
| [`09_action_variables.py`](09_action_variables.py) | Substitute `${name}` placeholders into a JSON action list at run time. |
| [`10_window_management.py`](10_window_management.py) | Enumerate windows, focus by title, wait for one to appear. |
| [`11_hotkey_daemon.py`](11_hotkey_daemon.py) | Bind a global hotkey combo to a JSON action file. |
| [`12_image_trigger.py`](12_image_trigger.py) | Auto-run a script when a template image appears on screen. |

## Integration and operations

| Script | What it shows |
| --- | --- |
| [`13_html_report.py`](13_html_report.py) | Generate an HTML report from the in-memory test record. |
| [`14_mcp_stdio_server.py`](14_mcp_stdio_server.py) | Expose AutoControl to Claude Desktop / other MCP clients over stdio. |
| [`15_rest_api.py`](15_rest_api.py) | Start the REST API server and dispatch an action over HTTP. |
| [`16_secrets.py`](16_secrets.py) | Store and read credentials from the Fernet-encrypted secret vault. |
| [`17_plugin_loading.py`](17_plugin_loading.py) | Load extra `AC_*` commands from an external plugin file. |

## End-to-end pipeline

| Script | What it shows |
| --- | --- |
| [`18_slack_daily_report.py`](18_slack_daily_report.py) | Full daily workflow: pull Slack messages → Anthropic summary → HTML/PDF report → SMTP email, on a cron schedule. Every external service degrades to a stub so the script always runs to completion. |

## Locators, agents and other hosts

| Script | What it shows |
| --- | --- |
| [`19_self_healing_locator.py`](19_self_healing_locator.py) | Locate with an image template first and fall back to a VLM on a miss; read the heal log. |
| [`20_webrunner_bridge.py`](20_webrunner_bridge.py) | Drive WebRunner (browser automation) from an AutoControl script. |
| [`21_computer_use.py`](21_computer_use.py) | Drive Anthropic Computer-Use against the live screen. |
| [`22_wayland_backend.py`](22_wayland_backend.py) | Run on a Wayland session: backend selection and which helper programs are installed. |
| [`23_cross_host_dag.py`](23_cross_host_dag.py) | Orchestrate a DAG of automation steps across several AutoControl hosts. |
| [`24_multi_viewer_presence.py`](24_multi_viewer_presence.py) | Maintain a presence roster across several connected viewers. |
| [`25_chatops_bot.py`](25_chatops_bot.py) | Stand up a Slack chat-ops bot. |
| [`26_pytest_plugin_and_bdd.py`](26_pytest_plugin_and_bdd.py) | Drive AutoControl from pytest and pytest-bdd. |
| [`27_anchor_locator.py`](27_anchor_locator.py) | Compose locators with spatial relations ("Submit below the Username label"). |

## Platforms, sync and review tooling (each has `--validate`)

| Script | What it shows | `--validate` uses |
| --- | --- | --- |
| [`28_wayland_diagnostics.py`](28_wayland_diagnostics.py) | `probe_capabilities()`: which of input, capture, recording and the stop key work right now, through which backend, and what to do when one does not. | Four desktops described by hand; no probe of this machine. |
| [`29_config_sync.py`](29_config_sync.py) | Sync scripts and settings across machines: revision-checked writes, an offline queue, conflicts kept for a person to resolve. | Two machines, a temp-directory store, a stand-in server on 127.0.0.1. |
| [`30_mobile_devices.py`](30_mobile_devices.py) | Isolated Android / iOS device sessions: setup report, capture, gestures, typing, the capability matrix. | An offline `adb` transport; no device. |
| [`31_healing_comparison.py`](31_healing_comparison.py) | Score two versions of a locator on labelled frames: accuracy, false positives, recovery. | Frames drawn in memory. |
| [`32_codegen_from_log.py`](32_codegen_from_log.py) | Record a run in the action journal and turn it into a candidate script for review. | Variable and flow-control commands only; a temp journal. |
| [`33_mcp_progressive.py`](33_mcp_progressive.py) | Progressive MCP tool mode: start with five tools, search, read a schema, enable what is needed. | An in-process server; no desktop tool is called. |

`--validate` runs the real API against in-memory, temp-directory or loopback
stand-ins and exits 0 when what it saw matches what the script's docstring
says. It never moves the pointer, types, captures the screen, reaches a device
or leaves 127.0.0.1, and CI runs all six that way with every such seam replaced
by a tripwire (`test/unit_test/headless/test_modernization_examples.py`). It is
evidence about how the calls are wired, not about hardware. Without the flag
each script does the real thing, and anything that sends input or changes
this machine's settings sits behind an explicit option (`--tap`, `--run`).

## Running

Each script is standalone and uses the package facade
(`import je_auto_control as ac`); the few that also import a helper from a
submodule say why next to the import. After `pip install -e .` from the
repo root:

```
python examples/01_screenshot_and_click.py
```

```
python examples/29_config_sync.py --validate
```

A few scripts have optional dependencies — the script comments
mention which `pip install` brings them in.
