# Workspace and headless workflow guide

Use Python 3.10 or newer in an isolated environment. Install `pip install -e .`
for headless use or `pip install -e '.[gui,webrtc,signaling]'` for GUI, remote
desktop and protected configuration transport. Mobile setup and SDK installation
are documented in [MOBILE_SETUP.md](MOBILE_SETUP.md). Importing the facade does
not load Qt, connect a device or start a server.

## First run and permission recovery

Run `python examples/28_wayland_diagnostics.py --validate` to inspect passive
capability metadata. `input`, `capture` and `restore_token` are separate results.
An available backend does not prove desktop permission. On Wayland, obtain portal
consent when starting the real operation; rejection, timeout or a revoked restore
token requires the reported recovery step and renewed consent. Never treat a
fallback or skipped backend as successful input. On macOS, allow the requested
Accessibility and Screen Recording permissions in system settings. Mixed DPI and
Retina require checking actual capture coordinates on the selected display.

Launch the workspace with
`python -c "import je_auto_control as ac; ac.start_autocontrol_gui()"`.
Search navigation with Ctrl+K, open a panel, fill its inputs and use Actions.
View controls theme, text size and details. Hiding retains entered state; closing
reclaims the panel. Missing dependencies display installation/recovery guidance.
Task cancellation is cooperative; owner cleanup reports failures and permits retry.
Closing one panel must not stop an unrelated panel or a global service.

## Six reproducible examples

Each script below accepts `--validate`. Validation uses passive metadata or
temporary fixtures and does not send desktop input, connect a mobile SDK or use
network services. It may write disposable temporary files.

| Script | Validation | Explicit real-data operation |
| --- | --- | --- |
| `28_wayland_diagnostics.py` | Passive host metadata | `--display-server wayland` remains passive |
| `29_config_sync.py` | Commit/reopen/retry in temporary SQLite | `--state example.sqlite` persists an example bucket |
| `30_mobile_devices.py` | Owned device context and passive setup | `--platform android --target SERIAL --capture phone.png` |
| `31_healing_comparison.py` | Two fixed predictions on identical bytes | `--dataset DATASET --versions VERSIONS_JSON` |
| `32_codegen_from_log.py` | Generate and compile a disposable fixture | `--journal events.jsonl --run-id RUN --target pytest` |
| `33_mcp_progressive.py` | Search/schema/enable/list in a local view | `--query screenshot` still invokes no tools |

Run from the repository root, for example
`python examples/32_codegen_from_log.py --validate`. Validation rejects persistent
state, device capture, a supplied dataset or journal when these would replace its
controlled fixtures. Persistent store writes use an operation ID for idempotent
retry; a changed write needs its own ID and current base revision. Network sync
requires configured identities, transport and authorization. Received executable
definitions remain disabled until reviewed; do not resolve conflicts by blindly
overwriting local changes. See [configuration lifecycle](API_LIFECYCLE.md).

Android capture needs a reachable explicit serial and installed SDKs. iOS needs
an already provisioned WDA endpoint on an Apple host; use `--platform ios --target
http://HOST:8100 --capture phone.png`. Keep App session endpoints exclusive to their
owner. Passive setup does not prove focus, Unicode typing, clipboard/IME recovery
or continuity after SDK capture. See [MOBILE_SETUP.md](MOBILE_SETUP.md).

Healing datasets must contain labelled saved frames; comparisons reuse those
bytes. A successful location score is separate from verified operation success.
Real version configuration uses the existing evaluation API; validation makes
no external model requests. See [evaluation lifecycle](API_LIFECYCLE.md).

Journal candidates preserve source-step provenance and warnings. Review the
candidate, manifest and differences before execution. Generation never executes
the candidate, and an observed path does not reconstruct unobserved branches.

## CLI and MCP deployment

Existing `-e`/`--execute_file`, `-d`, `-c` and `--execute_str` flags remain
compatible. Use existing action files for explicit execution; review their
contents before running them. To start progressive MCP:

```sh
python -m je_auto_control.utils.mcp_server --tool-mode progressive
```

Clients use `ac_discover_tools`, `ac_get_tool_schema`, `ac_enable_tools`, then
`tools/list`. Follow returned cursors only in their original live session.
Expired, foreign or revoked-permission cursors fail explicitly. Full mode remains
the default; a static profile fixes deployment availability. Local GUI previews
and example 33 do not mutate a remote MCP session. Selecting a tool does not grant
RBAC, path, environment, rate or native platform permission.

## Migration and acceptance

Legacy imports, facade aliases, JSON action files and default full MCP behavior
remain compatible. Version-one journals, evaluation datasets and candidate
manifests are explicit new formats; do not reinterpret old action JSON as these
formats. Keep existing applications on their own editable installation until
downstream integration is approved and their active processes have finished.

Container evidence covers native compositor/protocol behavior and the Android
emulator. It does not certify human consent interaction or physical keyboard
restoration. [CAPABILITY_MATRIX.md](CAPABILITY_MATRIX.md) distinguishes these
results; unresolved acceptance conditions remain in [Progress.md](../Progress.md).
