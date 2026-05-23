# AutoControl examples

Small, self-contained scripts you can copy-paste and run. Each one
demonstrates a single feature end-to-end so you can see the minimal
glue between AutoControl's public API and your code.

| Script | What it shows |
| --- | --- |
| [`01_screenshot_and_click.py`](01_screenshot_and_click.py) | Take a screenshot, find an image on screen, click its center. |
| [`02_ocr_find_text.py`](02_ocr_find_text.py) | Locate on-screen text via the OCR engine and click it. |
| [`03_scheduler.py`](03_scheduler.py) | Run a recurring job from the headless scheduler. |
| [`04_remote_desktop.py`](04_remote_desktop.py) | Stand up a host and connect a viewer over WebSocket. |
| [`05_agent_loop.py`](05_agent_loop.py) | Drive a closed-loop AI agent against a deterministic fake backend. |
| [`06_observability.py`](06_observability.py) | Expose `/metrics` for Prometheus and add a span to user code. |
| [`07_json_action_file.py`](07_json_action_file.py) | Execute a JSON action file from Python and from the CLI. |

## Running

Each script is standalone and uses only the package facade
(`import je_auto_control`). After `pip install -e .` from the repo
root:

```
python examples/01_screenshot_and_click.py
```

A few scripts have optional dependencies — the script comments mention
which `pip install` brings them in.
