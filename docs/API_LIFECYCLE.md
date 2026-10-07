# Public API lifecycle

The supported entry point for new integrations is `je_auto_control.api`.

`je_auto_control.api.mobile` is Beta and exports `DeviceContext`, `DeviceSession`,
`DeviceSessionError`, `DeviceFrame`, `Gesture`, `open_device`, `probe_device_contexts`,
`mobile_capture`, `mobile_gesture` and `mobile_type_text`; the facade mirrors these names.
Frozen serial/endpoint/configuration and execution-local bindings
keep matrix workers independent. Existing mobile helpers outside a binding retain
their defaults; a closed or mismatched binding cannot fall back to another device.
`connected` means logical owner lifetime. Cancellation invalidates before cleanup,
rejects late results and reclaims only a helper started by that Android SDK client.
The root WDA client never deletes a borrowed server-side app session on close.
Per-request ADB/SDK timeouts do not change SDK globals; native bootstrap and retry
internals are not a verified total-operation deadline. The JSON probe is shared by
AC/MCP/Builder and the Device Matrix Actions menu; it performs no device I/O.
Remote probing requires MANAGE_HOSTS. Device Matrix executes on the shared GUI
worker, whose relay keeps owner-bound callbacks through weak references.
Session capture/gestures/Unicode and immutable-frame OCR/template/VLM use explicit
mobile ownership. Bound self-heal consumes one device frame and native points,
without desktop fallback. WDA touch/size legacy values are UIKit points; their
numeric ABI is preserved. ADB input text rejects non-ASCII; use SDK Unicode.
`AC_mobile_*`, MCP and Builder schemas share the JSON services; Device
Matrix Actions can run them. Remote mobile access requires MANAGE_HOSTS. Typed
failure retains its cause, text arguments are masked and responses omit text.
Native SDK IME/clipboard changes, device rotation after a snapshot and WDA W3C
support remain explicit physical acceptance cases. See the mobile guide and
Progress.md for native acceptance scope.

Everything reachable only through `je_auto_control.utils` is internal unless a
document explicitly says otherwise. The historical top-level package remains
available for compatibility. New integrations are defined in `api`; required
historical facade mirrors share those definitions.

- Stable API removal requires a deprecation warning and two minor releases.
- Beta API removal requires one release note and one minor release.
- Experimental API may change in any release and must be labelled as such.
- Deprecations state the version introduced, planned removal version, and
  replacement. Use `je_auto_control.utils.deprecation.deprecated`.
- Breaking changes and migrations are recorded in `CHANGELOG.md`.

The project remains pre-1.0. A 1.0 release requires passing stable capability
tests on every claimed platform, documented recovery/diagnostic behavior, and
no unresolved critical security advisories.

Remote RBAC uses a reviewed capability catalog, independent of provider hints.
Unknown commands require host administration. Filesystem metadata is checked at
every scoped executor dispatch, including nested scripts and flow blocks.
Internal `RequestBinding` preserves authorization, roots and variable snapshots
for deferred work; it adds no public command or facade API.

`je_auto_control.api.journal` is Beta (schema version 1). It exports
`ActionEvent`, `ActionJournal`, `JournalError`, `read_events`,
`execute_journaled`, `read_action_journal` and `list_journal_runs`.
The legacy facade re-exports these for JSON/GUI integration compatibility;
the stable `core.py` namespace is unchanged. Journal readers validate schema
and ordering and do not execute records.

`je_auto_control.api.healing` is Beta. It exports fixed-frame evaluation models,
`evaluate_locators`, `healing_context`, `TemplateRevisionStore` and six JSON
comparison/revision adapters. HealEvent writes schema 2 and reads schema 1.
Compared location correctness and original-operation verification are separate.
Existing `self_heal_locate`/`self_heal_click` imports and commands remain available.

`je_auto_control.api.codegen` is Beta. It exports `CandidateScript`,
`CandidateError`, `generate_candidate_from_log` and `generate_journal_candidate`.
Manifest schema 1 identifies the exact source snapshot and observed-only replay.
Existing list-based codegen and CLI flags remain supported. Generation validates
but never executes the candidate; masked/incomplete/failed steps are omitted
from replay inputs and retained as provenance and warnings.

Candidate replay excludes ordinary runtime variable references without recorded resolved binding evidence. Block fields are validated without dispatch. Journal privacy includes signature-bound positional values and sensitive getter results; unhandled contained errors propagate to terminal container status while handled errors remain distinguishable.

