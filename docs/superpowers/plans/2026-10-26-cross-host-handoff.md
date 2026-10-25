# Cross-host Outcome Handoff Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. Existing inline/question opt-out applies; one whole-original-goal review at its actual end.

**Goal:** Transfer actual selected outcomes and adopt independently verified remote completion evidence
between registered hosts while keeping each host's ownership, current grants and retention separate.

**Architecture:** A runtime-owned transfer controller composes source snapshot/export grants,
content-addressed byte storage, destination immutable generation publication and a portable evidence
resolver. Source policy and coordinator DAG admission remain local, joined by authenticated closed
wire projections; private grant rows and local principals never cross hosts.

**Tech Stack:** Existing Python>=3.10, SQLite, WorkQueue, DeferredAuthorization, runtime HTTP,
config_sync blob/models/assets and PySide6 thin views. No dependency or shared environment changes.

**Spec:** docs/superpowers/specs/2026-10-26-cross-host-handoff-design.md

## Global Constraints

- Preserve the original forty-item P0-P9 goal and previous three full-suite failures in Progress.
- Entirely background; no desktop input/foreground/UIA Invoke or real-browser/native/device acceptance.
- Browser automation remains je_web_runner from D:/Codes/WebRunner.
- No production/main source, deployment, shared environment, dependency or version changes.
- Limits750/75/7/10/4/120; no new cyclic import edge, including inside existing components.
- Exact contract1,32hex IDs,64hex digests; keys<=256, notes<=4000, reviews300seconds.
- Files1..500,total<=64MiB,chunks256KiB,manifest/peer body<=1MiB.
- Per runtime: grants<=128,active imports<=16,reserved bytes<=1GiB,reserved chunks<=8192.
- Creation/retry/revocation/expiry and current authority follow the spec, with no deadline relaxation.
- Commit consistent independently tested steps; failed full acceptance stays explicitly open.

## Review Focus

- A real local DAG source cannot bypass its private admission by taking the remote grant route.
- Shared-token authentication is a shared account, never a claimed distinct peer/user identity.
- Source headers/body/portable metadata cannot cause a foreign local-store/principal lookup.
- Publication success racing cancellation/revocation must preserve exact owned outcome without replay.
- An unresolved coordinator record cannot extend an independent destination's evidence deadline.

## File responsibilities

Create under utils/agent_runtime/: transfer_models.py (closed DTOs/bounds), transfer_records.py
(fixed tables/review/key/revocation/reservations), transfer_source.py (selected immutable snapshots),
transfer_transport.py (registered-peer calls/projections), transfer_import.py (delivery/publication),
transfer_evidence.py (private source proof/portable view), transfer_protocol.py (closed controller).
Split a responsibility further before exceeding budgets; do not put new logic in the facade/GUI.
Modify runtime.py/store.py only for ownership/schema/lifecycle wiring, and existing recovery/DAG
modules for injected evidence consumers. Use a new gui/agent_transfer_view.py for the thin form.

## Task 1: Exact transfer models and private durable records

**Files:** create transfer_models.py, transfer_records.py; modify config_sync/blob_store.py for
bounded private-account deletion; tests test_agent_transfer_models.py / test_agent_transfer_records.py.

**Interfaces:**
- TransferSelection.from_dict(value: Mapping[str,Any]) -> TransferSelection validates exact
  criterion:int/names:list fields; .to_dict() preserves their types and declared selection.
- TransferManifest.from_dict(value: Mapping[str,Any]) -> TransferManifest; .to_dict() -> dict;
  .digest -> str. Preserve exact names/sizes/chunk descriptors and all spec field/type bounds.
- TransferRecords(store: Any) owns initialize(connection), reserve(connection,record),
  consume_review(connection,review,key,note), revoke(connection,identifier),
  active(connection,identifier), prune(cutoff). Only fixed table/column families, bound values.
  Private routed reviews bind actor/owning host fingerprint/peer token/digest/key/expiry separately
  from source grants and imports; caller-supplied peer review tokens cannot select those records.
