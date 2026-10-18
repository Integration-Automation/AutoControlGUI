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

## Running

[`29_mcp_journal.py`](29_mcp_journal.py) sends capture/read JSON-RPC requests to
an in-process MCP server with variable-only actions:

```bash
python examples/29_mcp_journal.py run.jsonl
```

[`28_action_journal.py`](28_action_journal.py) captures variable-only actions
through `AC_journal_capture` and prints sanitized snapshots with
`inspect_journal`; it sends no desktop input:

```bash
python examples/28_action_journal.py run.jsonl --run-id example
```

Each script is standalone and uses only the package facade
(`import je_auto_control as ac`). After `pip install -e .` from the
repo root:

```
python examples/01_screenshot_and_click.py
```

A few scripts have optional dependencies — the script comments
mention which `pip install` brings them in.

### Inspect journals in the GUI

Open Run History and use **Actions → Choose Journal** to select the JSONL file
produced by examples 28/29, then **Read Journal**. Existing history rows can
supply their provenance links through **Use Journals from Selected Run**.
Set a run ID and output limit, select snapshots for details, or cancel the read.

### 30. Explicit manual history

[`30_manual_history.py`](30_manual_history.py) records a variable-only run and
links its journal to a custom history database in the supplied directory.
Use `python examples/30_manual_history.py OUTPUT --validate` to check without
writing, or `--dry-run` to record a preview. Normal execution prints the history
ID, status, links and original action record. Configure allowed path roots for
an output directory outside the normal roots.

CLI `run SCRIPT --history` and the GUI's **Record in Run History** use the
default history store shown in Run History. `--history-db PATH` selects a custom
store for CLI/Python inspection; it does not switch the GUI's default store.