`je_auto_control.api.config_sync` is Beta. It exports ConfigStore, ConfigBucket, ConfigSyncError, ConfigRevisionConflict and ConfigStoreCapacityError. SQLite commit/get/close are lazy and Qt-free. Version-2 server writes require CAS and stable operation IDs; bare PUT requires explicit migration configuration. Historical facade re-exports match these names for integration compatibility.

Beta config_sync now also exports ConfigSyncClient/SyncClientOptions, SyncEntry/MergeDecision/merge_entries, PeerState/can_collect_tombstone, SyncOutbox/SyncOperation/OutboxReport and causal bucket helpers. Default client writes are protected; legacy timestamp merge and opt-in blind transport remain compatibility APIs. Causal wire metadata preserves operation/origin/vector/deletion revisions and unresolved alternatives.

Beta config_sync adds SyncAdapter/ApplyReport, five definition adapters, asset manifest/transport/result models and six shared sync operations. Python services accept cooperative cancellation; AC/MCP wire adapters expose JSON-only arguments. GUI and Script Builder use the same services. Historical facade exports are compatibility mirrors.

Beta remote_sessions exports immutable identities/status/events, typed errors and get/disconnect/events functions. AC/MCP add JSON lifecycle adapters and all transport commands accept keyword-only optional session_id; historical facade mirrors remain compatible. Omitted IDs use transport/role script defaults. GUI identities are independent. SessionStatus aliases RemoteSession; active is local allocation, not WebRTC peer authentication.

Beta config recovery now separates never-dispatched intent, exact uncertain writes and confirmed stale writes. Explicit Retry renews exhausted exact attempts and causally rebases stale envelopes atomically. Adapter acknowledgements advance only after resolved explicit Apply; status exposes applied_revision/recovery and Exchange distinguishes recovery_required. Existing commands and script transport defaults remain compatible.

`je_auto_control.api.capabilities` is Beta. `BackendContext`, `CapabilityStatus`,
`CapabilitySnapshot` and `probe_capabilities` expose passive status evidence,
not a claim of platform acceptance. The legacy facade re-exports these names;
the stable core namespace remains unchanged. `AC_diagnose(include_active=False)`
and GUI diagnostics skip actual capture/cursor reads. The stable Python
`run_diagnostics()` retains active checks by default and accepts
`include_active=False`. Native Wayland grant failures never choose another
input device automatically; CLI selection is explicit.

Existing image search, BGR screenshot and fixed-frame healing entry points keep
their signatures and lazily select NumPy/Pillow when OpenCV is absent. The
fallback supports bounded normalized gray template matching, not arbitrary
OpenCV processing or video. Strict OpenCV/je_open_cv dependency accessors now
raise ImageDependencyRequired, which preserves RuntimeError compatibility and
adds AutoControlException, needs_dependency and capability metadata.

`je_auto_control.api.wayland_input` is Beta and re-exports the D3
`linux_wayland.input_events` and `linux_wayland.global_shortcuts` models. PhysicalRecorder returns
bounded raw kernel events, not a replay timeline. StopShortcutSession owns one
asynchronous portal registration and its cancellation; failed authorization is
retained until explicit close/start. Constructing either helper does not open
devices or request consent. WaylandInputSession, five script operations and the historical facade mirror
share JSON AC/MCP/Script Builder adapters. Diagnostics owns an independent panel
session. Raw results are masked in action journals; remote operations require
host administration. Stop sets a cooperative stop_event and stops native input
control, not arbitrary Python execution. Native acceptance remains in Progress.md;
the stable namespace and legacy replay recording contract are unchanged.

Native default authorization uses a separate connection-attempt lock, with
active/pending owners detached under a short cache lock. Stop/reset cancel
pending IPC and stale completion cannot publish its grant; permission polling
also leaves the cache lock free. Tests include controlled workers without
performing desktop input.

GlobalShortcuts owners also retain a bus-daemon NameOwnerChanged subscription.
Loss/replacement of the portal owner revokes pending or active grants, without
automatic reauthorization; an active grant invokes its owned stop callback.
Foreign senders/names and unchanged ownership do not revoke the grant.

Shared GUI translation registries retain child wrappers and use weak proxies
for self entries, including tab titles. This prevents the registry's own cycle
from deferring parentless widget destruction to worker-thread garbage collection.
Setter/translation behavior and returned original widgets are unchanged.

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

Docker native source verification uses the public PhysicalRecorder lifecycle
from an installed wheel against actual ydotool kernel event nodes. A selected-node
open audit must stay empty; failed start must leave no worker, events or leaked
descriptors, and repeated close is safe. This establishes injected-source
exclusion. Physical device capture and GNOME/KDE consent/recovery remain separate
acceptance cases in WAYLAND_ACCEPTANCE.md.