- SyncAssetStore.delete_account(user_id: str) -> dict[str,int] removes only that private account
  transactionally. Runtime controller owns account IDs; expose no new generic account-delete route.

- [x] Write tests rejecting True-as-version/size, NaN deadlines, unknown keys,
  zero-file/501-file/64MiB+1 manifests and portable-name collisions/traversal.
  Chunk ordering changes the review digest; real stored bytes must reject a swapped ordering
  under the original full digest. A descriptor alone cannot derive a file hash from chunk hashes.
  Model canonical metadata stays bounded; test the raw1MiB+1 preparse body guard in Task2's real HTTP path.
  Assert an exact empty-file descriptor round-trips, and unrelated same-digest account survives deletion.
- [x] Run the two new test files in a fresh owned basetemp. Expected: missing-model/record behavior
  fails, not a typo/dependency failure; retain RED output before implementation.
- [x] Implement DTO/record interfaces; use existing AssetFile/SyncAssetBlob validation without
  importing optional config routes. Writer reservations atomically enforce all aggregate limits.
- [x] Add barrier tests: two capacity claims cannot overbook, one review binds one key, exact retry
  returns one ID, revoked ID/consumed review cannot recreate authority and crash rollback leaves no grant.
- [x] Run the new files plus existing blob-store tests. Expected: all pass and unrelated accounts intact.
  Update measured map/Progress/records and commit the consistent source step with remaining tasks open.

## Task 2: Source artifact review/export and authenticated peer reads

**Files:** create transfer_source.py / transfer_transport.py; modify routes.py, client.py,
dag/managed_tasks.py, dag_batches.py, rest_api/rest_server.py and rbac/policy.py;
tests test_agent_transfer_source.py /
test_agent_transfer_peer_security.py.
Create the minimal transfer_protocol.py controller and runtime owner wiring here so the source/peer
REST tests are independently executable. Import delivery/evidence are explicitly unavailable until
Tasks3/4; passive support describes those operations separately rather than advertising all as ready.

**Interfaces:**
- TransferSource(runtime: Any, records: TransferRecords).control(operation: str, request: Mapping) -> dict.
  Source management operations/fields are the exact spec table; optional host is stripped by routing.
- AgentTransfers(runtime: Any, peer: TransferPeer).control(operation: str, request: Mapping|None=None)
  -> dict; .peer(operation: str, request: Mapping) -> dict. Source operations work in this task;
  unsupported import/evidence operations fail explicitly. Host objects supply policy/proof callbacks.
- TransferPeer(invoke: Callable).call(host: str, binding: str, operation: str, request: Mapping,
  timeout: float) -> dict validates closed operations/replies using the injected host adapter.
- registered_host_transfer(host: str, binding: str, path: str, body: dict, timeout: float) -> dict in
  existing dag/managed_tasks.py accepts only /agent/transfer and /agent/transfer/peer; uses its
  existing host fingerprint/current-authorization/request_json dependencies, delegate_local=False.
  DagBatches.transfer_call delegates to it; no new neutral module imports managed_tasks/TaskPolicy.
- Peer source calls accept only export/chunk/evidence; management and peer route dispatch stay separate.

- [ ] RED actual files/real store tests: review selects a passed file criterion, binds its exact
  digest, creation yields one immutable grant, and one actual authorized peer read returns those bytes.
  Refuse an unconfirmed task/unsupported criterion/arbitrary path before touching unrelated files.
- [ ] RED named-source RBAC tests: recipient_policy derives only actual caller or original source owner;
  administrator export to caller and reviewer grant to source_owner both use real source identities.
  Changing that reviewed policy or supplying an arbitrary principal/store path fails. Another operator with
  the grant ID cannot read; removed/revoked issuer/owner/grant loses access. Shared-token tests assert
  shared-account semantics without fabricating a user. Poison a foreign-store loader and ensure the
  peer route refuses principal/origin headers before that loader is called.
