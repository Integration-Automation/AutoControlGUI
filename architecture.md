# AutoControl Architecture

manage_agent_skill adds review_execution(candidate_id, task_id, execution_task_id,
optional completion_task_id), returning an execution_review token, bounded evidence, expected_version
and approval_required. accept with execution_task_id requires that token plus the existing explicit
version/note. The real original validation trial/spec hash/skill pin stays unchanged. A new injected
recovery-review seam validates at most sixteen private executable links, exact complete original
semantic effects (including JSON types), fixed scope, current principals and final independent
completion/retirement. A separately reviewed read-only proof may verify only the final effect and is
nested under execution_review. No target probe, capture restoration, source success rewrite, fabricated
trial or input grant occurs. One BEGIN IMMEDIATE writer checks proof, candidate and authority before
and after version/publication SQL. New agent_skill_executions stores historical proof alongside the
unchanged five-column publication; get/list expose execution_review only when actually adopted.
Transient task retention cannot authorize new adoption; published audit survives without live rights.
Existing ordinary accept/completion/recording remains compatible. Shared API/AC/CLI/authenticated
MCP/REST/Builder inherit the operation; two inert GUI Actions and four locales prepare requests.

skill_completion validates private read-only admission, a bounded real recovery chain, exact derived
scope and live original/reviewer authority. The neutral completion_contract module checks independent
completion/retirement for both skill and DAG consumers. Runtime injects its existing authority/scope
checks, and AgentSkills supplies its existing snapshot digest; the evidence module stays a leaf.
managed_tasks.validate_recorded_completion
keeps its interface without making skill publication depend on DAG transport initialization. AgentSkills
accept optionally identifies completion_task_id while keeping the real pinned validation trial as
publication.task_id. Candidate integrity and the actual trial/pin are checked in BEGIN IMMEDIATE;
version CAS, publication and optional agent_skill_completions proof commit or roll back together.
Caller/proof authority is checked again after writes. Public completion_review contains historical
IDs/hashes without private principals, preserving the existing thirty-day reader retention. The thin
Actions example edits the shared accept request without task execution or publication.

Skill recording also adopts explicit read-only evidence for a stopped original workflow. Its semantic
actions come from skill_recording.recording_template after private proof checks, preserving the
recorded_spec succeeded-source API. AgentSkills shares candidate construction/insertion with _save;
reviewed recording uses one BEGIN IMMEDIATE writer for source/proof checks, draft insertion and
post-write authority checks. Provenance retains only historical reader IDs/hashes. The draft requires
its own exact validation before publication; the action-free reader is never a fabricated trial.
An additional thin Actions example prepares a record request with separate source and reader IDs.

control_admission classifies only fixed stop routes and closed DAG pause bodies. The shared client
uses existing reserved transport slots and an internal marker for multiplexed DAG pauses. REST
selects a separate bounded per-IP bucket in the exact built-in auth gate, then retains live principal,
role, ownership and ordinary handler checks. Marked non-pause DAG bodies refuse before dispatch;
custom gates keep their own contract. Both lanes share authentication failure/lockout state while
ordinary polls cannot spend stop tokens. Input cleanup and success publication are unchanged.

completion_recovery derives closed read-only task specifications from reviewed stopped sources. A trusted
CompletionBinding inserts private proof alongside real recovery lineage in the task transaction; model
options never select it. Runtime routes bound tasks to cached permanent ReadOnlyNativeTarget proxies,
blocks act/ordinary recovery upgrades, and evaluates original effects against fresh independent target
evidence. Existing broker generations, budgets, cancellation/restart and retirement/publication CAS remain
authoritative. Source/effect snapshots and both owners plus the actual reviewer stay live; the final parent
checkpoint now runs after helper retirement. Public completion_review metadata omits private stores.
Existing DAG adoption accepts the independently completed successor; the old source stays stopped.

readonly_worker.ReadOnlyWorker permanently restricts owned RPC to configuration/observation/verification
and empty cleanup, rejecting executor calls, input ACKs and authority replacement. Identical configuration
may repeat to rerun current readiness, without replacing the target or caching readiness/observations.
readonly_target provides
a fresh ReadOnlyNativeTarget/CompletionReader with exact no-input negotiation, live owner/root/parent
checks and closed-view fences. Host perform/recover overrides also block local workflow launch and
witness recovery. Unexpected input is recorded but never ACKed/released; helper retirement preserves
resource quarantine. Standard NativeDesktopTarget.completion_reader clones only its host interpreter,
profile and resource into the dedicated module after source retirement. It never reuses old observations.
Passive target summaries declare readonly_completion only for the exact built-in proxy, without custom
descriptor calls or readiness probes. Browser startup and ordinary/custom-worker fallback are refused.
The seam itself does not publish success; completion_recovery binds it to the reviewed task workflow above.

Android focus guards use one labeled sed extraction of display/window/activity and an exact quoted
comparison against six field-order permutations. Nonempty labels retain duplicate empty values through
command substitution; missing/extra/wrong values still refuse. Serial/boot sentinels, pre/post scope,
input-security digests and deadlines remain. Test-owned POSIX fixtures use Bash read/printf for byte-exact
files (including NUL) with external cat fallback; safe bounded phase/timing diagnostics replace raw
timeout command/output tracebacks. This reduces owned-worker deadline pressure without granting input.

task_authority.py adds explicit source-owner recovery admission. ownership_scope preserves the fresh
source owner separately from the actual reviewer; a snapshot/namespace/role-bound ownership review
precedes creation. RecoveryBinding carries ownership beside optional origin authorization into the
same task/lineage transaction. agent_recovery_owners retains private identities with the recovery
tombstone; recovery_link exposes only bounded audit fields. Shared check_task_authority combines local
DAG admission and explicit recovery owner/reviewer checks at scope/checkpoint/nested/pre-input and
maintenance boundaries. Default recovery stays caller-owned. Thin GUI owner selection carries the
review token without changing read ACLs. A source-owned independently completed recovery child can be
adopted through existing DAG evidence under the original owner. No arbitrary owner transfer is exposed.

dag_retention.py shares existing prune_agent_tasks/hourly maintenance: owner-scoped expiry of unused
registrations and settled successful batches, plus host-only terminal orphan agent_dag delivery cleanup.
The batch lock and write transaction recheck age/state, phases, related tasks/recovery descendants,
uncertain actions, live/durable input ownership and coordinator deliveries before cascading metadata.
retention.py protects every retained batch reference and recovery successor before deleting task
artifacts. Running/review/approved batches retain their evidence and local actor/admission gates.
Results add deleted_batches/deleted_dag_deliveries; no remote retention lease is implicitly granted.

dag_local.DagLocalTasks implements closed per-node local submit/get/lookup/pause behind durable claims.
The source service admits the frozen specification/key under the original owner; dag_admission carries
a trusted synchronous envelope into TaskAdmission and AgentTaskStore.create. Task/key/submission and
agent_dag_local_tasks actor/node/attempt records commit atomically. Key retries verify the previous
binding without backfilling. Runtime scope, pre-dispatch checkpoints and maintenance revalidate actor,
original owner, cross-owner management authority and live claim/attempt. managed_local_scope overrides
one copied node transport while preserving source checks; caller/background modes share the bridge.
Task metadata projects only bounded admission identity. Exact pause can retire an admitted task after
fencing; it does not grant submission, replay or another task's control. Explicit source-owner recovery
preserves evidence visibility; dag_retention.py protects these relationships until settled expiry.

Caller-bound DAG execution obtains AgentRuntimeClient.bound() before begin/approval, storing only an
absolute owner-file path and endpoint/token/generation digest. Fresh metadata checks precede every
request; managed_runtime_scope routes copied local-node contexts through that same client and checks
the binding during polling. local_evidence.runtime_evidence_scope binds server-side lookups to the
owning runtime without global client discovery, preserving current original-owner context while
refreshing the actual caller. Admin inspection reads original-owner request keys. Remote host policy
and credential forwarding stay destination-owned. Metadata replacement stops future calls, retaining
durable uncertainty; it does not claim cleanup of already accepted input. Ordinary clients keep
adaptive discovery. Explicit source-owner successors preserve ordinary original-owner evidence access.

dag_jobs.BackgroundDags uses the existing WorkQueue in the agent_dag namespace with four service
workers and a 64-delivery pending ceiling. run_background consumes a registered/approved attempt and
persists its delivery; acceptance failure fences it. dag_service_client binds coordination/local task
operations to the owning runtime with independent original-owner and actor refresh. A context-local
managed_runtime_scope follows copied node contexts, avoiding global connection discovery without
forwarding local principals/origins to remote hosts. Caller and service modes share execute_started,
claims and independent completion. Close/stop_all fence coordinators before task retirement. Process
restart fences running batches and marks old WorkQueue deliveries failed without reclaim or replay.
GUI Actions submits/reads service records and can close independently. Background lifecycle evidence is
in test_agent_dag_background.py, test_agent_dag_background_gui.py and test_agent_dag_background_crash.py.

Whole-DAG continuation uses dag_continuation.py with separate evidence and per-node decision modules.
Review binds the original graph/claims, current owner and real approving actor, pinned host configuration,
independent completion and local authority ceilings. Approval stores an immutable audit and transactional
bindings/adoptions; start revalidates and consumes one attempt. Adopted dependencies are checked again
before new claims. Pending dispatch requires no previous claim and no accepted request. Original input
graphs and trusted admission digests preserve historical identity across origin expiration; authority is
renewed separately within equal/narrower scope. Legacy tasks are never backfilled and require live matching.
run_dag recovery and API/AC/MCP/REST/CLI/Builder share the protocol; GUI Actions remain thin adapters.
pause_batch invalidates scheduling attempts without claiming destination-task cancellation or cleanup.

Request-key spec matching reuses the original normalized-spec digest calculation. Runtime.lookup can
validate a reviewed spec at the destination and compare it with the same owner/key record's immutable
hash, without dispatch or input acquisition. The additive spec_match_contract=1 capability permits DAG
inspection to perform a second read-only lookup; missing/invalid capability leaves legacy snapshots
unverified. Matching checks the same task ID and refreshes authorization/deadlines around each query.
Local origin witnesses never enter remote spec matching. Node-spec identity does not approve DAG topology,
batch identity or continuation; resume_permitted remains false.
When node specs match, recorded completion shares the execution verifier's exact report count/kind/status,
retirement and contract checks; a partial or mismatched report cannot certify completion.

DAG inspection.py validates the whole graph before querying up to 100 task keys under a finite budget.
It reuses managed_tasks connection policy and owner refresh, requests lookup only, strips remote metadata
and raw diagnostics, and never schedules actions or sends control operations. recorded_completion concerns
the recorded task alone; node-spec matching is optional and resume_permitted is always false. Public
API/AC/MCP/CLI/Builder and REST action execution share this read-only path. DAG Actions display snapshots
and discard results when the graph editor changes; worker authority and stop context survive offload.

Request-key inspection shares the submission identity/hash calculation in AgentTaskStore. Runtime.lookup
refreshes the current principal before resolving its exact user/store namespace and returns an owner-scoped
status snapshot without dispatch, target activation or writes to request keys. The closed POST lookup route
is shared by Python/AC/MCP/CLI/Builder/GUI; read-only MCP annotations retain drive_input authority.
No match is a snapshot, never proof that a still-pending request cannot arrive. GUI lookup binds both key
and selected task to discard late results. Registered-host DAG review remains distinct from submission.

DAG task_contract.py validates and freezes a closed task envelope, preserving destination paths without
local canonicalization. managed_tasks.py uses the local delegated client or a snapshot of a registered
admin host's URL/token; remote requests never delegate local principal/origin metadata. It submits once
with an explicit stable key, polls the exact task, checks matching criterion reports and durable completion
contract 1 plus input_released, and returns only bounded recovery identity. Failure requests bounded pause
with cancellation suspended; an unconfirmed acknowledgement never grants completion. Destination runtimes
own physical resource exclusion; graph failures skip dependants. Running managed nodes see the DAG stop
event; ordinary action runners retain their existing finish behavior. GUI workers capture caller context
before offload and existing Actions show recovery task IDs. Nested managed-task dispatch is refused.
DAG DTOs, parse_dag and run_dag are explicitly re-exported through api.core and api as well as the root.

