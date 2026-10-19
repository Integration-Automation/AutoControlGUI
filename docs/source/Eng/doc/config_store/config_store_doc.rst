Persistent configuration commits
================================

The experimental ``ConfigStore`` persists account buckets and operation receipts
in SQLite. Constructing a store or signaling app does not open a database.
The first operation resolves ``AUTOCONTROL_CONFIG_STORE`` or
``~/.autocontrol/config-sync.sqlite3``. Pass an explicit path to isolate stores.
Each operation closes its connection; a commit compares the base revision,
writes the bucket and saves its receipt in one ``BEGIN IMMEDIATE`` transaction.

Local API
---------

::

    from je_auto_control import ConfigBucket, ConfigStore

    bucket = ConfigBucket("alice")
    bucket.upsert("settings", "theme", {"value": "dark"})
    store = ConfigStore("config-sync.sqlite3")
    revision = store.commit("alice", bucket, base_revision=0, operation_id="edit-1")
    assert ConfigStore("config-sync.sqlite3").get("alice").revision == revision
    assert store.commit("alice", bucket, base_revision=0, operation_id="edit-1") == revision

The input bucket is not mutated. Reads return independent objects. An identical
operation retry returns its original revision, even after later commits or a
restart, without replacing newer data. Reusing an operation ID with different
content or base raises ``ConfigRevisionConflict``. IDs are scoped to accounts.
A stale base also raises that exception with ``current_revision``. New accounts
are capped at 1,024 by default; ``ConfigStoreFull`` is distinct from storage
failures (``ConfigStoreError``). Invalid input raises ``ConfigSyncError``.
Buckets are bounded to finite JSON of 1 MiB. Identifiers are nonempty printable
text up to 128 characters without ``/``; revisions are nonnegative SQLite integers.
Operation receipts are retained; no time-based deduplication expiry is imposed.

Run ``python -m examples.config_store`` for a temporary-file-only example.

HTTP and client
---------------

Start the existing optional signaling service with an explicit database::

    python -m je_auto_control.utils.remote_desktop.signaling_server --config-store config-sync.sqlite3

The existing ``--shared-secret`` / ``AC_SIGNALING_SECRET`` rules still apply.
GET uses ``/config/{user_id}``; conditional clients PUT to
``/config/{user_id}/commit``. The original PUT route also accepts v2 envelopes.
The dedicated commit route always refuses legacy bodies and prevents an old
blind-write server from storing an unsupported new envelope as bucket data.
The shared secret grants service access;
account names isolate storage namespaces and payload identities, rather than
providing a separate per-account login. Unauthenticated and malformed conditional
writes are refused before opening the config database. SDP sessions remain
process-local and are separate from persistent buckets.

A version-two PUT body has exactly these fields::

    {"version": 2, "base_revision": 0, "operation_id": "edit-1",
     "bucket": {"user_id": "alice", "revision": 0, "sections": {}}}

Success returns ``{"ok": true, "version": 2, "revision": 1}``.
Stale revisions or operation reuse with different input return HTTP 409, including
the current revision. GET retains the bucket shape and returns its committed
revision, with ``X-Autocontrol-Config-Protocol: 2`` and a CAS mode header.
The existing request-body cap and secret guard apply before JSON processing.

``ConfigSyncClient.push(bucket, base_revision=..., operation_id=...)`` uses this
protocol and returns the committed revision. Its default base is the bucket's
revision. Retain the same operation ID, base and content when retrying an
uncertain network result; omitting the ID creates a new one per push call.
``sync`` fetches, merges and commits against the fetched base. A conflict
propagates for an explicit refetch; it never falls back to a blind write.
Redirect protection and the existing HTTP egress policy remain active.

Compatibility and delivery
--------------------------

Blind legacy writes are disabled by default (HTTP 428). To opt in, set server
``allow_legacy_config_writes=True`` or ``--allow-legacy-config-writes``; a legacy
client needs ``legacy_writes=True``. Legacy documents retain opaque JSON fields,
while revisions remain server-owned. Legacy client pushes return ``None`` and
do not claim CAS or idempotency protection. GET advertises ``legacy-enabled``
when blind writes are allowed. Unsupported protocol versions are rejected.

``AC_config_store_get`` / ``ac_config_store_get`` read a local private database;
``AC_config_store_commit`` / ``ac_config_store_commit`` commit against a base and
operation ID. Both require DRIVE authority and honor path roots. Script Builder
provides explicit Data commands with the same fields, including JSON bucket
input. Reading an absent store can initialize its schema, so it is an explicit
private operation. These commands store data; they never run synced scripts or
enable triggers. MCP cancellation is checked before storage; a completed commit
is not relabelled cancelled.

The separate CausalConfigStore and dedicated version-three /causal protocol
validate peer acknowledgements, retirement/full-sync epochs and deletion payload
collection with permanent causal fences. Upgraded accounts reject plain reads and
writes; existing local store commands accept causal JSON with an explicit _actor.
See :doc:`../causal_sync/causal_sync_doc`. The current HTTP client/merge helper
retains last-modified ordering and time-bounded tombstones. Automatic peer-control/
full-resync orchestration and asset adapters remain in Progress.md. The explicit
CausalSyncClient.flush supplies durable v3 delivery and bounded rebasing. Local tests
use isolated files and loopback servers, without remote-machine or native acceptance.