- [ ] Implement current policy/descriptor snapshot, selected-file hashing and immutable blob creation
  outside the runtime writer. Recheck current source/scope after the grant INSERT within its writer.
  No public source roots/principals/origin witnesses or raw result/journal exports.
- [ ] Add changed-file-between-review/create, symlink swap, scope change, corrupt/missing chunk,
  off-manifest digest, host/token replacement and late reply cases. Post-export original-file edits
  do not change the consented blob; snapshot transfer never claims current application state.
- [ ] Run source/peer and existing transport/local-delegation/RBAC suites. Expected: all pass, peer
  bodies bounded before allocation and legacy local service forwarding unchanged. Commit source step.

## Task 3: Service-owned destination import/publication and retention

**Files:** create transfer_import.py; extend transfer_protocol.py; modify runtime.py/store.py/background
delivery wiring and retention.py; tests test_agent_transfer_import.py / test_agent_transfer_lifecycle.py.

**Interfaces:**
- AgentTransfers(runtime: Any, peer: TransferPeer).control(operation: str, request: Mapping|None=None) -> dict;
  .maintain() -> None; .close() -> None; .peer(operation: str, request: Mapping) -> dict.
- TransferImporter(runtime: Any, records: TransferRecords).control(operation: str, request: Mapping) -> dict;
  .deliver(import_id: str, generation: int, check: Callable[[],None]) -> dict.
- Runtime .transfers owns the controller; callers cannot inject a transport/provider through JSON.
  Existing host recovery/profile methods supply actual policy/proof objects through runtime
  collaborators; new neutral modules do not import Runtime/AgentRecovery/TaskPolicy in reverse.

- [ ] RED two independent real HTTP runtimes with distinct roots/accounts: an approved import of
  source bytes reaches the destination generation, whose files/hash/layout are independently read.
  Coordinator-local path substitution must fail even if a same-named local file exists.
- [ ] RED a third real coordinator routing source-B to destination-C. C resolves B through its
  own registered source account; A forwards no bearer/local principal/root. Replacing C's host
  registration or replaying its raw review token at A fails before a create call. Lost create ACK
  preserves one exact intent/key and no duplicate import; unrelated host work remains untouched.
- [ ] RED finite review/create/run/cancel and queue generation tests: wrong owner/profile/root/host
  cannot start; UI observer closure leaves owned delivery intact. Generation replacement fences old work.
- [ ] Implement source grant checks and existing chunk store + sync_assets staging/publication.
  Bind both local issuer/recipient authority and immutable files target profile before every effect;
  preserve exact published versus partial/unknown states and never replace differing user output.
- [ ] Add restart/late ACK/cancel-after-publication races, partial transfer/content corruption, profile
  disable/root move/credential revoke, independent source/destination expiry and cleanup-failure cases.
  Assert retained unresolved batches do not refresh receipt expiry or grant surviving expired bytes.
- [ ] Run actual import/lifecycle plus queue/retention/GUI-task-lifetime regressions. Expected: correct
  finite outcomes, byte verification and exclusively owned cleanup. Commit source/lifecycle step.

## Task 4: Portable evidence source and actual DAG/skill adoption

**Files:** create transfer_evidence.py; modify task_recovery.py/handoff_records.py only for injected
private families, dag_continuation_evidence.py/dag_continuation.py/dag_batch_recording.py and
skill evidence consumers; tests test_agent_transfer_evidence.py / test_agent_transfer_adoption.py.

**Interfaces:**
- RemoteEvidenceSource(runtime: Any, records: TransferRecords).control(operation: str, request: Mapping) -> dict;
  .resolve(grant_id: str, binding: Mapping) -> dict produces the exact portable projection in the spec.