Completion stores verification while still verifying, retires input, then conditionally publishes the
outcome only if control has not changed the state. Failed or busy retirement cannot publish success;
unconfirmed cleanup retains the lease and requires review. A crash before retirement confirmation leaves
verifying for recovery. AgentTaskStore.transition performs the state comparison and update in one write
transaction. Status metadata.input_released exposes local lease retirement; final reports publish after
the committed outcome. agent_completion stores contract version 1 atomically with new success, retains
it across restart and cascades on task deletion; legacy success has version zero. This evidence is local
to the owning runtime, not a remote-device acknowledgement.

The DAG pool captures a fresh context for each node, preserving caller authorization, command guards,
cancellation and managed operation state for default and custom runners. Node dispatch refreshes
store-backed identity through DeferredAuthorization.context_scope; operation-specific checks use that
current role. Default remote dispatch checks the existing host-management capability before address-book
or action-file access. Contexts never cross the network. Managed nodes use the closed lifecycle above;
production deployment and native/device evidence remain open in Progress.md.

> Short overview for people and agents. Per-module detail lives in [`architecture_explore.md`](architecture_explore.md).
> Last verified: 2026-10-19 on `dev`.

## 1. Purpose

AutoControl (`je_auto_control`) is a cross-platform GUI automation framework: mouse and keyboard control,
screen capture, image recognition, OCR, accessibility-tree lookup, action scripting and report generation
behind one headless Python API. Every feature is also reachable from JSON action files (`AC_*` commands),
a CLI, TCP / REST / MCP servers, a pytest plugin and an optional PySide6 GUI. Backends cover Windows,
macOS, Linux X11, Linux Wayland, Android and iOS.

## 2. Layers and directories

Managed task entry points share a local runtime service, authenticated REST routes and one command
catalogue for AC/MCP/Builder. AgentRuntime owns detached specs, principal references, SQLite task/action
state, a process lock and fenced target ownership. Internal skill/Ollama jobs reuse WorkQueue; external
agents use the same observe/act/finish operations. Completion is independently verified. TaskController
owns GUI requests only, so closing a view does not own or retire committed background tasks.
The Ollama adapter uses bounded loopback HTTP without redirects or remote fallback. Native calls use an owned helper process tree with cancellable IPC, a host input ledger and a shared
per-session input lock. Runtime operation context follows parallel/DAG workers. Cancelled HTTP calls
request host pause through separate control capacity. Physical activity monitoring, native acceptance,
richer workflows and origin-policy lifecycle remain open.

Agent tool calls share `Executor.execute_one` with the existing per-action pipeline.
`executor/dispatch.py` binds strict executor ownership, raw-result capture and intersecting
context-local guards. Guards run after variable interpolation on nested commands as well;
single-command callers also enforce the default command capability that server routes normally enforce.

Native pointer region validation preserves raw-first then layout-origin
mapping. A miss raises a failed LibeiUnavailable before motion/frame or
a following click. The input selector propagates that refusal and cannot
interpret it as optional dependency absence or switch automatically to CLI.
The cached sender remains usable for later valid coordinates.

wrapper/capabilities.py owns immutable caller contexts and independent
input/capture metadata. Live collection reads a bounded set of environment/
PATH facts and an already-loaded sender via a nonblocking local-state read.
It never constructs a native backend or polls it. Dependency presence is
unverified; observed native state may be stale and grants no authority.
One headless adapter serializes the SDK contract for AC and read-only MCP;
the Diagnostics view caches only inert snapshots and retranslates them
without probing. Live defaults omit addresses, arguments, executable paths
and native error text. XWayland scope is always limited; actual operations
continue to enforce permission/revocation independently of this report.

gui/task_controller.py composes the existing daemon-worker relay rather than
introducing another thread registry. Weak handle delivery and independent
task state prevent owner/handle callback retention. Owner destruction cancels
only its token; controller retirement also cleans jobs after the controller
has gone. Context/identity are refreshed on dispatch, without prescribing
one capability for every task. Each work function authorizes its operation.
Qt-free cancellation/progress live in utils/exception/cancellation.py.
Legacy start_worker retains its API and now rolls back failed thread starts.
Remaining panel/backend integration and WebRTC splitting remain open.

Diagnostics now adopts TaskController with a plain-data runner snapshot and
READ_SCREEN revalidation. Its run/stop Actions and cached four-language
state never operate widgets from the worker or reaccept closed-run data.
The worker binds cancellation_scope; SDK/AC and the additive active MCP
handler share the same diagnostic core and scoped checkpoints/progress.
The MCP token bridges only its own request event, preserving connection
identity and the established OperationCancelledError protocol.

utils/dbus_client/cancellable_io.py retains socket deadlines and partial
write offsets; utils/cancellable_process.py owns only newly launched
capture helpers/groups. Cleanup temporarily suspends cancellation, retains
primary controls and never signals an already reaped PID. Portal Close
remains separately bounded; liboeffis acquisition releases its own context.
Uncooperative extensions and remaining backends require separate migration.

The active diagnostics runner separates ordinary failed probes from explicit
direct/wrapped control signals. Headless controls propagate unchanged before
logging or subsequent checks; the GUI receives typed cancellation metadata. A failed
ordinary probe still contributes a report row and allows other probes.

The Diagnostics panel starts idle and its Actions command owns active checks.
Retranslation updates idle instructions and headers without invoking providers.
The existing headless runner and executor/MCP diagnostic command remain active
explicit operations. Passive capability inspection has its own Actions command.

Screenshot portal requests retain their own predicted/returned handle and bus.
Failure before Response attempts bounded Request.Close; completed interactions
are not closed again. Cleanup prioritizes original controls. The shared D-Bus
client budgets writes plus remaining replies, applies an explicit connect timeout
and retires descriptor ownership before closing partial __enter__ state. This
path neither selects a different capture provider nor acquires input permission.

The repository-only CI diagnostics runner wraps the existing pytest/coverage
command, streams stdout/stderr to a retained log and records runtime versions
and child exit status without an environment dump. Linux uses batch GDB with
user initialization and shell startup disabled. A secure temporary Python
launcher execs JSON-decoded argv so older GDB whitespace parsing cannot alter
arguments. SIGINT reaches the child; an independent Linux preflight verifies
the runner before tracing the suite. Native aborts retain all-thread
backtraces and a failing exit. Dev/main upload diagnostics on success or failure.
It does not import the framework, open devices or change SDK/GUI behavior.

Selected dev pushes run `.github/workflows/ei-lifecycle.yml` in an isolated
libei/libeis container, retaining versions and both native logs for 14 days in
`ei-lifecycle-<run>-<attempt>` artifacts. Half-open and live cleanup children
have 10/60-second deadlines and faulthandler. Unrelated child failures fail CI;
successful cleanup requires begin/end markers. The half-open probe also requires
equal integer descriptor counts; live cleanup releases owned device refs first.
Run 39507190704 on libei/libeis 1.3.901-1 passes 9/9 and 20/20 checks, including
native out-of-region refusal without CLI fallback. Half-open `ei_unref` still
segfaults, so runtime protection remains and helper isolation is pending.
Device pause and sequence readback remain unverified. These controlled socket
peers do not establish compositor consent, physical or multi-monitor acceptance.

Wayland input uses Qt-free `_input_state` metadata to distinguish optional
absence from authority/protocol refusal through portal, libei cache, selector
and keyboard/mouse layers. Refusal caches hold no traceback or native handle.
Disconnect latches sender revocation; explicit reset permits a fresh grant.
Native chord cleanup attempts all owned releases before choosing the primary
control/error. Neither revocation nor forced-native absence selects CLI.
This path leaves capture selection and the explicit wtype text path independent.

Each layer calls only the one below it:
entry points → execution core (`utils/executor/`) → headless capabilities (`utils/`) → `wrapper/` → one OS backend.

Fixed-frame self-healing evaluation is a separate headless flow in `utils/self_healing/`:
bounded manifest/PNG inputs → immutable samples → explicit locator strategies →
quality/latency/provenance report → optional atomic JSON/HTML export. It performs
no capture or input. Python VLM comparisons require an explicit backend; local
manifest commands never choose one. API, AC, MCP and a cancellable GUI worker use
the same evaluator. Live self-healing binds a lazy `cv2_utils/locator_frame.py`
owner around the existing image/VLM seams. The owner captures once in logical
coordinates, retains clipped geometry or a capture failure, and releases pixels
on exit. `runtime_evidence.py` snapshots source/version/frame/strategy metadata
without taking a screenshot. One schema-v2 audit row settles after any requested
click and explicit verification. Immutable requests prepare callback/VLM checks
before input; the post-click check binds a fresh frame, isolated from the locator
owner. JSON adapters constrain nested paths, distinguish false verification from
unknown and share phase cancellation across AC/MCP/CLI/GUI entry points.
Standalone VLM capture uses `vision/frame_capture.py` with scoped geometry;
logical PNGs stay in memory. Input dispatch and operation verification remain distinct. Existing result
and call signatures remain compatible, and unbound locator calls stay unbound.

Template revisions use immutable schema-v1 JSON bundles containing original and
candidate bytes, content hashes, canonical target and match threshold. Previews
are bounded PNG thumbnails. Verification reuses the fixed-frame sample loader and
comparison engine; the bundle supplies the frozen versions. Explicit acceptance
reverifies labelled positives/expected misses, then takes a target lock, rechecks
the reviewed bundle and file content and performs one atomic replacement. Revert
compares content before restoring exact original bytes. File state is derived
from bytes, so no mutable manifest pointer can disagree after interruption.
All paths intersect current/enclosing roots, including loaded sample paths at
commit checkpoints. GUI tasks retain authority/context and stop before writes;
completed writes are not relabelled cancelled. Native operation verification is
independent. Candidate operations share API/AC/MCP/CLI/Builder and GUI surfaces.

Local causal primitives retain independent JSON entry snapshots and version
vectors. Strict dominance selects successors; concurrent/forked data stays an
explicit conflict, and resolution observes all selected alternatives. A serialized
peer ledger keeps acknowledgements and retirement epochs without time-based expiry.
The SQLite outbox binds endpoint/account/device identity, preserves exact prepared
requests, schedules bounded retries and checks lease ownership before publishing
results. Cancellation and hard signals keep edits durable. Pure merge/peer-state
adapters and private local enqueue/status share API/AC/MCP/Builder surfaces; they
make no network requests or configuration changes. CausalBucket snapshots and
CausalConfigStore bind server-assigned change revisions, peer epochs and explicit
actor transitions to the same atomic CAS/receipt transaction. Dedicated version-three
/causal routes reject malformed membership, forgotten alternatives and obsolete
epochs. All active peers must acknowledge a deletion before payload collection;
permanent minimal fences retain its causal floor. Plain writes and reads refuse
upgraded accounts. Existing private store commands also accept causal JSON with
an explicit transient _actor. The explicit CausalSyncClient composes a v3 wire
adapter over the existing bounded HTTP egress/redirect seam. Durable prepared requests
retry before any refetch; only typed stale-base rejection allows bounded rebase.
Operation-ID conflicts retain the exact request. CausalReceipt confirms queue delivery
and the latest server snapshot in one lease-owned transaction; expired owners cannot
publish, older snapshots cannot regress and equal-revision forks roll back. Private
HTTP AC/MCP/Builder fetch/commit/flush commands use live environment credential
references. Durable explicit controls use a singleton leased intent per namespace and
compact receipt history. Controls drain before edits; uncertain payloads retry unchanged.
Only confirmed full-resync receipts atomically adopt local identity/cache and retire old
pending work with explicit consent. Schema 1/2-to-3 migration validates owned tables and
preserves edit wire. AC/MCP/Builder control status is private and local-only. Applications
choose ack/collection timing; Sync UI and referenced assets are described below. Shared-secret access is service-wide.

Asset manifests contain portable relative paths, sizes and SHA-256 only. AssetTransport
provides binary streams and a live local generation root; DirectoryAssetTransport is
the built-in local-only source. sync_assets stages all files, verifies their content,
then publishes one immutable generation directory. Reuse verifies metadata, exact tree
and all hashes; corruption preserves evidence and aborts. Private AC/MCP/Builder paths
share current root/cancellation checkpoints. Causal bundle coordination is described below; explicit native working-copy loading is described below. This layer never replaces active workspace files or runs scripts.

