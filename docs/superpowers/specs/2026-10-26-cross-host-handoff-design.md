# Cross-host artifact and completion evidence handoff

## Intent and scope

Complete the P8 cross-host outcome path in the original P0-P9 contract. A coordinator must obtain
explicitly selected outcomes from a registered host, publish independently verified bytes on another
host, and adopt actual remote completion evidence without forwarding local ownership or authority.
Artifact transport and evidence adoption are separate operations; both are required by this design.
The existing forty-item goal and deferred real-machine/native acceptance remain open.

Base: feature commit58c17e05. Its three full-suite DAG precondition failures remain in Progress.md.
This design does not count those failures, native/device/browser acceptance or production deployment
as complete. Existing inline execution and the user's question opt-out apply; no per-stage agents.

## Approach and alternatives

Use the existing registered-host configuration/fingerprint, authenticated bounded runtime transport,
private source recovery witnesses and config_sync's immutable chunk/blob/generation primitives.
Add a runtime-owned transfer controller, a source grant engine and a separate portable evidence view.
An opaque grant ID never supplies authentication or task-input permission.
New neutral modules receive peer/policy/evidence collaborators from the host. They do not import
Runtime, TaskPolicy, AgentRecovery or DAG managed_tasks back into the runtime-owned controller.
The existing DAG host adapter owns registered endpoint/token lookup and calls the existing HTTP
transport; injected callbacks are host objects, never public JSON fields or a model plugin hook.

Copying peer filesystem paths would lose host identity and policy. Forwarding private local handoff
rows would expose store paths/principals and fabricate foreign admission. The trusted-viewer file
receiver replaces destinations and lacks the required bounded digest/publication contract. These
are not suitable substitutes. No new FastAPI/config-service deployment or dependency is needed.

## Global constraints

- All execution background; no foreground/window activation, desktop input or UIA Invoke.
- Browser operations remain je_web_runner from D:/Codes/WebRunner; this protocol starts no browser.
- No production/main source edits, shared environment changes, dependency/version changes or deployment.
- No paid dependency, billing feature, credential replacement or Tripo operation.
- File/function/parameters/CC/nesting/line limits750/75/7/10/4/120, parameters include self.
- No new cyclic import edge, including within an existing component; no broad suppression.
- Existing completion, root/origin, current-role, cancellation and uncertain-effect rules remain.
- Use existing runtime ownership; no new global client discovery or service activation on import.

## Authority and host identity

Each server authorizes its own authenticated caller with its own local authorization store. Source
issuance requires current management rights over every referenced source/effect/reader. The source
grant's recipient is derived privately from recipient_policy, exactly caller or source_owner.
caller selects the actual authenticated issuer; source_owner selects the original source's actual
owner. Neither accepts an arbitrary principal/store path. The policy is included in the reviewed
proof; an administrator may explicitly export reviewed source data to their own source account,
or grant selected reader evidence to its original source owner. Consumption authenticates as that
derived source-local recipient; ordinary task visibility is unchanged.

A destination uses a registered source label and pins the existing endpoint/token fingerprint.
Changing/removing that registration invalidates an old import/adoption review and execution.
The source owner's token is used only as an HTTP credential, never returned, copied into task options
or stored in a portable manifest. Existing shared-token mode authenticates a trusted shared account;
it does not prove a distinct peer/user identity. Named separation requires the existing source RBAC.

The new peer-read route is POST /agent/transfer/peer. It rejects local principal/origin delegation
headers before any forwarded-principal/store lookup. It authenticates solely with the receiving
server's ordinary bearer/RBAC gate. The local management route remains POST /agent/transfer and
preserves the existing authenticated local-service delegation for real local callers.

Only host-side management may resolve a remote registered label. Management requests may use
optional host="local" or a registered owning host; routing strips host before its closed parser.
For a remote import, source_host is resolved by the destination's own registry. A coordinator never
forwards its source credential into that destination. The destination must already have an approved
source account matching the reviewed recipient. A third coordinator may therefore route B-to-C work
without treating B/C paths or credentials as local. Remote calls use delegate_local=False and refresh
coordinator authority pre/post.
Routed reviews are privately stored at the coordinator, binding its actor, exact owning-host
fingerprint, peer review token, public review digest, expiry and key. Return a local opaque review
token; creation unwraps it only for that unchanged host. A replaced host or a caller-authored peer
token cannot bypass this binding. Persist an intent before forwarding creation; lost acknowledgement
stays uncertain and exact key/review deduplication never creates a second grant or import.
Active task operations cannot recursively invoke transfer management or dispatch new agents.

## Artifact identity and selection