Beta mobile additionally exports `AppState`, `app_state`, `launch_app`,
`wait_for_app`, `stop_app`, `handle_mobile_alert`, `MobileExtension`,
`MobileExtensionSpec`, `run_mobile_extension`, `mobile_app`, `mobile_alert` and
`mobile_extension_action`. The facade mirrors these names. Configure a passive
extension spec with `session.configure_extension(spec)` before first use;
its factory receives `(context, guard)` and must own its native clients, bound
requests and cleanup. Metadata queries never execute the factory. Unsupported
adapter operations and missing dependencies report reasons/recovery. Native
Android install/files/clipboard are provided; iOS equivalents and recording
require a configured adapter. Generic extension operations validate options and
local path roots before creating clients. Clipboard data is explicit API output;
extension options/results are masked in automatic journals. WDA app IDs are newly
created and never borrowed for deletion; deleting a session may terminate its app.
Android owner close does not stop apps. Repeated close retries failed cleanup,
including late construction; no action is automatically replayed after lost replies.

WDA app operations require a dedicated idle endpoint. Bounded status preflight rejects existing or missing session ownership metadata; a short local lease rejects another pending/active owner for the exact URL. WDA has no atomic external-client exclusion: endpoint aliases and external users require operational exclusivity. POST/session can replace an active server session; unknown creation replies require native-state inspection before explicit retry.

### E4 mobile delivery (Beta)

`DeviceSetupReport`, `inspect_device_setup`, `mobile_setup`, `mobile_surface_matrix`,
`android_mobile_action`, `ios_mobile_action`, `run_mobile_actions` and `mobile_run`
are available from api.mobile and the facade. AC/MCP/Builder use the same services.
`mobile_surface_matrix(include_executor=True)` includes the live command inventory;
False gives the lightweight operation catalog. DeviceSession.revoke() immediately
rejects requests without native I/O; call close() off Qt for cleanup/retry. Closing
an owner does not prove restoration of native state. Flat mobile batches validate
all command names/schemas first and exclude desktop/flow/macro/file commands.
The setup report distinguishes SDK version, HTTP/ADB connectivity and untested input.
See [setup and signing](MOBILE_SETUP.md) for explicit opt-in smoke and ownership limits.

### F1 GUI catalog and lifetime

The `gui.main_widget.AutoControlGUIWidget` import path and core methods remain
compatible through lazy descriptors. show/hide/list retain catalog identities,
ordering and visibility fields. hide keeps input/state; the close button and new
close_tab release/delete the widget and remove subscriptions. Reopen builds a new
widget under the same key. TabSpec/TabRegistry metadata in gui.tab_registry is
Qt-free until a factory is opened; open/close belong on the GUI thread. Closing
native panels follows their existing owner cleanup; native state restoration is a
separate acceptance case. No unopened feature is created during metadata, language
or engine refresh.

### F2 workspace presentation

WorkspaceShell embeds one tab registry owner. Navigation and theme tokens are GUI
presentation, not automation services; metadata/token imports remain Qt-free.
Search/language/theme changes do not recreate panels. Responsive details show only
explicitly reported execution state, with ready distinct from native authorization.
Legacy widget constructor remains compatible and accepts an optional standalone
registry for controlled embedding; binding is GUI-thread-only and cannot transfer
an existing owner. Shared task cancellation uses the F3 lifecycle below.

### F3 owned work

TaskController owns run-specific typed result/error/progress delivery. Work receives
copied/headless inputs, a cancellation Event and deadline under captured request
policy. Cancellation/owner destruction revoke delivery; nested AC_sleep wakes and
new actions stop at checkpoints. Backend requests remain bounded and cooperative.
Legacy CallWorker binds the same request/cancellation/input context (300-second
cooperative deadline); custom workers retain their explicit stop Event. Qt-facing
signals/relays do not prove backend cleanup or physical state restoration.

GUI raw input preserves known previously pressed keys/buttons. InputOwner retains
successful raw holds across runs until explicit release/cancel/panel destruction;
failed releases keep ownership and original policy for retry. Cleanup snapshots
cannot release later replacement holds. Unknown initial state rejects acquisition.
The ownership registry serializes cooperating GUI allocation, not external clients.
Headless input outside these scopes retains existing semantics.