Seven dependency-free source adapters capture selected scripts, locator repositories,
hotkey/trigger metadata, address-book entries, JSON settings and saved native workspace preferences. A lazy owned SQLite
ledger retains concurrent heads, source baselines and immutable operation receipts per
endpoint/account/origin/epoch/profile/domain. Incoming data is validated before the
transaction, including numeric ranges before finite conversion; cancellation rolls back the complete batch. Explicit reviewed head sets
gate resolution. Received profiles never mutate active sources or register callbacks.
SyncBindings carries named vault/local references; only explicit local scalar bindings
are resolved (absolute path entropy is not a credential classification), and vault values are never read. Complete native-format profiles publish
through the verified asset generation layer with hotkeys/triggers disabled. Four private
AC/MCP/Builder commands use the same lazy descriptor factory and live root/cancellation
checks. Source/outbox/full-resync coordination is described below;
explicit live GUI preference application and Sync UI are described below.

WorkspaceSettingsSyncAdapter adds the workspace causal section for saved native GUI
INI preferences. Only theme/font_pt/navigation_visible/navigation_width are captured;
other sections and machine state are excluded. A Qt-free bounded INI reader follows
local native key case and refuses ambiguous aliases, without Python DEFAULT inheritance.
The GUI and source reader share tolerant preference normalization, while incoming values
require canonical types and supported bounds. Complete generations include workspace.ini
and portable version metadata, with defaults for absent/deleted preferences. Seven kinds
can publish together. Explicit GUI loading uses a separate mutable working copy; opening
the immutable generation itself for GUI writes would damage its verified cache. Existing
four private AC/MCP/Builder commands accept workspace descriptors without new commands.

SyncWorkspace coordinates explicit seven-domain source profiles over the causal outbox
and HTTP client. A bounded namespace lease excludes concurrent mutators, atomic batch
enqueue imports pending heads before source capture, and strict typed validation runs
before snapshot cache/prepare/receipt adoption. Full-resync source fingerprints share
the durable control-intent transaction. Adapter ledger schema 2 adopts each confirmed
new-generation baseline once, retaining later local edits and compact deletion fences.
Source/asset-cache/state/outbox roles cannot overlap; selected kind/state bindings remain fixed.
Private API/AC/MCP/Builder use live roots/cancellation and per-RPC environment credentials.
Materialization remains inert; explicit native working-copy loading is described below. The two-source example and regressions use temporary loopback only.

The lazy config_sync_tab uses immutable JSON requests and the shared GUI-thread relay.
config_sync_worker captures context/authority, refreshes DRIVE at core checkpoints and queued
delivery, and cooperatively cancels without relabelling committed writes. Actions expose
status/capture/sync/controls/review/resolve/materialize and explicit reviewed preference
application. Qt-free workspace_review compares the exact reviewed head set, refuses
conflicts and returns four canonical defaults/values without observing source files.
MainWindow validates all values before live theme/font/navigation mutation; normal close
persists them. Receipt never changes a running window or activates native definitions.

Native loading is a separate explicit boundary: profile_load verifies the exact source
manifest, streams/hash-checks into owned staging, and profile_native compares canonical
native files with sealed heads before one atomic fresh working-copy publication.
profile_bindings resolves only typed assets and native file fields against that root.
profile_runtime looks up native subsystem factories only for explicit nonempty loading,
avoiding engine-default initialization from the config_sync import path. LoadedSyncProfile
owns the initial native snapshot and disabled hotkey/trigger objects; repository/book
handles open working files explicitly. Private API/AC/MCP/Builder share DRIVE and live
roots/cancellation. Sync UI retains the loaded snapshot for kind inspection, explicit
Builder import and preference application, checking both current caller and captured owner.
Existing source selection and global engines retain their own ownership; received data
does not register listeners, connect saved hosts, resolve vaults or execute scripts.

Referenced assets add explicit private alias/destination bindings and portable full/chunk
SHA-256 descriptors. Source capture freezes bytes in an account/endpoint-scoped sibling
cache before causal fingerprints. A separate owned schema-1 chunk store verifies bytes,
size/layout and full hashes before immutable blob receipts, with byte/object/user quotas.
Authenticated signaling asset routes and the lazy per-RPC credential client resume only
missing content-addressed chunks. Upload precedes new causal prepare; uncertain prepared
definition retries bypass asset probes. Selected received heads download to the cache;
one consistent profile bundle streams native metadata and exact asset capabilities into
the all-or-none generation publisher. Native paths are relative to generation root;
missing/corrupt/conflicting assets cannot publish a script-only generation. No received
work activates. Low-level profile paths are authorized and fixed at construction, so
later cwd changes cannot redirect asset reads. Server --asset-store chooses a separate
lazy SQLite location; existing config/outbox database and wire versions stay unchanged.

Cancellation carriers and classifiers live in the dependency-free
`utils/exception/control_signals.py` seam. MCP context and run-history import paths
remain aliases to the same classes/functions; transport code need not import the
executor to preserve wrapped interruptions. MCP cancellation keeps its deliberate
RuntimeError-only ancestry so ordinary framework handlers cannot swallow it.

Persistent configuration uses a shared wire contract and lazy per-operation
SQLite connections. One transaction checks the account base revision, replaces
the bucket and records its operation receipt. Identical retries retain their
original revision across later writes and restart; stale or reused identities
conflict. The signaling service delegates conditional config routes to this
headless store; SDP remains process-local. Clients use version-two envelopes by
default and propagate conflicts. Legacy blind writes require explicit client and
server settings. AC/MCP/Builder expose local private store reads and commits;
no synchronized script or trigger is activated. Causal merge/outbox and asset
adapters remain separate layers.

Journal candidates read a bounded byte snapshot and validate the whole structured
wire schema and append order before selecting a run. Lifecycle reconciliation
retains source line and append-sequence provenance, parent hierarchy and provable
retry boundaries.
Selection preserves recorded block inputs, covers their children once and uses
explicit observed-path fallbacks only for sequential observations; incomplete or
failed roots and unreconstructable parallel sources are excluded. Existing codegen
renders all three targets; static/signature/dry-run validation dispatches no input
and unbinds enclosing journal capture. Sealed review data rejects later mutation.
One atomic ZIP contains code, actions and provenance. CLI --from-log, AC/MCP and
owned background GUI review share the core. Explicit Builder import retains source
metadata and refuses edits made after the diff baseline; it does not execute.
Journal redaction inspects encoded parallel branches before persistence, preserves
safe source strings/references and masks resolved input strings/dynamic keys.

| Path | Responsibility |
| --- | --- |
| `je_auto_control/__init__.py` | Facade: re-exports the public API and lists it in `__all__`. Must import without PySide6. |
| `je_auto_control/api/` | Small versioned headless facade (`core.py`); the supported entry for new integrations per `docs/API_LIFECYCLE.md`. |
| `je_auto_control/cli.py`, `__main__.py` | Main CLI and the legacy argparse entry point. |
| `je_auto_control/utils/executor/` | Execution core: `Executor.event_dict` (`AC_*` name → callable) in `action_executor.py`, block commands in `flow_control.py`, validation in `action_schema.py`. |
| `je_auto_control/utils/` | Headless capability layer, one subpackage per feature, zero Qt imports. Grouped by theme in `architecture_explore.md` §5.4. |
| `je_auto_control/utils/{socket_server,rest_api,mcp_server,pytest_plugin}/` | Server and integration surfaces (§3). |
| `je_auto_control/utils/{remote_desktop,usb,usbip}/` | Remote desktop (TCP / WebSocket / WebRTC) and USB passthrough; file_sync.py owns content digests, explicit receive receipts and stopped folder workers; webrtc_file_write.py confirms bounded/cancellable channel writes, webrtc_file_commit.py owns weak channel/epoch bindings and authenticated publication confirmation, file_sync.py exports immutable retired-worker checkpoints and folder_sync_io.py binds explicit GUI resume to peer/root/principal, clipboard_delivery.py binds explicit TCP/WS clipboard work to concrete peers and refreshed local authority, using once-bound weak registration to avoid self-owned viewers while queued deliveries retain original identity, webrtc_file_tasks.py owns queued inbox pushes, webrtc_file_receive.py binds inbound file lifetimes to the authenticated peer/channel, file_receipts.py freezes local publication metadata, webrtc_file_callbacks.py preserves native path/receipt/audit callback semantics, and GUI folder_sync_io.py binds jobs to authorization and peer identity. |
| `je_auto_control/utils/webrunner_bridge/` | Optional bridge that runs WebRunner `WR_*` commands (§6). |
| `je_auto_control/wrapper/` | Platform-neutral API (`auto_control_mouse/keyboard/screen/image/record/window.py`); `platform_wrapper.py` picks the backend; `backend_contract.py` types the seam; `window_backends/`. |
| `je_auto_control/{windows,osx,linux_with_x11,linux_wayland}/` | Desktop OS backends; only the running OS's backend is imported. |
| `je_auto_control/{android,ios}/` | Mobile device control (adb / uiautomator2, WebDriverAgent). |
| `je_auto_control/gui/` | Optional PySide6 GUI (`[gui]` extra): `main_window.py` (menus, navigation dock, theme), `main_widget.py` (the tabbed workspace), `workspace.py` (scroll containers preserving original page identity, vector close buttons), `workspace_settings.py` (validated per-user QSettings, injectable in tests), the Qt-free `TabRegistry` in `tab_registry.py` (open caches panels; close detaches and schedules owned panels for destruction, retaining metadata and legacy forms), `navigation.py`, `theme.py`, `script_builder/`, `remote_desktop/`, `language_wrapper/`. |
| `autocontrol-lsp/` | Separate distribution: language server for `AC_*` action JSON, plus a `vscode/` client. |
| `test/` | `unit_test/headless/` (CI gate), `unit_test/flow_control/`, `integrated_test/`, `gui_test/`, `manual_test/`, `verify/`. |
| `docs/` | Sphinx docs, `API_LIFECYCLE.md`, `CAPABILITY_MATRIX.md`. |
| `examples/`, `benchmarks/` | Runnable example scripts; latency smoke benchmark. |
| `docker/`, `k8s/helm/`, `ci_templates/` | Container images and backend verification harnesses, Helm chart, GitLab CI template. |
| `browser-extension/`, `AutoControl/`, `exe/`, `autocontrol_driver/` | Manifest v3 companion extension, project-template sample, packaged GUI launcher, driver build script. |
| `scripts/` | Release tooling, not shipped: `dev_release.py` numbers and gates the dev-channel package (§3). |

## 3. Entry points and public interfaces

| Surface | Exact name | Notes |
| --- | --- | --- |
| Python facade | `import je_auto_control` | Broad historical surface (`__all__`). |
| Stable API | `je_auto_control.api` → `api/core.py` | `CancellationToken`, `TaskProgress`, `cancellation_scope`, `BackendContext`, `CapabilitySnapshot`, `CapabilityStatus`, `probe_capabilities`, `FailureBundleOptions`, `create_failure_bundle`, `execute_action`, `execute_action_with_vars`, `failure_bundle_on_error`, `generate_code`, `run_diagnostics`. |
| Main CLI | `je_auto_control` → `je_auto_control.cli:main` | Subcommands `run` (`--var`, `--dry-run`), `validate` / `lint`, `fmt`, `list-commands`, `record`, `codegen`, `failure-bundle`, `list-jobs`, `start-server`, `start-rest`, `version`. |
| Legacy CLI | `python -m je_auto_control` (`__main__.py`) | Private `_main()` owns dispatch and error conversion. `-e/--execute_file FILE`, `-d/--execute_dir DIR`, `-c/--create_project PATH`, `--execute_str JSON`. `--execute_str` also accepts a double-encoded JSON string. Any error exits 1 with a log line rather than a traceback, and a `-d` path that is not a directory is an error. |
| MCP server | `je_auto_control_mcp` → `utils/mcp_server/__main__.py:main` | stdio; `start_mcp_stdio_server()`; HTTP transport via the `AC_start_mcp_http_server` command. |
| REST API | `je_auto_control start-rest`, `python -m je_auto_control.utils.rest_api`, `start_rest_api_server()` | Default `127.0.0.1:9939`, bearer token + rate limit. |
| TCP server | `je_auto_control start-server`, `start_autocontrol_socket_server()` | `utils/socket_server/auto_control_socket_server.py`, default `127.0.0.1:9938`, JSON action lists. |
| pytest plugin | `pytest11` entry point `je_auto_control_pytest` (top-level module, imports only pytest; `je_auto_control.utils.pytest_plugin` re-exports it) | Loaded automatically once the package is installed, without importing the package (see coverage rule in §7). |
| LSP | `autocontrol-lsp` → `autocontrol_lsp.server.server:run`; `python -m autocontrol_lsp.server` | Command list is read from the live executor. |
| GUI | `start_autocontrol_gui()` in `gui/__init__.py`; `exe/start_autocontrol_gui.py` | Needs `pip install je_auto_control[gui]`; PySide6 is imported only under `gui/`. |
| Action lint | `python -m je_auto_control.utils.action_lint` | Used by `.github/workflows/action-json-lint.yml`. |
| PyPI packages | `je_auto_control` (stable), `je_auto_control_dev` (dev channel) | Both ship the same `je_auto_control` import package. Stable: a push to `main` runs the `publish` job of `stable.yml`, which bumps `pyproject.toml`, uploads and tags. Dev: the `publish-dev` job of `dev.yml` runs after the headless suite on a push to `dev`, builds from `dev.toml` and uploads when the commit is still the tip of `dev` and the wheel differs from the newest published one; `scripts/dev_release.py` takes the version from PyPI (newest release plus one patch), so nothing is committed back. `dev.toml` declares what `pyproject.toml` declares (`test_dev_toml_parity.py`). Both jobs hold the PyPI token and install nothing but the hash-locked `.github/requirements/publish.txt` (`build`, `twine` and the `setuptools` backend, generated from `publish.in` beside it), then build with `python -m build --no-isolation`, so the backend is the locked one (`test_publish_tooling_lock.py`). |