Source export requires a succeeded, independently verified task with exact completion_contract=1
and input_released=true. Selection names original file criteria by index: file_exists/file_text/
file_sha256 select their one file; file_manifest selects a distinct explicit subset of its names.
Only source policy resolves those paths. A selected file must be a confined regular file and remain
the same descriptor/path/content throughout snapshotting and export creation. Ambiguous output-name
collisions, links, unsupported criteria and inaccessible evidence are rejected. No arbitrary path,
raw journal, user database, browser handle or screenshot-cache selector is exposed.
selection is a list of exact objects {criterion:int,names:list[str]}; criterion indexes are distinct,
within the actual original criteria array and exclude booleans. names is empty for a single-file
criterion, and a nonempty duplicate-free subset of declared names for file_manifest. Output names
come from the source's verified files; callers cannot supply a replacement path or filename.

Approved output-file bytes retain their exact content; they are explicit user output, not a new
screen capture. Framework observations retain their existing masking/in-memory rules. Portable
evidence is generated from a closed redacted projection, never by copying a raw result/journal file.

Ruling: export creates a consent-bound immutable artifact snapshot. A source file change between
review and creation invalidates creation. After commit, the blob is the selected historical artifact;
later edits of the original user file do not mutate the approved blob or establish current app state.
Every chunk still checks current grant, recipient, source evidence, permissions, expiry and revocation.
Corrupt/missing blob bytes fail verification. Live completion evidence is separately revalidated.

Use SyncAssetBlob/AssetFile/AssetManifest and SyncAssetStore internally; never use a caller-supplied
config account ID. Each grant/import has a generated private blob account. Host admission reserves
capacity under the runtime writer: at most128 retained grants,16 active imports,1GiB reserved bytes
and8192 chunks overall. Each manifest has1..500 distinct portable filenames, total bytes<=64MiB,
256KiB chunks and encoded manifest<=1MiB. Empty files are valid exact zero-byte blobs. Reject booleans
as integers, unknown fields, duplicate/case-colliding names, parent/drive/UNC/alternate-stream paths,
nonfinite deadlines and inconsistent chunk/size/digest descriptors before filesystem effects.

## Wire and review contracts

Public version fields are exact JSON integer1. Task/export/import/grant IDs are32 lowercase hex;
digests are64 lowercase hex; idempotency keys are nonempty strings of at most256 characters.
Notes are nonempty strings of at most4000 characters. Review tokens expire after300 seconds.
Creation atomically consumes one review into one exact idempotency key; an identical retry returns
the original record. Changed note/key/scope fails. Revoked IDs and consumed reviews cannot recreate
authority; new consent requires a new review and key. Source snapshots/roles are rechecked after
insertion under the same SQLite writer; no network/file hashing runs while holding that writer.

Portable export manifest fields: contract,export_id,source_task,source_snapshot,submission_digest,
files,expires. Each file has name,size,sha256,chunks. No owner, local roots, store path, origin IDs,
journal path or host bearer is included. A manifest digest covers this entire canonical envelope.
Imported bytes and a transfer receipt are not evidence that a source task or DAG has completed.

Peer operations are exactly export(export_id), chunk(export_id,sha256) and evidence(grant_id,binding).
Chunk replies contain contract,sha256,data with bounded canonical base64. Only a digest actually in
that exact grant may be read, even if the private store contains the same digest elsewhere. Peer
JSON bodies are capped at1MiB before allocation; redirects and arbitrary URLs are refused.

Management operations and closed request fields (optional host routes to the owning service):

| Operation | Fields |
| --- | --- |
| review_export | source_task, selection, recipient_policy, idempotency_key |
| create_export | review, note, idempotency_key |
| get_export / revoke_export | export_id |
| list_exports | source_task |
| review_import | source_host, export_id, target, directory, idempotency_key |
| create_import | review, note, idempotency_key |
| get_import / run_import / cancel_import | import_id |
| list_imports | none |
| review_evidence | source_task, task_id, recipient_policy, idempotency_key |
| create_evidence | review, note, idempotency_key |
| get_evidence / revoke_evidence | grant_id |
| list_evidence | source_task |

## Destination publication and lifecycle

Review binds actual local recipient, source fingerprint/manifest digest, an enabled immutable files
target profile, directory inside both its roots and the current caller/session ceilings, and the key.
Only local destination code interprets directory; it is never sent to the source as authority.
Creation persists the exact review and issuer before queueing a service-owned transfer delivery.
Use the existing WorkQueue claim/generation/fencing and DeferredAuthorization checks.

States: queued,receiving,verified,published,requires_review,cancelled,expired. Chunks may be accepted
idempotently by content address, but an uncertain operation never dispatches task input or silently
restarts publication. On restart, inspect the exact owned staging/generation and durable intent;
reverify bytes/manifest and original authority before continuing. Unknown ownership/publication is
requires_review. Cancellation keeps a confirmed already-published outcome distinct from an unstarted
or partial transfer. GUI closure detaches its observer and leaves service-owned work intact.

Reuse sync_assets for exclusive staging and immutable generation publication; verify full layout,
sizes and hashes again after publication. Check current destination authority/profile/root/source
grant before/after I/O and before durable publication acceptance. Existing differing user output is
never replaced. Destination files-directory plus exact digest can supply ordinary independent local
file verification under that task's separately approved roots; it grants no automatic downstream input.