GUI Record uses an independent native recorder or X11 subscription. Global recorder
state is borrowed and never stopped by panel cleanup. Unsupported owned recording
fails before allocation. Remote session revocation is immediate; allocation and
native close share a gate off Qt, with failed resources retained. Recorder container
close failures also remain retryable. Tools → Retry owned cleanup retries only
retained owned callbacks/recorders. Global servers/engines require explicit Stop;
completed atomic file/vault/service changes are not rolled back by Cancel.
See [the complete catalog I/O audit](GUI_TASK_LIFECYCLE.md).

### F4 benchmark lifecycle

`benchmarks/gui_startup.py` uses fresh child processes and an explicit target checkout;
the before/after comparison requires identical environment and workload. One warmup
and three samples are retained separately. `--budget` checks calibrated startup/memory
ratios and first-open/event-loop medians, refusing a different calibration environment.
GUI frames capture busy, cancelled-after-return and error states without native input.
Reference results and commands: `benchmarks/results/gui-workspace-f4/README.md`.

### MCP discovery (Beta)

ToolIndex, ToolSummary, MCPToolDescriptor, ToolCategory, ToolCapability and
ToolDiscoveryError plus default_tool_index/discover_tools/get_tool_schema are
Beta exports. Local APIs/actions/Builder/Tools use the default registry; MCP handlers
use the serving registry via call context. Search/index construction invokes no
handler or native capability probe. Current RBAC and read-only apply to each query;
base capability summaries are not grants for arguments/root/env or execution.
Copied schemas and mutation versions belong to the captured snapshot. Full legacy
tools/list is unchanged. Detailed contract: `docs/MCP_DISCOVERY.md`.

### MCP session availability (Beta)

ToolView/DisclosureMode/DisclosureResult/ToolPage/ToolDisclosureError and
preview_tool_disclosure are Beta owner APIs. ToolView.close revokes immediately,
clears selection/snapshots and rejects accepted late work; request ContextVar leases
keep the same closed view across transport drop. No native action is undone or run.
Stateful views/cursors are owned per HTTP session or stdio peer. Preview API/AC/
Builder/MCP/GUI is isolated metadata and closes its ephemeral owner; preview has
no usable continuation cursor. Deployment environment settings preserve default
full lists and provide progressive/static/explicit paging. Stateless requests use
fixed availability and reject cursor/session mutations. Detailed limits and policy:
`docs/MCP_DISCOVERY.md`.


### Policy and measured cost

Stdio flags `--tool-mode`, `--tool-profile` and `--tool-page-size` override corresponding
mode/profile/page-size settings; existing flags and full catalog inspection remain.
Readonly rejects mutating custom-registry calls as well as hiding/disallowing enable.
Availability never replaces the existing schema/RBAC/root/env/rate/confirmation checks.
Concurrent work captures accepted peer identity, roots and capabilities, including after
session removal; the original closed view lease cannot create a replacement session.
Controlled regressions verify root denial, authenticated audits and removed-tool rejection.
`benchmarks/mcp_discovery.py --output report.json` compares identical registry/policy
with one warmup/five samples and records source hash/platform/version. Reference:
full747/363544bytes, core6/2506bytes; local initialize+list37.91/9.56ms and
search9.78/9.65ms. This measures local JSON-RPC, excluding networking/native input.
Artifact: `benchmarks/results/mcp-discovery-g3/report.json`.

### Modernization typing

The strict manifest `test/verify/typing_modernization_modules.txt` and mypy overrides require complete definitions/generics on all new and explicitly rewritten modules. Stable three-platform checks retain zero exemptions. `--extras` requires real PySide6 and checks every modernization GUI module with its stubs enabled, without changing the stable optional-dependency boundary. Lazy SDK handles expose AndroidSDK/IOSSDK structural protocols and typed literal adapter selection; raw construction/disposal stays at SDK adapter boundaries, with dynamic JSON payloads explicit. These internal contracts add no native operation or new public business API.

### H2 reproducible workflow boundary

Six modernization examples expose `--validate` without desktop/device/network effects. Journal v1, labelled evaluation datasets and candidate manifests are explicit formats; legacy action JSON and full MCP defaults stay compatible. Generated code is reviewed before execution. Local metadata previews do not mutate remote sessions. See [workflow and migration guide](MODERNIZATION_GUIDE.md).

H3 acceptance tooling records controlled journal replay and durable sync restart with platform/backend/version, actual outcomes and existing artifact paths; offscreen GUI rendering is tested separately. macOS native JSON retains failed probes. Fifteen coverage CI jobs keep the existing floor. See [acceptance evidence](MODERNIZATION_ACCEPTANCE.md).