## 4. Main flows

Executor runs use a `utils/logging/secret_scope.py` mask for vault values resolved
by interpolation. CLI/REST/MCP and scheduled/triggered/hotkey/email owners keep
the mask alive through error handling and persistent diagnostics. A logger
filter sanitizes records before handlers; audit, history and report snapshots
mask text before storage. Joined local parallel/DAG workers share the mask;
independent requests isolate it, and the owner clears it on exit. API outcomes
retain their values; CLI error output is sanitized. Watchdog/observer rules and
callback-executor invocations own their complete diagnostic scope; nested
invocations reuse the enclosing run mask. DAG calls also own a mask; each
node worker binds it through runner execution, error handling and final timing,
including custom local runners. Returned error payloads retain their values.

**A. JSON action script (primary path)**

```
action.json → utils/json/json_file.read_action_json
  → Executor.execute_action                       (utils/executor/action_executor.py)
      → action_schema.validate_actions            (unknown AC_* names rejected before anything runs)
      → _execute_event → flow_control.BLOCK_COMMANDS  (AC_loop / AC_if_* / AC_try / AC_retry …)
                       | event_dict[name](**args)     (${var} / ${secrets.*} interpolated via utils/script_vars)
  → wrapper/auto_control_*.py → wrapper/platform_wrapper.py → windows/ | osx/ | linux_with_x11/ | linux_wayland/
  → record dict {"execute: [...]": result or repr(error)}
```

Errors of the `AutoControlException` family are recorded, not raised (unless `raise_on_error=True`);
`AutoControlAssertionException` always propagates. Every path that runs an action file from disk (`execute_files`,
the CLI, the scheduler, triggers, hotkeys, webhooks, the MCP run tool, the GUI) loads it with
`read_executable_action_json`, which reads it once and verifies those bytes against the `.sig` sidecar when
`JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS` is set (`utils/action_signing/`).

**B. Remote and external drivers** all feed the single global `executor`:

```
TCP socket_server | REST rest_api | MCP mcp_server | utils/scheduler | utils/triggers | utils/chatops
  → execute_action → same Executor instance → flow A
AC_web_run / AC_web_run_actions → utils/webrunner_bridge/bridge.py
  → je_web_runner.utils.executor.action_executor.execute_one(["WR_*", params])
    (event_dict["WR_*"] on a WebRunner without execute_one); a failure → WebRunnerBridgeError
```

REST gate adaptation preserves check-only custom gates under shared-token auth;
store-backed servers require an authenticated user context even from replacement
gates. Registry status exposes `rbac_enabled` and omits the inactive shared token
so the GUI presents the authentication mode that the server actually accepts.
MCP role decisions also apply explicit sensitive-read overrides independently
of read-only hints; clipboard, local data, credential, external service and
microphone operations require operator authority at both listing and dispatch.

TCP client authentication marks rejection terminal before writing AUTH_FAIL. Admission
reaping therefore releases its client slot before an immediate retry can arrive, while
the separate handshake semaphore bounds outstanding cleanup and authentication threads.

Delayed work captures registration authority through `utils/rbac/deferred.py`.
Schedulers, triggers, hotkeys, watchdogs, webhooks, e-mail watchers and observers
bind that owner at dispatch, independently of the worker's ambient context.
`resolve_token` attaches the source store path to `AuthorizationContext`; dispatch
re-reads that store for current roles and revocations, without retaining bearer
tokens. Trusted local registrations bind no RBAC identity. Observer/watchdog
callbacks also use script jobs' fresh variables and per-run failure deltas,
preserving any earlier failures recorded by the caller.
CLI runs and previews seed a fresh variable scope even without `--var`.
Top-level LLM planner and FSM runs also open a scope; nested invocations reuse
an existing one so their actions and states share run-local values. Explicit
`Executor()` objects retain their own variables; FSM `context` is separate.

Structured action provenance is being built separately in `utils/action_journal/`.
Its storage foundation uses frozen schema-v1 lifecycle snapshots, pre-write
redaction, interprocess append sequencing and fsync. Readers preserve incomplete
steps and ignore bounded uncommitted tails; opaque outcomes/errors are redacted.
Explicit `journal_scope` capture wraps each executor dispatch; loop bodies keep
their step parent and local parallel/DAG workers rebind the same run metadata.
`execute_action_with_journal` opens a fresh variable scope and returns a typed
run summary. Journal types, capture/read helpers and `JournalLink` are exported
from the Qt-free facade. CLI `run --journal` retains the original record/exit
contract; `journal` validates a full file then emits a bounded, sanitized snapshot
selection. Both new CLI paths use the existing allowed-root guard and create no
history row or database implicitly. Capture starts are durable before effects;
failed actions, handled loop signals, cancellation and dry-runs receive distinct
completion statuses.
`AC_journal_capture` uses `action_journal/commands.py` to validate its nested
body and run it on the current executor, retaining variables, strictness and
loop/cancellation signals. The command opens a new capture root and restores any
outer journal. `inspection.py::inspect_journal` shares default-root confinement,
full-file validation and bounded sanitized snapshots across the facade, CLI and
`AC_journal_read`. Both commands have Script Builder forms and require
`drive_input` under RBAC. Linting walks body-bearing ordinary commands as well
as blocks. A plain outer dry-run previews the capture command without opening
a journal; Python/CLI run-level capture can record individual dry-run steps.
`action_journal/run.py` supplies frozen `JournalRunOptions` and the isolated
`execute_journal_run` service; the seven-parameter convenience API delegates to
it. Bindings retain observer/policy tuples through nested roots and local workers.
Policies intersect and are checked before linking and at each append; observers
run before a start and after durable completion, preserving pending failures.
The reader owns a closing generator and invokes count observers outside storage
error translation. MCP journal adapters use these hooks for progress/cancellation
and receive the server's live policy through `ToolCallContext`. This confines
nested journal operations; general nested action argument policies remain pending.
`MCPToolResult` keeps failure metadata outside its JSON dictionary fields. The
server sets `isError` and audit status from this explicit type while preserving
structured payloads; ordinary dictionaries cannot set protocol flags.
`gui/journal_browser.py` shares read-only snapshot inspection between Run History
and Self-Healing. Captured healing events store an optional canonical journal path
only when an actual action-step binding exists. The path plus run/step IDs identifies
the original lifecycle snapshots. Source inspection filters before limiting, validates
the whole journal and rechecks current roots around observer calls. API/AC/MCP/CLI
and GUI source views never replay recorded commands; legacy/unbound rows have no source link.
Its worker copies the submission context, refreshes deferred authority before
file I/O and uses the shared inspector. Counts are queued to GUI slots;
request generations reject old results after a target change. Closing the view
or destroying its owner requests cooperative cancellation. The existing daemon
worker relay drops callbacks after owner destruction. Selecting history links
loads metadata only; neither inspection nor link selection creates a history row.
`run_history/manual.py` creates explicitly requested manual owners around an
existing execution. It binds both an ambient journal and captures opened later,
retains caller variables/results, counts only the current counter delta and
keeps normal loop signals distinct from failures. Original signals survive a
failed finish; labels are scrubbed before insertion. The named-body command
adapter stays on the owning executor. CLI opt-in and the shared GUI
`ManualRunControls` wrap existing run paths; only a CLI-owned custom store is
closed by the CLI. Default and journal-only paths open no history database.
`utils/run_history/context.py` binds an existing history row to execution.
Scheduler/trigger/hotkey/webhook/email owners bind their own row; local parallel
and DAG workers carry it explicitly. `journal_scope` attaches an idempotent
non-owning path/run-ID link before dispatch. `run_journals` cascades metadata
when rows are pruned/cleared; external journal files are never deleted by history.
`run_history/run_outcome.py` shares interruption classification and finalization.
Cancellation bypasses ordinary executor recovery/retry and callback guards;
parallel/DAG workers preserve the original signal. History settles interrupted
attempts as `error`, without a snapshot; a failed completion preserves a pending
hard signal and leaves the history row unfinished. Explicit script `finally`
branches retain their cleanup contract. Already-started parallel branches are
joined before propagation; this is not forcible interruption of native I/O.
Facade/command/CLI/MCP/GUI and manual-run history controls remain pending.

**C. Record → edit → generate code**

```
wrapper/auto_control_record.record → OS listener (e.g. windows/record/win32_input_hook.py)
  → stop_record / record_to_json → action list
  → utils/recording_edit (trim / filter / rescale) | utils/semantic_recording (anchors for cross-machine replay)
  → utils/codegen (pytest / python / robot)
```

## 5. Extension points

**New feature or `AC_*` command**, in this order (CLAUDE.md › Feature Delivery Rules):

1. Headless implementation in `je_auto_control/utils/<feature>/` (or `wrapper/`); no PySide6; optional deps imported lazily.
2. Re-export public names in `je_auto_control/__init__.py` and its `__all__`.
3. Register the `AC_*` name in `Executor.event_dict` (`utils/executor/action_executor.py`); commands with nested
   action bodies go in `BLOCK_COMMANDS` (`utils/executor/flow_control.py`).
4. Describe its parameters in `gui/script_builder/command_schema.py` (Script Builder form).
5. Optional MCP tool: factory in `utils/mcp_server/tools/_factories.py`, adapter in the themed handler module —
   `_handlers_input.py`, `_handlers_screen.py`, `_handlers_system.py`, `_handlers_runs.py`,
   `_handlers_scheduling.py`, `_handlers_remote.py`, `_handlers_locators.py`, `_handlers_operations.py`,
   `_handlers_qa.py`, `_handlers_executor_bridge.py` (a three-line delegation to an executor function), or
   `_handlers.py` for data, text and the WebRunner bridge.
6. GUI: thin widget in `gui/`, registered by one `TabSpec` row in `gui/tab_registry.py` (module and class name, so
   it is imported only when opened) with commands exposed through `menu_actions()`; strings in every
   `gui/language_wrapper/*.py` catalogue.
7. Headless test in `test/unit_test/headless/`.
8. Update `architecture_explore.md` (and `README.md` + `README/` translations if a quoted count changes), then run
   `python test/unit_test/headless/test_doc_line_counts.py --fix`. Regenerate the typed stub with
   `python -m je_auto_control.utils.stubs.generator je_auto_control/actions.pyi`.

**Other seams**

- Runtime commands without touching core: `add_command_to_executor({"AC_x": fn})`, `utils/plugin_loader/`
  (directory scan) or `utils/plugin_sdk/` (package entry points).
- New OS backend: package `je_auto_control/<platform>/` + assembly module `wrapper/_platform_<name>.py` satisfying
  `wrapper/backend_contract.py` + one branch in `wrapper/platform_wrapper.py`; window management in `wrapper/window_backends/`.
- New accessibility / OCR / vision / llm / agent / hotkey backend: implement the base class in that subpackage's
  `backends/` directory; a null fallback keeps imports dependency-free.
- New report format: add a generator beside `utils/generate_report/generate_{html,json,xml}_report.py`.

## 6. Cross-project boundaries