## Portable completion evidence

Source validates at most16 real recovery links using actual source/effect snapshots, original
accepted request/submission witness, owners/reviewer, completion renewal and current private scope.
Reuse AgentRecovery.handoff_witness/handoff_scope and neutral completion checks through injected
collaborators; do not duplicate policy or import service/DAG layers into a neutral leaf.

A new source context distinguishes an actual remotely accepted DAG node from a local DAG admission.
If an ancestor has a real local batch/admission, use its existing local handoff context and admission;
the new route cannot bypass it by dropping/changing dag_batch tags. A remote node with no local batch
binds its actual accepted request and source-local owner, not a fabricated coordinator admission.
Standalone tasks retain their actual non-DAG lineage. New private storage families cannot ambiguously
resolve an old local grant ID, and new operations cannot turn existing local grants into wire grants.

Portable evidence fields: contract,grant_id,source_task,task_id,source_snapshot,completion_snapshot,
submitted_spec_digest,node,chain,verification,expires,evidence_only=true,input_authorized=false.
node is absent for a real standalone source, otherwise exact batch_id/graph_hash/node_id/request_digest.
The peer binding names source_task,request_key_hash,submitted_spec_digest and, for a DAG node,
batch_id/graph_hash/node_id. The source matches that request_key_hash against a real privately owned
accepted request row. node.request_digest hashes the canonical object {key_hash,submitted_spec_digest};
coordinator-only wait_seconds is not fabricated as a field the source received. Multiple real accepted
aliases cannot make a different key/spec acceptable; the exact requested witness must be pinned.
chain contains source_task/task_id/snapshot hashes only, never source owners, local policy bundles or
origin witnesses. Source rechecks the private proof and live authority on every peer resolution.

Coordinator adoption matches its real private batch/graph/node/attempt, original source request key,
source task ID, accepted spec digest and reviewed source host fingerprint. Only the authenticated
source can resolve its grant; a stored receipt/manifest/flag cannot substitute. Validate exact original
criteria/input retirement with completion_contract, preserve source and current successor snapshots,
and re-resolve at review, approval, claim and final downstream acceptance. Source unavailable,
expired/revoked or changed evidence stays non-admissible. Existing local adoption remains unchanged.
Shared recording/skill consumers may use a validated portable view for selected evidence; they retain
original actions/trials/versions and their own current authorization. No foreign task ownership moves.

There is no cross-host atomic SQLite transaction. New adoption stays provisional until a post-write
source resolution succeeds; provisional/unavailable records cannot dispatch downstream work. Every
next dispatch/acceptance repeats source resolution under the same pinned coordinator attempt.
Revocation after a remote task was already admitted cannot undo its inputs: request its existing
owned pause, retain uncertain retirement and block further coordination/completion. That task's own
destination-local input authorization remains independently enforced; evidence grants supply none.

## Retention and cleanup

Source export expiry is source terminal updated+30days. Evidence expiry uses the earliest retained
terminal witness in its actual chain, matching existing local grants. Destination receipt expiry is
min(source expiry,local creation+30days); retries, imports, restarts and retained unresolved batches
never refresh it. Each host checks its own fixed deadline; source resolution remains authoritative.
Expired or disconnected destination evidence cannot be replaced by a coordinator's own receipt.

Prune only exclusively owned staging/chunk accounts and transfer metadata, preserving revocation
tombstones needed by retained records. Add a bounded private account-deletion operation to the blob
store with actual ownership checks and no caller-controlled account route. User output and unrelated
journals stay untouched; surviving bytes do not preserve an expired grant. Failed cleanup stays tracked.

## Surfaces and proof

Expose manage_agent_transfer / AC_agent_transfer, agent-task transfer, MCP/REST/Builder and a thin
Transfers page with Actions, JSON requests and results through the existing TaskController. Four
locales and inert examples cover export/import/evidence review/creation; no consent auto-dispatch.
Update three READMEs, both Sphinx guides, reference/capability/lifecycle/architecture/map together.

Proof requires two independently owned runtimes with distinct SQLite stores, roots and actual named
RBAC accounts; real authenticated loopback HTTP, real bytes and immutable generation publication.
Coordinator-local paths deliberately cannot satisfy the destination.
Add a real third coordinator for routed review/create/import: the destination uses only its own
source registration, host replacement invalidates routed consent and no credential is forwarded.
Test private-header rejection, wrong credential/owner/host/graph/node/key, source snapshot/content
changes, all bounds/path attacks,
revocation/expiry/disconnection, partial/late ACK, restart, conflict and stopped cleanup. Verify source
and destination independently rather than mocking the entire transport/provider.
Fresh headless/coverage, three-platform typing, no-added lint/cycle/duplicate checks, docs and exact
wheel/sdist/installed-byte/worker proof are required for the implementation. Preserve earlier full
failures and all original P0-P9 gaps; real-machine/native/browser/device/24-hour acceptance is separate.