- resolve_remote_evidence(peer: TransferPeer, host: str, host_binding: str, grant_id: str, binding: Mapping,
  timeout: float=30) -> dict validates a fresh authenticated peer reply without local path/owner decoding.
- ContinuationEvidence.successor keeps its existing signature; remote handoff IDs select the new
  validated source protocol, local IDs keep the old local engine. Stable portable views do not broaden get.

- [ ] RED real source recovery/completion grant adopted by its actual coordinator node, with leaf
  evidence owned by a different reviewed source account. Ordinary foreign task get remains denied.
  Original request key/spec, actual source task, graph/node and source fingerprint must all match.
- [ ] RED local-DAG bypass attempts: strip/change tags, use a new wire grant over a real local
  admission or choose standalone ancestry. Every actual local admission still needs its original
  private grant checks; no synthetic DAG/admission/ownership row is created for a remote node.
- [ ] Implement source current proof using existing injected snapshot/witness/scope collaborators,
  bounded sixteen-link ancestry and distinct private remote grant family. Post-insertion changes
  roll back. Portable fields contain only IDs/hashes/finite criteria, not private owners or policies.
- [ ] Implement live resolution at review/approval/claim/downstream completion, plus selected skill
  evidence integration preserving original actions/trial/version. Add revoke/expiry/source mutation,
  unavailable peer, expired reader consent and wrong completion/retirement-contract cases.
  Barrier tests revoke between local adoption write and post-write source check: no downstream
  dispatch from provisional state. Revoke after actual dispatch preserves owned pause uncertainty
  and blocks further success; it cannot pretend to undo remote inputs or grant input authority.
- [ ] Run all actual local handoff/renewal/ownership/recovery/skill and fourteen DAG files with new
  remote cases. Preserve exact deadlines and prior failed runs. Commit the coherent evidence step.

## Task 5: Public surfaces, full verification and delivery

**Files:** api.py/commands.py/cli.py/client.py/routes.py, runtime package/facade/core exports,
MCP/REST schemas/Builder, gui/agent_transfer_view.py + agent_tasks_tab.py, four locales,
three READMEs/Sphinx2/API_LIFECYCLE/CAPABILITY_MATRIX/architecture/map/examples/Progress/updates.
Tests: test_agent_transfer_surfaces.py / test_agent_transfer_gui.py and existing shared-surface tests.

**Interfaces:** manage_agent_transfer(operation: str, request: Mapping|None=None) -> dict;
AC_agent_transfer(operation,request); agent-task transfer --operation --request;
POST /agent/transfer {operation,request}; existing TaskController transports one finite request.

- [ ] RED Python/AC/MCP/authenticated REST/CLI/Builder parity and four locale/Actions tests. GUI
  request/result views reject stale replies after selection/close and never auto-send consent.
- [ ] Implement thin surface wiring, source/destination/grant selection examples and passive
  transfer-contract diagnostics distinct from an actual grant or verified remote/native capability.
- [ ] Self-check every spec section against its owning tests; compare exact import edges against
  committed58c17e05, including edges inside old cyclic components; reject added cycles/duplicates.
- [ ] Run focused/real loopback/three-platform typing/Ruff/full Pylint normalized audit/Bandit/Radon,
  strict Sphinx and measured counts; build fresh wheel/sdist and verify exact source/installed bytes.
- [ ] Freeze actual code/test/config/doc inputs; run a fresh full coverage suite in an absent owned
  basetemp, inspect all failures/errors/warnings/atexit and exact coverage. Prior three DAG failures
  and409/bootstrap/shared-pytest-link concerns cannot disappear through a passing subset or retry.
- [ ] Publish accurate current records under the monthly ID lock, mirror only main Agent Progress
  preserving unrelated raw bytes, stage explicit owned paths, commit/push feature and verify remote
  SHA/clean state. Do not mark the original goal complete; real-host deployment/acceptance and other
  original requirements remain until their separate evidence exists.