| Consumer | How it uses this repo | What it relies on |
| --- | --- | --- |
| Jeffrey_RPA | Editable install of **this working tree**: uncommitted changes here reach it immediately. Single facade `JeffreyRPA/_gui_control.py`. | Top-level names (e.g. `click_mouse`, `hotkey`, `write`, `screen_size`, `get_pixel`, `post_click_to_window`) and internal paths `je_auto_control.wrapper.auto_control_window`, `je_auto_control.wrapper.auto_control_keyboard.WRITE_CONTROL_KEYS`, `je_auto_control.utils.monitor_layout` (`logical_virtual_rect`, `enumerate_monitors`), and `wrapper.platform_wrapper.keyboard_keys_table` / `mouse_keys_table` — it validates every key name a user types against the keyboard table and reverse-looks-up recorded virtual keys through it, so a name removed there becomes a rejected hotkey over in that repo. Added so it can drop its own copies: the Tesseract setup helpers `find_tesseract_cmd`, `set_tessdata_dir`, `ocr_languages` (`None` when the engine cannot be asked, `[]` when it has no language data) and `ocr_status`; `click_mouse(clicks=, interval=)` for a double-click in one call; `tween_drag` / `drag_path` pacing (`step_delay_s`, `settle_s`); `keyboard_key_name` and `wrapper.platform_wrapper.keyboard_key_aliases` for reverse lookups that never answer with an alias, plus the Windows table's OEM keys, `browser_home`, lower-case `launch_app2` and its aliases (`ctrl`, `esc`, `enter`, `win`, `pgup`, `numpad0`, ...), which match the names and codes of its own `KEY_ALIASES` / `_EXTRA_KEY_CODES`. |
| PyBreeze | Subprocess `python -m je_auto_control --execute_str <json>` / `--execute_file <path>`; on Windows the JSON string arrives double-encoded. | Legacy CLI flags; also embeds `je_auto_control.gui.main_widget.AutoControlGUIWidget` and calls `record` / `stop_record` in-process. |
| TestPioneer | Optional extra `gui = ["je_auto_control"]`; `parallel_run` starts `python -m je_auto_control --execute_file <path>`. It sets `TEST_PIONEER_ARTIFACT_DIR` for the runner. | `execute_action`, `execute_files`, `RecordingThread`; the `--execute_file` flag. | The flag's exit status, 1 when an action failed (`recorded_failures()` in `__main__.py`); the `<name>_success.json` / `<name>_failure.json` pair, written below the artifact directory for a relative name (`utils/generate_report/report_path.py`).
| WebRunner | Optional extra `autocontrol = ["je_auto_control>=0.0.224"]`; `je_web_runner/utils/autocontrol_bridge/` (`WR_ac_*`) imports this package only when one of those commands runs. | `je_auto_control.utils.executor.action_executor.executor`: `execute_action(actions, raise_on_error=True)`, whose record values it reads in action order, and `known_commands()`; its native commands send `AC_write` (`write_string`), `AC_write_secret` (`secret`, from `WR_ac_basic_auth`), `AC_type_keyboard` (`keycode`), `AC_get_keyboard_keys_table` (the `enter` or `return` key), `AC_locate_image_center` (`image`, `detect_threshold`) and `AC_click_mouse` (`mouse_keycode`, `x`, `y` in this DPI-aware process's coordinates). It refuses `AC_shell_command`, `AC_execute_process`, `AC_add_package_*`, `AC_execute_action`, `AC_execute_files`, `AC_run_agent` and `AC_web_*` by name, so renaming one of them would let it through WebRunner's bridge. |

**Guarded by** `test/unit_test/headless/test_cross_project_contracts.py`: every legacy CLI flag (short and long, run as a
real child process, including PyBreeze's double-encoded `--execute_str`), the facade names in the rows above
(Jeffrey_RPA's list is every `ac.<name>` in `_gui_control.py`, plus the names and keyword parameters added so it
can drop its own copies), the `auto_control_window` functions Jeffrey_RPA calls,
its three internal imports, the two key tables (shape everywhere, Windows key names on Windows),
`AutoControlGUIWidget`, and the executor API and refused command names WebRunner's bridge relies on. The test only knows what this table knows: when a consumer starts relying on something
new, add it to both.

**Outbound (optional):** `utils/webrunner_bridge/bridge.py` imports WebRunner's supported module
`je_web_runner.utils.executor.action_executor` lazily, for `AC_web_*` commands and `gui/webrunner_tab.py`: `executor`
(its `event_dict` lists and checks the `WR_*` names) and `execute_one`, which runs each command through WebRunner's
gates, retries and failure screenshots; a WebRunner without `execute_one` gets the `event_dict` callable directly.
The helpers send `WR_get_webdriver_manager`, `WR_to_url`, `WR_quit`, `WR_save_screenshot`, `WR_get_current_url`;
WebRunner's `test_public_api.py` guards those names and `execute_one`, and `test_webrunner_contract.py` here checks
them against the installed package. `je_web_runner` is not a declared dependency: `is_webrunner_available` looks it
up with `importlib.util.find_spec`, because importing it writes `WEBRunner.log` into the cwd, and a missing package
raises `WebRunnerBridgeError`. Any error from a `WR_*` command is re-raised as `WebRunnerBridgeError` (an
`AutoControlException`), so the executor records it instead of aborting the script.

**Wire contract between AutoControl versions:** the Admin Console and DAG remote nodes drive other hosts through
REST `POST /execute` (`{"actions": [...], "raise_on_error": bool}`), and those hosts may run an older release.
A new body field must be optional and safe to ignore — an old host drops `raise_on_error` and answers the pre-flag
`{"result": ...}`, which the client still reads as `ok: true`.

**Import-time contracts**

- `import je_auto_control` must not load PySide6; the GUI window is imported only inside `start_autocontrol_gui()`.
  `test/unit_test/headless/test_facade_import_is_light.py` also keeps `cv2`, `numpy`, `PIL`, `cryptography`,
  `je_open_cv` and `mss` off the import path.
- `utils/logging/logging_instance.py` attaches a file handler at import and sets the level of its own logger only
  (never the root logger — that would push every third-party library's DEBUG records into the host's handlers). The
  handler opens its file on the first record, and nothing logs during the import: importing writes no file at all.
  The file is `$JE_AUTOCONTROL_LOG_FILE` as read when the file is opened (so a `conftest.py` can still set it after
  the `pytest11` plugin imported the package; a relative path resolves against the cwd then), else
  `~/.je_auto_control/logs/AutoControlGUI.log`, shared by every process: appended to, rotated to `.1` past 10 MB
  only when a process opens it, and swapped for `os.devnull` with one `RuntimeWarning` when it cannot be opened.
  Consumers that must keep the log out of a shared file (a test suite) set the variable before importing;
  changing the working directory no longer redirects it.
- No module reads the home directory at import; every `~/.je_auto_control/` path is resolved when used, so a
  consumer can redirect `HOME` / `USERPROFILE` after the import (this repo's `test/conftest.py` gives each test run
  a temporary home). `test/unit_test/headless/test_state_paths_follow_home.py` scans the package for violations.

**De-facto public:** `docs/API_LIFECYCLE.md` calls `je_auto_control.utils.*` internal, but the internal paths in the
table above are used by sibling repos; treat renaming or removing them as a breaking change and check the consumers
first. `AC_*` command names and the legacy CLI flags are public too (action files live outside this repo).

Managed runtime peers additionally support the additive `POST /agent/dag` protocol and
`manage_agent_dag` / `AC_agent_dag`; optional `run_dag(..., batch_id=...)` pins whole-graph identity.
Destination task options carry only batch/graph/node tags and derived request keys. Remote calls never
forward coordinator principal/origin metadata. Existing sibling callers omitting batch_id keep their
historical path. Versioned-name checks and actual two-host evidence live in
`test_agent_dag_batch_surfaces.py` and `test_agent_dag_batch_loopback.py`; continuation is covered by
`test_agent_dag_continuation.py`, `test_agent_dag_continuation_guards.py` and
`test_agent_dag_continuation_gui.py`. Background coordination and retention share the owning service;
source-owner recovery evidence shares existing ACLs; cross-host evidence handoff remains in Progress.md.

## 7. Design constraints

- Every feature ships a headless API, a facade export, an `AC_*` command and a thin GUI tab whose commands live in the
  Actions menu (enforced by `test_actions_menu_gui.py`). → CLAUDE.md › Feature Delivery Rules › Every feature ships both a headless API and a GUI surface
- The top-level package stays Qt-free. → same section
- `architecture_explore.md` changes in the same commit as the code; counts are measured, never estimated;
  `test_doc_counts.py` and `test_doc_line_counts.py` fail CI on drift. → CLAUDE.md › Feature Delivery Rules › `architecture_explore.md` is updated with every change
- Agreed-but-unfinished work is recorded in `Progress.md` (open items only). → CLAUDE.md › Feature Delivery Rules › Outstanding work goes in `Progress.md`
- Flat exception hierarchy: every framework error derives from `AutoControlException`; assertion failures keep
  propagating. → CLAUDE.md › Coding Standards › Project-specific rules
- Validate at boundaries and reject unknown command names; servers bind `127.0.0.1` unless explicitly opted in. → same
- `AC_add_package_to_executor` / `AC_add_package_to_callback_executor` pass the package gate in
  `utils/package_manager/package_manager_class.py` before importing: `executor.allow_packages(...)` and
  `executor.set_allow_arbitrary_packages(...)` are Python-only switches, never `AC_*` commands, so an action list
  cannot open its own gate. Unconfigured, any package loads with a `DeprecationWarning` (workspace X-12).
- No `print()` or runtime `assert` in library code; lazy imports for optional and platform deps; release platform
  resources in `finally` / `with`; guard shared state with locks or queues; pin dependency versions. → same
- Size limits (cyclomatic ≤ 10, cognitive ≤ 15, function ≤ 75 lines, file ≤ 750 lines, line ≤ 120) are a review
  standard; grandfathered over-limit files are listed in `Progress.md`. → CLAUDE.md › Coding Standards › Size and complexity limits
- Run ruff, pylint, bandit and radon before committing; every suppression carries an inline reason. → CLAUDE.md › Coding Standards › Automated verification
- Measure coverage with `python -m coverage run -m pytest`, never `pytest --cov` (the pytest11 plugin imports the
  facade first), with the `[webrtc]` extra installed; never loosen `python_files = ["test_*.py"]`. → CLAUDE.md › Development Commands
- Tests cover the headless path, avoid sleeps over 1 s, are order-independent, and keep the Qt `deleteLater()`
  flush fixture in `test/unit_test/headless/conftest.py`. → CLAUDE.md › Testing
- Commit messages are imperative and explain why; attribution rules apply. → CLAUDE.md › Commit Conventions

## 8. When to update this file

- A top-level package or directory in §2 is added, removed or renamed, or an OS backend is added or dropped.
- An entry point changes: console script, `python -m` module, server surface, pytest or LSP plugin, legacy CLI flag.
- The executor contract changes (action shape, validation, error containment, signing) or the layer order in §2.
- A new extension mechanism appears or the ordered steps in §5 change.
- A sibling repo starts or stops depending on this one, starts using another internal path, the WebRunner bridge
  target moves, or the log file name or location changes.
- A hard rule in CLAUDE.md is added or changed.
- On every edit, refresh the "Last verified" line. Module-level changes belong in `architecture_explore.md`, not here.

Workflow specs compile four reviewed templates into pinned skill actions. Receipt-backed captures
and allowlisted text transforms cannot select commands or widen scope. A separate local-files target
uses the same helper protocol without desktop input; semantic desktop steps refuse ambiguous controls.

Presence-only Win32 hooks live inside the owned native helper. A control-notice channel remains
independent of action replies; the host requests pause on a separate controller thread before retiring
the input owner. Persistent monotonic budget high-water marks prevent clock rollback or restart resets.

TaskEvidence atomically links the runtime task with the existing HistoryStore schema in the same
SQLite transaction. Append-only journals mirror receipt certainty; reports summarize per-row outcomes.
Owner testimony reconciles uncertain attempts without automatic resume. Retention only removes validated
generated cache files and matching private metadata; external journals and user outputs remain separate.

AgentTriggers persists captured task templates, owner provenance and bounded schedule/file/event
bindings. Event/request deduplication and task creation share one SQLite transaction before WorkQueue
delivery. Trigger and lease watchers have independent owned threads. Canonical root snapshots and
operation-bound vault guards follow worker handoff; view cancellation only detaches from service work.

Input ownership writes a private, fsynced per-resource crash witness before native dispatch and input ACK. An unfinished witness blocks new owners across databases. Explicit host-only recovery requires a review note and a trusted no-held-input probe, never replays persisted input or signals persisted PIDs, and does not reconcile/resume the old task. POSIX input helpers monitor their actual parent and retire only their own live session group. Approved document handoff runs outside the input helper tree, so user applications survive normal task cleanup; bounded, preapproved focus steps wait for scoped windows. Observations also expire against a host monotonic clock. Native desktop/device acceptance remains unverified.

Managed skill candidates store sealed task scopes, typed explicit data slots and source-task provenance in the runtime SQLite database. Recording requires confirmed receipts and independently verified success. Validation creates a distinct pinned task; publication requires that exact trial's successful completion, an explicit review note and a compare-and-set version. Semantic selector repairs create new candidates. In-flight tasks retain their original version/digest; arbitrary pointer receipts are not guessed into semantic skills. Legacy mutable SkillLibrary behavior is preserved.

Accepted tasks, trigger templates and skill trials retain live origin policy references. A private witness contains only current root ceilings; missing/revoked/corrupt witnesses fail closed. Authenticated local HTTP forwards the current caller's additional restrictive ceiling without granting identity or capability. Every operation checkpoint and lease maintenance rechecks roots. MCP client roots and asynchronous roots refresh are session-local; stale replies cannot renew retired authorities. Static host policies persist until replacement, while retiring client-supplied root authority revokes its references. HTTP client roots do not overwrite the shared resource provider's configured workspace. Workers/maintenance run in fresh contexts, shutdown tracks actual in-flight deliveries before lease acquisition, and unstarted queued work remains durable.

Legacy MCP wrappers and parallel/local DAG workers preserve the origin intersection. Metadata is resolved lazily for task-aware dispatch and worker handoff, and a failed policy publication invalidates its previous witness.

Managed action references resolve observation-local element centers or rendered image pixels into native coordinates only after identity/freshness/fingerprint checks. Explicit coordinates cannot conflict with a reference; invalid/disabled/out-of-frame targets fail before preparing an action. SQLite atomically links grounding metadata to each prepared receipt, including requested arguments, frame ID/hash and non-image geometry; reports expose the same provenance. Local-model schemas carry an observed_target extension while legacy executor signatures stay unchanged. AgentObservationStale round-trips over local HTTP, and bounded pre-dispatch replanning requires an adapter's explicit can_reobserve guarantee. Native adapters deny it while any owned input or unsettled operation remains. Native acceptance stays unverified.

Native helper protocol 1 includes a read-only bootstrap handshake bounded to fifteen seconds. Configure/observe/perform retain their configured action deadlines; cleanup retains its own bound and ownership cannot transfer before retirement. Image-point grounding verifies actual bounded JPEG pixels against the advertised rendered dimensions.

Managed mouse presses normalize button ownership and confirm the actual cursor before input. Windows pointer checks reject foreign overlays. Vision renders the exact scoped window into cleared private GDI storage, rejects geometry changes and releases resources even on rendering/read failure. There is no desktop-crop fallback. Fake-native tests cover these paths; native acceptance remains unverified.

The Agent tasks view groups task scope, workflow settings, triggers, skills and recovery into separate pages. Its observation page lists read-only elements and shows a validated, strictly masked JPEG at one rendered pixel per logical widget pixel. Selecting a row or image point only edits a frame-bound action request; Actions -> Perform observed action sends it through the shared task API. Switching tasks clears the preview, and late replies cannot replace the selected task. A new frame requires reselection before an old reference can be sent. Closing the view only detaches its requests.

Managed workflow waits (workflow_wait / AC_workflow_wait) poll only exact scoped control values or states, with cancellation and a deadline capped by the action budget (default five seconds, maximum sixty). They never replay a write or submit. Fixed skills require all previous receipts to match the pinned sequence before continuing, including after resume; autonomous model loops retain stuck detection. New form/transfer drafts refuse an already-matching confirmation before submit and wait for a fresh transition afterward. Batch configurations may provide new_record_selector to reset each record; confirmations prove the configured UI transition, and transaction-specific receipt values should be used when available. Archive drafts also re-read the exact reviewed manifest and current file digests at finish (one-megabyte manifest and sixty-four-megabyte total evidence limit).

AgentHumanReview identifies an unsaved-content or unknown-dialog gate. It persists waiting_user and retires input ownership, including for external observe requests; explicit resume still rechecks the gate. Windows detection uses native dialog/disabled-owner evidence and known English/Chinese/Japanese unsaved labels. Workspace tasks also pause for leading/trailing asterisks in document titles; a window entry may supply unsaved_selector and unsaved_value for an application-specific indicator before layout changes. These checks do not infer every application's dirty state. Recognized standard file pickers use a context-local driver on the existing AC_handle_file_dialog executor: exact unique title, same PID, confirmed foreground and canonical rooted absolute paths. UIA control patterns must belong to the actual owned root window, even when another window shares its PID. All behavior has fake-native/loopback coverage; actual platform acceptance remains unverified.

Host-reviewed targets use AgentTargetProfile and manage_agent_target (AC_agent_target; register/get/disable/enable). Names and configuration are immutable; desktop/file adapters are currently supported, and unimplemented kinds or executable settings are rejected. Tasks pin the host profile digest and cannot expand its tools, applications, roots or network origins. Availability persists across restart and is checked at dispatch; disabling requests pause/cleanup, while enabling requires explicit task resume. list_agent_targets / AC_agent_target_list / CLI agent-task targets expose passive metadata with readiness=not_probed and native_evidence=not_recorded. Full configuration requires manage_hosts; CLI agent-task target and the GUI Host targets page use the same service. Live anonymous MCP tool sessions have operator authority across direct and legacy wrapper calls; MCP host management requires an authenticated administrator. Trusted direct Python callers remain unchanged. Browser automation belongs to WebRunner (je_web_runner), with D:/Codes/WebRunner as the development source; the managed browser adapter is not part of these target registrations.

Existing browser automation, including open_path(URL) and AC_open_path, delegates to WebRunner (Python package je_web_runner). URL plans now report backend=je_web_runner; callers inspecting the previous webbrowser descriptor should use the new value. Signatures and local-file opening stay compatible. URL execution requires the configured WebRunner project and propagates WebRunnerBridgeError when unavailable, without opening an OS browser as a fallback. The development source is D:/Codes/WebRunner. Planning and injected-opener tests remain usable without that package; browser protocol support is determined by WebRunner and its selected browser. Existing dedicated browser GUI/MCP/AC paths and recorded WR_* actions share the same bridge.

MCP metadata discovery uses ToolIndex detached snapshots of the shared registry. Search returns bounded summaries; single-schema lookup returns a detached descriptor. Both refresh current authority. ToolCallContext carries an inert catalogue callback so server queries include that registry's read-only filter and current plugins. Python/core/AC/Builder/CLI use the default catalogue; Diagnostics Actions expose the same passive API without starting a transport. Progressive session views remain pending.

MCP ToolView owns session-local enablement and at most eight five-minute opaque cursors. Cursors retain names/offsets, not duplicate schema payloads, and bind visible names, caller scope and registry metadata digests; stale snapshots fail explicitly. The disclosure server mixin filters current authority and host read-only ceilings before the original argument/root/env/rate-limit/confirmation/invocation path. Closing or reconfiguring a view retires it permanently. Stateless requests use a fixed initial profile and keep no session state. CLI/AC stdio settings and Diagnostics configuration preview share headless profile validation. Legacy server-module stdio exports delegate to stdio.py, avoiding further growth of the dispatcher.

MCP async handoff copies the accepting context and explicitly captures its connection writer/notifier, exact ArgumentPolicy and ToolView. Deferred identities still refresh before invocation. Closed views and retired PathPolicy validation reject late work without recreating connection entries. Async stateless requests capture an ephemeral fixed view. Each HTTP transport owns a detachable tool-list sink that snapshots live session streams, broadcasts registry changes and targets availability changes; delivered session identities suppress duplicate request-local notifications. Stream claim and header publication are atomic under the writer lock. The benchmark uses only registry metadata and records warm in-process JSON-RPC sizes/timings; no automation tools run.

Managed browser profiles bind a private NativeDesktopTarget helper using a digest-specific resource lock and no desktop activity probe. browser_target.py lazily opens the WebRunner ManagedBrowserSession API, retains the identical scope across readiness checks and flattens frame DOM nodes into bounded indexed observations. browser_commands.py binds the private SDK session for shared guarded leaf dispatch only; six AC_browser_* tools expose no engine, profile, script, argv, native input or file-transfer escape. Host and task origin grants intersect before startup. observation_refs/model_tools resolve DOM indexes alongside existing pointer references, and GUI selection only edits requests. Browser cleanup is acknowledged even with an empty native input ledger before the host reaps its owned helper. Cross-source contracts target WebRunner feat/managed-browser-sessions at c082dc3; no shared environment installation or native acceptance is performed.

browser_workflows.py extends the existing workflow compiler with an explicit browser backend for batch_form/transfer only. Shared rooted CSV/XLSX readers and capture transforms produce closed WebRunner actions; no session is opened during preview. Each field has exact readback, each save has a non-stale baseline plus a bounded confirmation poll. browser_wait forwards the remaining poll deadline to the SDK, probes visibility before a read, rejects late matches and never retries an effect. Catalog, model, MCP, Builder and GUI preview share the schema/compiler. Semantic browser reads count as independent skill evidence. Unsupported browser workflow kinds fail rather than choose desktop input.

Browser consumer compatibility is explicit: require integer WebRunner ManagedBrowserSession.contract_version=1 before creating the policy/session. Preserve trusted SDK/dependency compatibility errors through readiness, while containing raw browser errors. Match UTF-16/Unicode limits for arguments and offline workflow data before effects. Companion SDK 575e5d2 rejects over-limit strings before IPC and never returns truncated exact-read evidence; native acceptance remains unclaimed.

browser_verification.py validates closed user-pinned URL/text/value/visibility criteria and requires an existing browser-read/origin grant. The common finish verifier accepts an optional host-only browser callback; NativeDesktopTarget forwards only the pinned clause to NativeWorker verify_browser on the same owned session. BrowserTarget checks clause membership, fresh page origin and SDK policy before guarded exact reads; URL comparison uses current SDK state. No observation preview or previous receipt can supply completion. Invalid/unavailable replies become unknown, while cancellation/authorization/human-review exceptions retain control semantics. GUI Actions drafts a passive scope example through the existing task model. Shared browser URL validation preserves SPA fragments and rejects credentials/port zero.

browser_transfers.py reads bounded rooted regular-file snapshots and delegates byte uploads/URL downloads exclusively to je_web_runner. SDK transfer version 1 is required before startup only for transfer grants; existing seven core commands retain base contract version 1. Download streams reuse rooted workflow_files atomic publication; SHA256 is mandatory for reuse. Explicit DOM link reads can use observation indexes, while URL downloads cannot. browser_workflows compiles query/link/download/manifest actions with independent file evidence. All three new public commands share root/api.core/executor/MCP/REST/CLI/Builder/model surfaces. The GUI Actions file example only fills reviewable profile/workflow/action data. TaskPolicy rejects expanded navigation/download origins before dispatch; cancellation/authorization errors are preserved through SDK containment.

Runtime client contract closure: request_json does not copy local principal/origin metadata merely because a bearer token exists. AgentRuntimeClient explicitly selects loopback-only delegation; its metadata destination is validated again before forwarding. api/__init__.py mirrors core through explicit PEP 484 aliases, including the managed runtime recovery/skill surface. The command stub generator rejects unresolved postponed annotation identifiers using AST inspection and its existing Any policy. BudgetClock samples both clocks only after BEGIN IMMEDIATE, preserving high-water/rollback protection while serializing concurrent readers correctly.

target_continuity.py rejects retained finite skill prefixes without their original live browser context. Runtime activation asks the target before broker acquisition/helper startup; BrowserTarget checks its pinned SDK session and NativeDesktopTarget checks its profiled browser channel. Proven failed/not-applied attempts do not consume a prefix. Human review retains receipts and requires a reviewed new task rather than reconstructing draft/authentication state from history. External observation and uninterrupted skills keep their existing lifecycle.

DesktopTarget now checks its live pinned scope before trusting a retained finite prefix. NativeDesktopTarget applies the same pure target_continuity validator to host-profiled desktop/browser targets and the built-in local desktop, before starting another channel; file profiles retain persistent evidence recovery. A fake semantic application proves that edited fields cannot be submitted after scope cleanup, while an uninterrupted flow still succeeds.

Browser environment contract: host-only settings.helper_python selects a local absolute interpreter and preserves virtualenv executable symlinks; task options cannot override it. target_factory supplies fixed -I/-u/-m worker arguments for that interpreter. helper_environment.py probes dependencies in a separately owned, concurrency-bounded helper, without input-resource acquisition or reuse of a configured channel. NativeWorker accepts probe_browser only before configuration. browser_environment.py reuses the SDK readback/transfer contracts and delegates runtime imports to je_web_runner.webdriver.playwright_wrapper._require_playwright(); the returned factory is never started. This existing private SDK hook is now a cross-project dependency contract. Target management exposes probe on shared surfaces with host authority, keeps long probes outside the runtime mutex and publishes only bounded timestamped metadata. Python dependency success never establishes native/browser execution readiness or enables targets.

Remote-device prerequisite: remote_journal.py binds a physical platform/device identity (not an app,
profile or endpoint) to durable controller/sequence begin/end events. OwnedChannel ACK follows fsync.
remote_target.py owns a fixed host-selected helper, requires remote_effect_protocol=1, denies writes
outside perform and retires the local writer before release. An unmatched remote begin retains the OS
resource and durable quarantine; desktop InputJournal recovery refuses remote witnesses. Host-trusted
recovery first records an epoch after all old writers retire, then requires a later epoch invalidating
old commands without replay. No ADB/WDA proof is assumed. These are internal adapter prerequisites;
Android/iOS factory profiles, real device-control providers, public surfaces and native readiness remain unavailable.

android_transport.py is an internal ADB smart-socket prerequisite using an explicit existing loopback
server. It shares android.adb_client._parse_devices, selects a numeric transport per connection and
requires bounded shell-v2 stdout/stderr, an exact exit packet and EOF. One deadline and live checkpoints
cover framing; failures preserve control exceptions and redact remote diagnostics. No CLI invocation,
server management, reconnect, command retry or legacy shell fallback occurs. Server restart can reuse
transport IDs. The session/compiler recheck physical device/boot/app on the command connection and
construct finite tools; real device fencing and public managed wiring remain required before Android is advertised.

Android identity/proposal boundary: android_scope.py validates bounded serial/boot/default-display
window/activity evidence and discards raw dumps. android_session.py selects one exact ready endpoint,
shares a deadline and atomically pins boot after live checks; it never launches an app or adopts a new
boot. android_commands.py compiles only four finite existing input names with closed arguments and
same-connection pre/post identity guards, sentinel-preserved serial/boot and labeled focus evidence,
literal text, fixed results
and the transport byte limit. Proposals carry input_authorized=false. Checked input evidence additionally
needs trusted presence/device-fencing/capture providers and managed target wiring;
no managed device profile, SDK execution authority or new catalog command is advertised.

Android native input evidence: android_input_windows.py decodes pinned front-to-back window records
and drops foreign names; android_geometry.py proves complete half-open pointer-path coverage using
exact rational intervals. android_input_evidence.py checks current focus, owner/channel bindings,
quiescent input queues and both keyguard views. Stable current routing/queue and keyguard digests omit
history/old ANR data and are rechecked by android_commands.py before input on the selected connection.
AndroidDeviceSession.inspect_input/propose_checked share the deadline and preserve authority revocation.
Evidence remains input_authorized=false; global monitors, physical activity/held inputs and device
fencing require separate trusted authorization before any managed Android target is advertised.

Android action-result boundary: android_action_result.py accepts only complete v2 phase/exit pairs
from ManagedAdbServer.shell. android_commands.py contains pre/post guard exits in separate subshells;
only complete pre-input refusal proves this command did not invoke input. Input failure and post-input
refusal retain possible effects; partial/legacy/malformed evidence stays unknown. A returned-input
phase is not an idle, retirement, recovery or task-completion certificate and never permits replay.

Owned remote SDK boundary: remote_worker.py serves a fixed host factory after parent_watch starts,
with closed bounded RPC, typed JSON scope/owner pins, refreshed store-backed authority, deadlines and
sticky physical takeover. RemoteDeviceAdapter supplies read-only preparation and trusted live checks;
remote_effect.py invokes one PreparedRemoteAction only after durable begin ACK. End requires an exact
device/epoch settlement proof of released input and no queued remote writes; return values never imply
settlement. NativeRemoteTarget forwards owner provenance and physical takeover without reader self-join.
Errors retire the helper and preserve unknown remote effects, with no replay or desktop input cleanup.
This is an internal SDK seam; the WDA adapter, real proof providers and managed profiles remain open.

Checked Android SDK bridge: android_adapter.py requires one fresh metadata-only observation per action,
rereads the full native proof and consumes it after preparation. android_control.py defines explicit
host-only AndroidCommandLease/device-fence contracts with no default provider. After durable begin ACK,
android_session.dispatch_checked recompiles the exact finite body and rejects unchecked/altered/foreign
session or boot proposals before a single shell-v2 call inside the trusted fence. Settlement separately
binds the random request ID, boot, device and epoch; shell phases cannot prove remote input retirement.
The provider must actually suppress old device writes on human takeover, expiry or cancellation; a
host-only lock/context manager or local helper exit is insufficient. No production provider is assumed
and no default managed profile or native readiness is advertised.

Android semantic readback: android_hierarchy.py streams defused, bounded single-window XML against the
proven native snapshot/display and a fresh host reader request. Only explicit host path grants reveal
non-sensitive/read-only text; XML never grants authority. Password/editable values and protected
descendants are masked, foreign subtrees excluded, bounds/indexes/booleans closed and hit tests gate
element actionability. android_adapter.py brackets capture with native checks and rereads semantics at
preparation and inside the device fence. Raw XML and keyed witnesses stay private; public random
revisions remain stable for unchanged observations but refresh on changes/reversions and actions/no-ops.
observation_refs.py resolves actionable Android element indexes in android_display coordinates only.
Existing observe/act/finish and screen criteria provide fresh reviewed-label readback; verification.py
keeps missing/masked absence and malformed capability/elements unknown rather than accepting empty
metadata as a complete screen. Protected field-value verification and richer partial predicates remain
open. Readers are explicit trusted host callables with no CLI/SDK startup or capture fallback; standard
UiAutomation default connection can suppress other accessibility owners and is not silently invoked.

Built-in screen coverage: targets.py marks bounded/masked desktop controls as partial semantic text and
bootstrap as unavailable; browser_target.py marks bounded WebRunner controls/frames as partial, and
file_target.py declares no semantic screen evidence. verification.py ignores protected/hidden/untyped
labels for partial text checks and combines clauses with passed/failed/unknown semantics. A known
contradiction fails the conjunction; missing evidence cannot pass it. Other partial screen predicates
remain unknown. Legacy custom sources without flags keep their prior contract; exact browser checks
still use pinned fresh SDK reads rather than previews. No new command or GUI-specific branch is added.

Reviewed successors: task_recovery.py is a trusted runtime collaborator with a closed preview/create
protocol. It locks the source task, refreshes owner/operator authority, binds approval to the exact
task/receipt/review snapshot and preserves the normalized scope while allowing reviewed goal/actions.
Unknown effects require reconciliation; indexed/coordinate actions and unavailable historical captures
need fresh semantic reconstruction. store.py atomically inserts a queued task and unique source link,
independently of caller request-key namespaces. Retries reuse that child and never copy action receipts or skill publication
authority. Runtime metadata exposes provenance; retention.py preserves source evidence until the child
is removed, retaining a no-resurrection tombstone in the meantime. A delegated source cannot resume. routes/client/api, the shared command
catalog, REST capability map and CLI expose the same protocol. The thin Recovery editor accepts explicit
Actions approval, clears selection-bound drafts and ignores late source replies; it never submits a
preview through the ordinary task form or cancels service work on close.

Dynamic recovery: task_recovery.py separates finite-prefix reconstruction from external/local-model
replanning. Dynamic preview ignores dormant action arrays and exposes no guessed completed count or
remaining steps. Its review_template has a blank goal and actions; explicit approval must supply a new
nonempty goal within the original mode/options/authority/completion contract. GUI Recovery presents
this template without submitting the ordinary task form. BackgroundTasks leaves external children for
caller-driven observe/act, while Ollama children construct a new backend and child-only recent history.
No model API is called by preview. Existing source snapshots, owner/operator checks, unknown-effect
reconciliation, atomic unique links, parent retirement and retention remain shared across all modes.

Explicit successor authorization: recovery_authorization.py prepares a source-snapshot-bound digest
from original roots, surviving source policies and current caller authority. Policy roots are clipped
before disclosure; only unavailable old references may be replaced and approved roots may only shrink.
task_recovery.py keeps ordinary recovery strict, revalidates all other scope, and checks the review
again before creation. origin_policy.py reads current authority strictly without rewriting old files.
store.py inserts authorization evidence with task/recovery in one transaction. Its authorization row
references the recovery tombstone, so child pruning retains proof until source pruning cascades it.
Public recovery metadata exposes actor/context/approved roots. The same four-operation protocol flows
through routes/API/catalog/CLI/Builder and separate thin GUI Actions; only explicit creation dispatches.
Input lease/quarantine, source receipts and source status remain independent of authorization renewal.

Skill authorization: skill_reauthorization.py reuses bounded origin review to bind a current published
candidate to a new draft. The full plan and parameter schema stay fixed. task_skills.py inserts draft
and agent_skill_authorizations linkage atomically, with concurrent-caller deduplication and a latest-version
check inside the write transaction. Provenance holds actor/context/approved roots. Existing trial/pin/
publication contracts require fresh validation and explicit next-version acceptance; old candidates
and task pins never mutate. Shared operation enums reach API/catalog/CLI/Builder and thin GUI selectors.

Trigger authorization: trigger_reauthorization.py binds approval to the source row, streamed event
digest and effective origin intersection. trigger_registration.py shares bounded future-event insertion
with ordinary registration. Creation atomically stores one replacement/proof, retires the source and
seeds trigger_history.py's lineage ledger. Store event binding extends the original task/local-event
transaction with a lineage receipt. Shared event/pending lookups span all generations; inherited task
IDs are query-only duplicates and cannot trigger background restart. Original task provenance remains
unchanged. Ancestor deletion retains history; explicit removal of the whole family clears proofs and
tombstones. GUI review prepares a blank-note request, checks trigger selection for late responses and
uses the same explicit operation selector; no business logic moves into Qt.

Managed batch foundation: dag/batch_contract.py normalizes closed all-managed graphs, hashes complete
topology/contracts and derives batch-bound task tags/keys. agent_runtime/dag_batches.py persists owner,
host fingerprints, graph and per-node claims in the runtime database. Registration never dispatches;
begin is a one-shot registered-to-running transition. dag_batch_recording.py fences dependencies and
independently checks destination lookup/spec-match/completion/retirement before confirming a receipt.
dag/batch_execution.py wraps the existing pool/managed waiter: claim before possible delivery, record
bounded identity and derive final state from durable phases. Lost replies remain unknown/claimed.
Managed host connections capture matching endpoint/credentials once; fingerprints never enter destination
specs, and remote transport still omits local principal/origin witnesses. New manage_agent_dag and
AC_agent_dag share API/MCP/REST/CLI/Builder; run_dag gains optional batch_id. DAG GUI registers/reads
explicitly and guards graph/batch selection before presenting replies. Explicit whole-graph continuation,
service coordination and settled-batch retention share these records; old graphs are not silently adopted.

## Local DAG evidence-only grants

Existing recovery children held by another caller can provide completion evidence to their
original local DAG through an explicit revocable handoff. In `manage_agent_recovery`, use
`review_handoff` with the final `task_id`, `batch_id` and `node_id`; an authorized manager then calls
`create_handoff` with the same IDs, returned `handoff_review` as `review`, and a nonempty `note`.
The service derives the recipient from the real original admission. In a `review_continuation`
successor decision, explicitly include `handoff_id` alongside `node_id`, `action` and `task_id`, then
review and approve the whole continuation. At most sixteen real recovery links are supported,
including a privately admitted permanent read-only final verifier. Ordinary task ownership remains.

`get_handoff` and `revoke_handoff` take `handoff_id`; `list_handoffs` takes `batch_id` and `node_id`.
Issuance and consumption refresh actual owners, admitting reviewers, issuing-session root witnesses,
current consumer ceilings, fixed scope, effect snapshots, independent completion and retirement.
Approval, start and late dependency validation recheck consent; revocation or evidence loss blocks
adoption. Grants expire no later than the earliest retained terminal witness's existing thirty-day
deadline. Returned data contains bounded IDs, hashes and status, without private task arguments,
captures or principal-store paths. No ordinary task-read/input access, ownership transfer or replay is
granted. Cross-host and non-DAG handoff contracts remain outstanding in `Progress.md`.

The Agent Tasks Handoffs page has an operation selector and JSON editor; Actions prepare review,
create and revoke requests without dispatching them. Five editable `agent_handoff_*.json` examples
cover review/create/get/list/revoke. Python, AC, CLI, authenticated MCP, REST and Builder use the
same recovery operations. These checks establish contract and owned-file behavior; deferred native
desktop, browser, device and 24-hour acceptance still require their own evidence.

## Atomic read-only completion authorization renewal

When original origin references are expired or unavailable, explicitly call
`manage_agent_recovery("review_completion_authorization", {"task_id": "<source-id>"})`.
Review the server-derived `verification_spec` and retained/replaced/current origin context, then call
`create_authorized_completion` with the same `task_id`, returned `snapshot`, `authorization_review`
and a nonempty `note`. Optional `owner_policy="source_owner"` requires the returned `ownership_review`
at creation. Callers cannot supply a replacement verification spec. Existing live constraints stay;
new roots intersect the original ceiling, prior reader ceiling and current session. Ordinary
completion review does not replace this explicit consent for an already renewed reader.

The child is permanently read-only. It independently checks current conditions against the actual
confirmed original effects, without input, replay, restoring captures or modifying old witnesses.
Source/effect snapshots, real owners/reviewers and original DAG admission are rechecked. Task admission
and final completion each revalidate inside their own SQLite writer after SQL; changes roll back.
At most sixteen actual recovery links are supported. A retired successful reader may be explicitly
renewed again, retaining its previous narrower ceiling and all still-valid inherited restrictions.
Changed source/effect evidence remains refused and must not be silently repaired by scope renewal.

Historical `get` preserves succeeded state; loss of renewed authority makes its current
`completion_contract` zero and `completion_authorization` unavailable. DAG adoption and late dependency
validation then refuse that evidence. Malformed/missing renewed read-only markers fail before helper
startup. Recording with `completion_task_id` uses the approved restricted scope and original semantic
actions, but the draft still needs its own fresh validation trial. Renewal does not publish an expired
candidate or renew a published skill grant. Existing skill reauthorization remains separate.

Python, AC, CLI, authenticated MCP, REST and Builder share both operations. The Recovery page exposes
two explicit Actions using its selected task, owner policy and request editor. Editable examples are
`agent_completion_authorization_review.json` and `agent_completion_authorization_create.json`.
Remote read-only providers, cross-host handoffs, actual application
state restoration and deferred native/device/browser/24-hour acceptance remain in `Progress.md`.

## Explicit renewed-reader completion handoffs

Existing `review_handoff` / `create_handoff` can explicitly transfer completion evidence from
a privately renewed, permanently read-only reader to its real original local DAG. Select that reader's
task ID and the actual original batch/node. The service derives the proof; callers cannot supply a
policy, ownership override or authorization bundle. Ordinary handoffs keep their existing rules.

The preview's `evidence.completion_authorization` contains the completion task/review, a bound review
digest, approved-root count and replaced/retained/current origin IDs. It omits private principal paths,
action arguments and captures. Set creation's `review` to the returned top-level `handoff_review`, then
provide a nonempty `note`. Every actual task keeps its reviewed ceiling; all live historical restrictions stay, unavailable
references are explicitly reviewed, and the issuing session's additional constraints remain live.
The grant uses the exact already-verified reader roots. A different intersection requires another
real completion review and verification. The consuming session/profile still applies its own limits.

At most sixteen actual recovery links may mix previously reviewed executable successors and private
readers. A succeeded intermediate reader needs actual private historical scope and retirement proof;
an ordinary succeeded source does not gain that exemption. No helper is launched or input replayed
while granting or adopting evidence. Old source state, witnesses, receipts and all task owners stay.
The original owner receives only the bounded completion projection, without ordinary access to the
other caller's task. Revocation or lost authority blocks adoption and late dependency validation.

Original accepted-request hashes, raw submission witnesses, private admission, graph, owners/reviewers,
all real source/child snapshots and the leaf renewal remain bound. Reads and post-write checks use
the same SQLite writer, including uncommitted changes; mutation rolls back admission/grant creation.
An inherited `dag_batch` option is not admission: a bounded real recovery chain must resolve the actual
original request and admitting identity without creating a replacement admission row. Earlier ordinary
completion binding hashes remain compatible. Each historical task retains its own policy review;
combining history cannot bypass the normal sixteen-live-origin limit or any original root ceiling.

Exact active retries retain their note and ID; revoked IDs never reactivate. Restart and adoption
preserve the earliest retained terminal witness's thirty-day deadline. Historical get/list/revoke stay
available after an origin expires, while that history supplies no usable completion or input grant.
Python, AC, CLI, authenticated MCP, REST and Builder share the five existing operations. Existing
Handoffs Actions and its JSON editor/result view show the explicit renewed review without dispatching
consent automatically. Cross-host handoff, remote readers, actual application/device
providers and deferred native/browser/device/24-hour acceptance remain in `Progress.md`.

## Explicit task-source completion evidence handoffs

The five existing handoff operations also accept a real non-DAG source task:

- `review_handoff`: supply `source_task` and the actual final evidence `task_id`.
- `create_handoff`: add the returned top-level `handoff_review` as `review`, plus a nonempty `note`.
- `list_handoffs`: supply `source_task`; `get_handoff` and `revoke_handoff` still use `handoff_id`.

Task-source fields and DAG batch/node fields are mutually exclusive. The service resolves persisted
grant IDs to their actual storage family. Original DAG ancestry must use its real batch/node route,
even if a later read-only reader dropped its `dag_batch` option. No synthetic DAG node or admission
is created. Ordinary standalone tasks need no invented submission witness or idempotency key;
any actual accepted request is bound and rechecked on the same SQLite writer.

Select `handoff_id` explicitly in existing skill operations. `record` uses a separate verified reader
through `completion_task_id` and creates a draft which still needs its own new validation trial.
`accept` with `completion_task_id` keeps the actual original candidate's validation task.
`review_execution` and its matching `accept` may select an actual `execution_task_id`; add
`completion_task_id` when the final granted evidence is a separate reader. The service verifies
the exact complete original semantic action plan, real execution IDs and independent final criteria.
A reader never becomes an execution task or a substitute validation trial.

The grant yields only a private bounded evidence view. Original task owners, source state and
receipts remain; ordinary get/list/observe/act/resume access never expands. Granting or adopting
launches no helper and replays no input. Real source/child snapshots, original optional requests,
actual owners/reviewers, retired input and every live historical origin remain checked. New recorded
drafts retain both issuing and consuming session ceilings. Unavailable restrictions require actual
private completion renewal; matching hashes or caller-authored scope flags cannot replace it.
Read-only evidence adoption does not renew a published skill's original input authorization.

At most sixteen real recovery links include source ancestry and the forward granted chain. Earliest
retained terminal evidence expires after thirty days; anchoring at a later reader cannot extend an
older ancestor. Same-writer post-insert and exact-retry checks honor revocation tombstones for both
DAG and task grants. Source/request/role/origin/revocation changes roll back grant creation, draft
recording or publication. Revoked IDs never reactivate. Historical get/list/revoke after an origin
expires expose bounded IDs and hashes, not continued completion or input authority.

The Handoffs page explicitly selects original local DAG or original task when preparing JSON.
Three skill Actions prepare recording, publication or execution review with a handoff placeholder;
they do not issue consent or publish automatically. Python, AC, CLI, authenticated REST/MCP and
Builder share the same operations and actual caller identities. Editable requests are
`agent_task_handoff_review.json`, `agent_task_handoff_create.json`, `agent_skill_recording_handoff.json`,
`agent_skill_completion_handoff.json`, `agent_skill_execution_handoff_review.json` and
`agent_skill_execution_handoff_accept.json` under `examples/`.

Cross-host handoffs, remote readers, actual application/device providers, deferred native
and twenty-four-hour acceptance, and unresolved HTTP409/bootstrap issues remain in `Progress.md`.

## Retained original browser completion

Stopped browser tasks with confirmed effects can now use the existing completion review and
skill workflow with their actual original WebRunner context. The owned worker permanently freezes
SDK input/network before its input journal and lease release; the runtime retains at most 16
contexts for at most 300 absolute seconds, starting before detachment. Preview/new admission probe that exact effect task's live SDK view.
The verifier borrows it for fresh bounded DOM/value reads, without configure, input ACKs, transfers
or another browser/helper. Retirement, capability probes and cleanup deny nested tools and native input.
Same-profile tasks keep separate contexts. A saved context ID grants nothing.
Private completion authorization can explicitly renew the verification scope within the original
ceiling while the original input specification stays immutable. Expired input origins grant no reads;
bounded private custody alone is not authority. Removed owners, disabled targets, changed sources,
expiry and failed reads invalidate contexts. Confirmed process reaping is required to free ownership;
failed cleanup stays tracked. Restart cannot restore a page. Network-retired DOM is not new server data.
Existing Python/AC/MCP/REST/CLI/Builder and GUI Actions share the same review requests. Skill recording
keeps original actions; publication requires its own actual validation trial and selected completion.
See `examples/agent_browser_retained_completion.py`. Cold browser-prefix reconstruction, remote
readers, production deployment and deferred native/browser/device/24-hour acceptance remain open.

Cross-project helper contract: WebRunner readonly_contract_version=1/freeze_readonly retains the
original SDK context. The configured built-in NativeWorker adds browser_readonly=1 to bootstrap
protocol 1; initial/legacy bootstrap remains compatible. Host detachment probes this actual channel
before retirement; absent/nonexact availability markers close normally without issuing a reader.
Metadata alone is never retirement evidence: actual SDK contract/input_supported/network_retired/
context_id proof is checked before releasing the original input journal/resource and broker lease.
browser_retirement.py validates descriptions and rejects input/tool dispatch; browser_readonly_scope.py
checks a separate host-admitted no-action scope against original tools/criteria/settings/root ceiling.
bind_browser_reader never changes input configuration, original owner or SDK page. Current origin
witnesses are supplied by private completion admission, validated live, and cannot revive old input.
retained_browser.py owns six-field entries, capacity reservations, absolute lifetime and reaping.
retained_browser_runtime.py joins existing broker cleanup/private effect admission/maintenance;
retained_browser_target.py owns a single transient read borrow and never launches/configures input.
NativeDesktopTarget reports original channel ownership; completion_recovery composes effect eligibility
through its existing policy imports. Runtime injects the current-operation getter. NativeWorker supplies
the actual policy validator after immutable reader-scope comparison, keeping BrowserTarget independent
of host policy imports. The audit also rejects added import edges inside existing cyclic components.
NativeWorker keeps the original input spec while scoped reads use the exact approved verifier;
both host and helper reject input ACKs, executable tools, transfers and ordinary reconfiguration.
No new public command, serialized session grant, alternate browser engine or dependency is added.

## Idle work queue polling

Idle background workers check empty work queues without reserving a database writer, reducing
contention with task status and completion transactions. A nonempty hint still requires the original
transaction to recheck and claim the work. Claim generations, stale-work recovery and retry limits
remain enforced; task and transport deadlines are unchanged.

Lease maintenance binds expiry/revocation stops to the actual input owner and generation in the
same stop transaction. A delayed watcher cannot rewrite retired recovery evidence or cancel a newer
lease. The accepted final state and cancellation token are set before the stop becomes visible;
current revocation and the original deadlines remain enforced.

## Portable transfer proposal models

agent_runtime/transfer_models.py contains only immutable selection/file/manifest data with strict
version, identity, deadline, name, chunk and aggregate-size bounds. It reuses neutral config_sync
AssetFile/AssetManifest/SyncAssetBlob validators; canonical digest binding grants no authority and
does not verify payload bytes. transfer_records.py composes these neutral validators without
importing runtime/policy/service layers. Its fixed source-grant/import/routed-review tables
share exact-intent tombstones and atomic writer quotas. Revocation/expiry retain byte/chunk
reservations until the trusted host fences producers, cleans the generated account and calls
release; cleaned grant metadata still counts toward128 retained grants until actual expiry.
Pruning never removes unexpired metadata even with a future cutoff. Source authorization,
transport, producer lifecycle and current-host checks are not supplied by these primitives.
SyncAssetStore.delete_account removes only one host-selected account in one transaction;
it exposes no generic delete route and cannot prove caller ownership or producer retirement.
Actual runtime/surfaces, import/publication and remote evidence adoption remain in Progress.
