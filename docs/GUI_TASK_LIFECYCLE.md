# GUI task lifecycle and I/O audit

Actions → Cancel current task affects the selected panel and its children. Work
receives copied inputs, captured authorization/path policy, a cancellation Event
and a cooperative deadline. Typed completion checks the original owner/run/session;
Qt renders results and progress. Destroyed panels cannot receive late callbacks.
Legacy CallWorker binds the same nested cancellation/input scope with a 300-second
deadline; custom workers retain their explicit stop Events. No thread is force-killed.

Nested AC_sleep wakes on cancellation; new executor actions and desktop input
check the boundary. Device Matrix caps each device request by remaining time.
Native connection/signaling requests use bounded timeouts and cancellation waits.
A native call already in flight must return at its own backend boundary. Completed
file/vault/plugin/global-service mutations cannot be undone by dropping a result.
Global servers and engines continue until an explicit Stop; closing their control
panel does not revoke another caller's global service.

GUI recording owns an independent recorder or X11 subscription. It does not stop
the global recorder/listener. Raw key/button holds use a headless InputOwner shared
by that panel's workers. Known initially pressed input is borrowed; unknown state
refuses acquisition. Successful holds persist until explicit release/cancel/owner
destruction. Cleanup retains failures and captured request policy, and a cleanup
snapshot cannot release a later replacement hold. Cooperation between GUI owners
does not provide atomic isolation from physical users or other input clients.

Remote session generations revoke immediately on Qt. A per-session gate serializes
native allocation and close off Qt, so cleanup follows a late bounded connection.
Failed peers, shared capture and recorder containers stay retained for retry.
Folder Sync revokes its Event immediately and drains off Qt. Tools → Retry owned
cleanup retries only retained owned callbacks and recorders. Worker return, widget
deletion and a ready label do not prove physical state restoration.

## Catalog I/O inventory

This inventory covers the 50 catalog keys. Qt dialogs, editing, rendering, short
local configuration reads/writes and bounded metadata remain on Qt. It does not
claim every local filesystem operation is asynchronous. Slow device/network,
capture/recognition and explicit service drain operations use workers. Legacy
unbound test/embedding shims preserve their synchronous method contracts; actual
constructed panels use the owned worker paths.

| Keys | Execution / close boundary |
| --- | --- |
| `auto_click`, `screenshot`, `image_detect`, `record`, `script_builder`, `script`, `config_sync`, `secrets` | Shared task snapshots; cancel/close suppresses delivery. Timed clicking skips busy ticks. Capture/pixel reads run off Qt. Recording and raw input have independent ownership. Vault writes remain atomic global mutations. |
| `self_healing`, `ocr_reader`, `accessibility`, `live_hud`, `llm_planner`, `test_suite`, `assertions`, `data_source`, `a11y_audit` | Shared tasks for locate/click, OCR/tree queries, HUD sampling, planner/suite/QA/data work. HUD skips busy ticks and cancels while hidden. GUI renders typed outcomes. |
| `mobile`, `device_matrix`, `media_checks`, `window_manager`, `plugins`, `webrunner`, `chatops`, `diagnostics`, `report` | Shared tasks for SDK/device/media/window enumeration, plugin loading, browser/dispatch/diagnostics/report work. Matrix probe remains passive. Mobile close revokes its persistent native owner. Diagnostics stop/reset drains off Qt. |
| `remote_desktop` | Independent host/viewer tasks, immutable signaling/session identity, queued Qt rendering; generation revocation precedes retained off-Qt native cleanup. |
| `vlm`, `run_history`, `email_triggers`, `admin_console`, `usb_devices`, `usb_browser`, `usb_share` | Existing worker/relay paths now inherit CallWorker cancellation, request policy and raw-input ownership. Watchers retain their existing shared-holder rules. Long SDK/provider calls remain cooperative and bounded by their backend. |
| `computer_use`, `dag_runner` | Existing custom workers use explicit stop Events. Owner destruction requests stop; result callbacks remain GUI-owned. Paid/provider native acceptance is an open Progress item. |
| `scheduler`, `hotkeys`, `triggers`, `webhooks`, `rest_api` | Explicit global start/stop executes through shared tasks off Qt. Panel close cancels delivery and does not stop borrowed global services. Metadata/tables remain on Qt. Tools engine starts also run off Qt. |
| `flow_editor`, `recording_editor`, `variables`, `flakiness`, `profiler`, `trace_replay`, `presence`, `audit_log`, `inspector` | Local editing/history/trace rendering and bounded in-memory metadata; no model/device/network round trip in the normal view path. Qt image rendering/dialogs remain interactive GUI work. |

## Evidence and limits

Controlled offscreen tests cover event-loop ticks during slow work, GUI-thread
result/progress delivery, owner death, superseded runs, deadlines, nested waits,
borrowed Shift preservation, successful raw holds cleaned on owner death, independent
recording, retained failures and late native connection cleanup. Native loopback
TCP tests retain real frame delivery and operator approval/denial assertions while
awaiting asynchronous completion. The fixture tests do not inject physical input.

Physical key-state restoration, GNOME/KDE permission prompts, real Android/iOS
SDK cancellation, external WDA/input-client races, native codec content and mixed
DPI remain explicit H3 acceptance items in Progress.md. Docker native evidence is
recorded separately in the update log; it does not turn these controlled GUI
fixtures into physical-device evidence.

F4 reference frames and warmed same-environment latency results are retained in
`benchmarks/results/gui-workspace-f4/README.md`. The task renderer uses actual
AC_sleep, cancellation-after-return and invalid-JSON failure; it does not operate
native inputs or certify recording content/physical recovery.
