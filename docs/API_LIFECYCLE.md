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
