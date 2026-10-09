Cross-Machine Config Sync
=========================

``je_auto_control.utils.config_sync`` keeps one user's hotkeys, triggers,
address book and other small settings the same on several machines. Each user
has one *bucket* on a sync server; the signaling server
(``python -m je_auto_control.utils.remote_desktop.signaling_server``, the
``[signaling]`` extra) serves it at ``GET`` / ``PUT /config/{user_id}``.

Everything a script needs is on the package facade: ``import je_auto_control as
ac`` gives ``ac.config_sync_run`` and its three siblings, ``ac.run_sync``,
``ac.ConfigSyncClient``, ``ac.ConfigBucket``, ``ac.SyncOutbox``, ``ac.SyncEntry``,
``ac.SyncOperation``, ``ac.SyncAdapter`` and the five concrete adapters
(``ac.ScriptSyncAdapter`` ...), ``ac.DirectoryAssetTransport``,
``ac.HttpAssetTransport``, ``ac.ConfigStore``, ``ac.BlobStore``, the errors
(``ac.ConfigSyncError``, ``ac.ConfigSyncConflict``, ``ac.FullResyncRequired``,
``ac.OperationMismatchError``, ``ac.ConfigStoreError``,
``ac.RevisionConflictError``), blob housekeeping
(``ac.config_sync_collect_blobs``, ``ac.collect_unreferenced_blobs``,
``ac.referenced_blob_digests``) and ``ac.CONFIG_SYNC_WIRE_VERSION`` (the module's
``WIRE_VERSION``, ``2``). The rest stays importable from
``je_auto_control.utils.config_sync``.

Server: persistent, revision-checked buckets
--------------------------------------------

Buckets are stored in one SQLite file by
``je_auto_control.utils.config_sync.store.ConfigStore``, so a server restart
keeps them. The file is chosen by, in order, ``--config-db PATH``, the
``AC_SIGNALING_CONFIG_DB`` environment variable, and the default
``~/.je_auto_control/config_sync.sqlite3``; it is opened at the first
``/config`` request, not at start-up. When embedding the app, pass
``create_app(config_store_path=...)``.

Every bucket has a server-assigned **revision** (``1`` for the first write,
then ``+1`` per commit). A write names the revision it was built on, and the
comparison and the write happen inside one SQLite transaction:

.. code-block:: python

    from je_auto_control.utils.config_sync.store import ConfigStore, RevisionConflictError

    store = ConfigStore("buckets.sqlite3")
    revision = store.commit("alice", bucket, base_revision=0, operation_id="op-1")   # -> 1
    store.commit("alice", bucket, base_revision=0, operation_id="op-1")              # -> 1 again
    store.commit("alice", other, base_revision=0, operation_id="op-2")               # RevisionConflictError

A repeated ``operation_id`` returns the revision its first commit produced and
writes nothing, so a client whose reply was lost can simply send the same
request again. The last 256 operation ids per user are remembered.

An operation id names *one* write. The store keeps a SHA-256 of what each id
wrote (the base revision plus the bucket without its ``revision`` field), and
the same id sent with a different bucket or base revision raises
``OperationMismatchError`` (``.operation_id``, ``.revision`` of the first
write) and writes nothing -- before, it was answered as if it had been
committed. An id recorded by a release that kept no hash is still answered
the old way; the column is added to an existing database at first use.

Wire format (version 2)
-----------------------

.. list-table::
   :header-rows: 1

   * - Request
     - Reply
   * - ``GET /config/{user_id}``
     - ``200`` with ``{"user_id", "sections", "peers", "revision": <committed>, "version": 2}``,
       or ``404`` when the user has no bucket.
   * - ``PUT /config/{user_id}`` with
       ``{"version": 2, "base_revision": N, "operation_id": "...", "bucket": {...}}``
     - ``200 {"ok": true, "revision": N + 1, "version": 2}``; ``409 {"detail": "revision conflict",
       "revision": <current>}`` when the bucket is no longer at ``N`` (nothing is written);
       ``409 {"code": "operation_mismatch", "revision": <the first write's>}`` when
       ``operation_id`` was already used for a different write (nothing is written);
       ``400`` for a malformed envelope or bucket, or a bucket naming another user.
   * - ``PUT /config/{user_id}`` with a bare bucket (the pre-version-2 body)
     - ``428`` -- unless the server runs with ``--allow-blind-config-writes``
       (``create_app(allow_blind_config_writes=True)``), which overwrites without a check
       and replies ``200 {"ok": true, "revision": ...}``.

``base_revision`` ``0`` means "there is no bucket yet". The shared secret
(``X-Signaling-Secret``), the 1 MiB body cap (``413``, checked before the body
is read), the ``Content-Length`` requirement (``411``) and the 1,024-user limit
(``503``) are unchanged. The bucket is now validated on the way in: sections
must be mappings of entry id to an object.

**Clients older than version 2** push a bare bucket. Against a server in its
default mode their ``push`` / ``sync`` fails with ``ConfigSyncError: config
sync PUT returned HTTP 428`` and nothing is written; their ``fetch`` keeps
working (the reply has the same fields plus ``version``, which they ignore).
Start the server with ``--allow-blind-config-writes`` to keep serving them,
accepting that two such clients pushing together can still overwrite each
other. A **version-2 client against an older server** is told so:
``push`` raises ``ConfigSyncError`` ("predates revision-checked writes")
because the reply carries no revision -- upgrade the server first.

Client
------

.. code-block:: python

    from je_auto_control.utils.config_sync import ConfigBucket, ConfigSyncClient, ConfigSyncConflict

    client = ConfigSyncClient("https://sync.example", user_id="alice", secret="...")
    merged, conflicts = client.sync(local_bucket)     # fetch, merge, push on top of what was fetched
    print(merged.revision)                            # the revision the server committed

``sync`` pushes with the fetched revision as ``base_revision``; when another
machine pushed in between it fetches and merges again, up to ``max_attempts``
(default 4) times, then raises ``ConfigSyncConflict``. Each ``sync`` also records the client's device
(``ConfigSyncClient(..., device_id=...)``, default: this machine's stored id)
under the bucket's ``peers`` as having merged the committed revision, and
drops the tombstones every device has seen -- the same bookkeeping
``push_operations`` does. A device the group retired gets
``FullResyncRequired`` from ``sync`` as well. ``push(bucket)`` uses
``bucket.revision`` as the base, returns the committed revision and raises
``ConfigSyncConflict`` (``.revision`` is the server's current one) instead of
overwriting. A ``409`` whose ``code`` is ``operation_mismatch`` raises
``OperationMismatchError`` instead; it is a ``ConfigSyncError`` but not a
``ConfigSyncConflict``, so ``sync`` does not fetch and retry it. A client
from before this code existed sees that reply as an ordinary conflict.

Causal merge: no clock picks a winner
-------------------------------------

An entry written with a device id is *versioned*
(``je_auto_control.utils.config_sync.versions.SyncEntry``): it carries a
version vector (per device, how many of that device's changes it includes),
the ``origin`` device and an ``operation_id``. ``merge_entries(left, right)``
returns a ``MergeDecision``:

* the entry made *knowing* the other supersedes it -- nothing is reported;
* two changes to the same key made apart are **both kept**: ``decision.conflict``
  is a ``SyncConflict(key, local, remote)`` and ``decision.entry`` holds the
  candidates as ``siblings`` until someone calls
  ``entry.resolved(value, origin)``. An edit made apart from a delete is a
  conflict too;
* changes to different keys never conflict (``merge_collections``).

``modified_at`` is carried for display only. Whatever the clocks of the
machines say, the decision is the same, and it is the same on every machine.

.. code-block:: python

    bucket.upsert("hotkeys", "hk1", {"combo": "ctrl+a"})                    # versioned, by this machine
    bucket.upsert("hotkeys", "hk1", {"combo": "ctrl+b"}, origin="laptop")   # ... or by a named device
    bucket.remove("hotkeys", "hk1")                                         # versioned tombstone
    bucket.values("hotkeys")        # live values; entries still in conflict are left out
    bucket.conflicts()              # [(section, SyncEntry with .siblings), ...]

``origin`` defaults to this machine's device id
(``default_device_id()``, kept in ``~/.je_auto_control/config_sync_device_id``),
so code written before version vectors -- ``bucket.upsert(section, id, value)``
and ``client.sync(bucket)`` -- is causal without being changed. A
``last_modified`` inside the value passed to ``upsert`` becomes the entry's
display stamp and is not stored in the value. ``remove`` on a flat entry
writes a versioned tombstone, which supersedes every flat copy.

.. warning::

   This changes what ``upsert`` stores. The entry is now
   ``{"value": {...}, "vector": {...}, "origin": ..., "operation_id": ...,
   "deleted": false, "last_modified": ...}`` rather than the value itself, so
   read values with ``bucket.values(section)`` (which works for both shapes)
   instead of ``bucket.sections[section][id]["field"]``. Pass
   ``versioned=False`` to ``upsert`` / ``remove`` to keep writing the flat
   entry; two flat entries still merge by "later wins" (reported in
   ``ConflictRecord``), and a versioned entry supersedes a flat copy of the
   same id. ``ConflictRecord.unresolved`` is true for a causal conflict, where
   nothing was dropped.

**An existing bucket after its first sync with this release.** Flat entries
this machine did not touch stay exactly as they were (same bytes, still "later
wins" among themselves). An entry this machine creates, edits or removes is
stored versioned with ``{"<device id>": n}`` as its vector. ``peers`` gains
``{"<device id>": {"acked_revision": <committed revision>, "last_seen": ...,
"retired": false}}``. A version-2 client from before this release reads all of
it: it already understood both entry shapes and ignores peers it does not
know. A tombstone only *waits* for devices already listed under ``peers``, so
a machine that has not synced yet is covered by the hold described below
instead: a deletion stays in the bucket for thirty days, and such a machine
meets it when it first syncs inside that time. Let every machine sync once
within thirty days of a deletion, or before deleting at all.

Deletions and retired devices
-----------------------------

A deletion is a tombstone. A versioned tombstone is **never dropped by age**:
``collect_tombstones`` removes it only when every active device recorded
under the bucket's ``peers`` has acknowledged a revision that includes it.
``ConfigSyncClient.push_operations`` maintains those acknowledgements.

**Held for the machines the bucket does not list yet.** Acknowledgement only
covers the devices under ``peers``. A machine that holds the entry but has
never synced is not one of them, and once the tombstone was gone its first
sync simply added the entry again, with no conflict and no report. So an
acknowledged tombstone is also kept for ``TOMBSTONE_HOLD_S`` (thirty days)
from the commit that first carried it. A machine that joins inside that time
meets the deletion: its versioned copy becomes a **conflict** (the deletion
and the copy, for a person to settle with ``config_sync_resolve``), and a
flat copy stays deleted and is reported in a ``ConflictRecord``. After the
hold the next commit by any device drops the tombstone, so the bucket does
not grow for ever; a machine that first syncs later than that can still bring
the entry back.

The commit that first carries a tombstone stamps it with ``deleted_at`` (that
device's wall clock) next to ``deleted_revision``. Age is only ever a reason
to *keep* a tombstone longer: a wrong clock can shorten or lengthen the hold,
never the wait for the listed devices. ``ConfigSyncClient(...,
tombstone_hold_s=0)`` restores the earlier rule for the buckets that client
commits, and ``collect_tombstones(entries, peers, now=..., hold_s=...)``
applies the hold only when ``now`` is given. A tombstone stamped by a release
from before this has no ``deleted_at`` and is dropped on acknowledgement as
before; such a release also drops acknowledged tombstones without holding
them, so the hold is only as good as the oldest client still committing.
A device joins ``peers`` with the first change it commits.
``push_operations([])`` from a device the bucket does not list writes
nothing, whether the bucket holds entries or not: a device that only reads a
bucket commits no revision for joining it, and a first sync of an empty
account commits none either. (Earlier a join against a non-empty bucket
wrote one revision so that later deletions would wait for the device.)

**What an unlisted device still gets, and what it does not.** A deletion made
while the device is unlisted reaches it through the held tombstone: inside
the thirty days its untouched copy is removed, and a copy it edited in the
meantime becomes a conflict. After the hold the tombstone is gone. A copy
the device did not touch is still removed -- its own baseline records that
the entry came from the bucket, so its absence is a deletion made elsewhere.
What is no longer guaranteed is the edited copy: a device that has only ever
read the bucket, edits an entry, and first sends that edit more than
``TOMBSTONE_HOLD_S`` after the entry was deleted elsewhere **re-creates the
entry with no conflict**. With the join revision the tombstone would have
waited for that device indefinitely and the edit would have been a
conflict. The remedy is the same as for a machine that never synced: sync
every machine at least once every thirty days, or have it commit a change
before it goes away.

A device that will not come back is retired with
``client.retire_peer(device_id)`` (or automatically with
``push_operations(..., max_offline_s=...)``, which compares ``last_seen``
stamps -- the only use of a clock, and it never decides between two values).
Tombstones stop waiting for a retired device, so when it does return its
pushes are refused with ``FullResyncRequired``; it must call
``client.full_resync(device_id=...)``, replace its local state with the
returned bucket and discard its pending operations. Merging instead could
bring deleted entries back.

Offline outbox
--------------

``SyncOutbox(db_path, account=..., endpoint=...)`` is a SQLite queue of
``SyncOperation(section, entry)`` not yet on the server (default file
``~/.je_auto_control/config_sync_outbox.sqlite3``; one file can hold several
accounts and endpoints, each isolated).

.. code-block:: python

    from je_auto_control.utils.config_sync import SyncEntry, SyncOperation, SyncOutbox

    outbox = SyncOutbox(account="alice", endpoint="https://sync.example")
    outbox.enqueue(SyncOperation("hotkeys", SyncEntry.create("hk1", {"combo": "ctrl+a"}, "laptop")))
    report = outbox.drain(
        lambda batch: client.push_operations(batch, device_id="laptop"), cancel=stop_event)
    # DrainReport(sent, pending, attempts, offline, cancelled, error)

Operations are queued under their operation id (queueing one twice is a
no-op), survive a restart, and are resent with the same ids -- applying a
batch the server already has changes nothing. A failed send backs off
2 s, 4 s, 8 s ... up to 300 s (``base_delay_s`` / ``max_delay_s``), a drain
makes at most ``max_attempts`` sends (default 5), ``wait=False`` returns
instead of sleeping through a back-off, and setting ``cancel`` ends a drain
even in the middle of a wait.

A drain that finds the queue still inside a retry delay sends nothing and
returns ``DrainReport(backing_off=True, retry_in_s=<seconds left>)``;
``offline`` is true as well (the queue did not get out) and ``error`` is the
failure that started the wait. ``drain(..., force=True)`` sends once without
regard to the delay; if that attempt fails too, the longer delay it earns is
respected.

Adapters: what is synced, and what stays on the machine
--------------------------------------------------------

``je_auto_control.utils.config_sync.adapters`` connects one bucket section to
one local store. ``SyncAdapter.snapshot()`` returns ``{key: SyncEntry}``
measured against the state last merged, and ``apply(entries)`` writes merged
entries back and returns an ``ApplyReport`` (``written`` / ``removed`` /
``skipped`` / ``conflicts`` / ``left_disabled``).

.. list-table::
   :header-rows: 1

   * - Section
     - Adapter
     - Local store
   * - ``scripts``
     - ``ScriptSyncAdapter(origin, scripts_dir)``
     - ``*.json`` action files under a folder, by relative path
   * - ``locators``
     - ``LocatorSyncAdapter(origin, repository)``
     - an ``ElementRepository``
   * - ``hotkeys``
     - ``HotkeySyncAdapter(origin, daemon, scripts_dir=...)``
     - a ``HotkeyDaemon``'s bindings
   * - ``triggers``
     - ``TriggerSyncAdapter(origin, engine, scripts_dir=...)``
     - a ``TriggerEngine``'s image / window / pixel / file / cron triggers and the
       all-of / any-of / sequence composites built from them
   * - ``address_book``
     - ``AddressBookSyncAdapter(origin, book)``
     - the remote-desktop ``AddressBook``

Three rules hold for every adapter:

* **Secrets stay local.** A field whose name marks it as a secret
  (``password``, ``token``, ``api_key`` ...) leaves as
  ``{"$local": "secret"}``; the receiving machine keeps its own value. A
  ``${secrets.NAME}`` reference travels as it is. A script containing a
  literal secret is not synced at all and is listed under ``withheld``.
* **Machine paths stay local.** A path inside ``scripts_dir`` travels as a
  relative reference and is resolved against the receiver's own folder. Any
  other path becomes ``{"$local": "path"}``; an item that needs it and has no
  local value is reported under ``skipped`` -- and its absence here is *not*
  turned into a deletion for the other machines.
* **Syncing never enables anything.** ``enabled`` is not synced. A hotkey or
  trigger that arrives is created **disabled** (``HotkeyDaemon.bind(...,
  enabled=False)``), an existing one keeps the state this machine gave it,
  and no adapter starts an engine or runs a script.

**Composite triggers.** ``AllOfTrigger`` / ``AnyOfTrigger`` / ``SequenceTrigger``
travel as their own fields plus a ``children`` list of definitions, nested as
deep as the composite is:

.. code-block:: json

    {"type": "AllOfTrigger", "repeat": true, "cooldown_seconds": 30.0,
     "script_path": {"$local": "path", "root": "scripts", "relative": "report.json"},
     "children": [
       {"type": "CronTrigger", "trigger_id": "at-nine", "cron": "0 9 * * *", "...": "..."},
       {"type": "ImageAppearsTrigger", "trigger_id": "logo", "threshold": 0.9,
        "image_path": {"$local": "path", "root": "scripts", "relative": "logo.png"}}]}

A child keeps its ``trigger_id`` and has its paths made portable like any
other; its ``enabled``, ``fired`` and ``script_path`` mean nothing inside a
composite and are not sent. The composite is created **disabled** with
disabled children, and an update keeps whatever this machine chose for
``enabled``. A definition is built completely before it is added, so one bad
child (unknown type, invalid cron, more than 64 children, more than 8 levels)
skips the whole composite and reports it under ``skipped``. A composite
holding a child that is not one of the trigger types above stays local and
is listed under ``withheld``. The RBAC principal that registered a trigger
(``owner``) is never sent. A machine running a release from before this
reports an arriving composite under ``skipped`` ("unknown trigger type") and
leaves the entry in the bucket untouched.

Assets
------

A script up to 64 KiB travels inside its entry together with its SHA-256;
content that does not match the hash is not written. Larger scripts and
other files (template images) travel through an ``AssetTransport``:

.. code-block:: python

    from je_auto_control.utils.config_sync.assets import (
        AssetManifest, DirectoryAssetTransport, publish_assets, sync_assets)

    transport = DirectoryAssetTransport("//nas/autocontrol-assets")   # a folder both machines reach
    manifest = AssetManifest.from_directory("scripts", ("*.png",))
    publish_assets(manifest, transport)                              # sender
    result = sync_assets(AssetManifest(root=their_scripts, assets=manifest.assets), transport)
    # AssetSyncResult(transferred, unchanged, failed, hashes, cancelled)

``sync_assets`` checks every file against its SHA-256 and size *before*
writing, replaces the destination atomically, leaves the existing file alone
when the check fails, and refuses a path that would leave the folder.
Two transports ship; implement ``fetch`` / ``store`` / ``has`` for any other
blob store.

.. list-table::
   :header-rows: 1

   * - Transport
     - Use it when
   * - ``DirectoryAssetTransport(folder)``
     - both machines reach one folder (a share, a mounted bucket);
       ``config_sync_run(..., assets_dir=folder)``
   * - ``HttpAssetTransport(server_url, user_id=..., secret=...)``
     - the machines share only the sync server;
       ``config_sync_run(..., assets_server=True)``

``assets_dir`` and ``assets_server`` together are an error.

**Blobs on the sync server.** The signaling server keeps assets as
content-addressed blobs per account:

.. list-table::
   :header-rows: 1

   * - Request
     - Reply
   * - ``PUT /blobs/{user_id}/{sha256}`` with the raw bytes
     - ``201 {"ok": true, "sha256", "size", "stored": true}``; ``200`` with
       ``"stored": false`` when the account already holds it; ``400`` when the
       bytes do not hash to the digest in the path or the digest is malformed;
       ``413`` over the per-blob cap and ``411`` without ``Content-Length``
       (both before the body is read); ``507`` when the account's quota would
       be exceeded; ``503`` for too many accounts or a failing store
   * - ``GET /blobs/{user_id}/{sha256}``
     - ``200`` with the bytes (``application/octet-stream``), or ``404``
   * - ``HEAD /blobs/{user_id}/{sha256}``
     - ``200`` or ``404``, no body
   * - ``DELETE /blobs/{user_id}/{sha256}``
     - ``200 {"deleted": true | false}``
   * - ``GET /blobs/{user_id}``
     - ``200 {"used", "quota", "count", "max_blob_bytes", "blobs": [{"sha256", "size",
       "age_s"}]}``; ``age_s`` is the seconds since the blob was last stored, by the
       server's clock (a ``PUT`` of content already held counts)

The rules are the ones ``/config`` follows: every request needs the shared
secret (``X-Signaling-Secret``, ``401`` otherwise); the account is the one in
the path, so one account never reads, lists or deletes another's blobs; and
the size cap is checked against ``Content-Length`` before the body is read.
On top of that an account has a **total quota**.

.. list-table::
   :header-rows: 1

   * - Setting
     - Default
     - Flag / ``create_app`` argument
   * - largest single blob
     - 16 MiB
     - ``--max-blob-bytes`` / ``max_blob_bytes``
   * - total per account
     - 256 MiB
     - ``--blob-quota-bytes`` / ``blob_quota_bytes``
   * - where blobs are kept
     - the config database's path with ``.blobs`` added
       (``~/.je_auto_control/config_sync.sqlite3.blobs``)
     - ``--blob-dir`` / ``blob_store_path``
   * - accounts holding blobs
     - 1,024
     - --

The folder is created at the first upload, not at start-up. Storage is
``je_auto_control.utils.config_sync.blobs.BlobStore`` (``put`` / ``get`` /
``has`` / ``delete`` / ``usage``); each account's blobs are in a folder named
by a hash of the account id, and a blob is written to a temporary file and
renamed. A write holds the lock file ``<blob folder>/store.lock`` (the helper
the shared JSON stores use), so the quota check and the write are one step
for **every** server process sharing the folder, not only for the threads of
one. A lock another process keeps for more than ten seconds is
``BlobStoreBusyError`` (``503``) and nothing is written; a lock left by a
process that died is taken over after thirty seconds.

``HttpAssetTransport`` goes through ``je_auto_control.utils.http_client`` (the
egress policy applies) and does not follow redirects. A refused upload says
why -- too large, quota used up, wrong secret, or a server that predates
``/blobs`` -- and ``publish_assets`` reports it per file under ``failed``
without stopping the other files. The ``/blobs`` routes are additions: the
``/config`` wire format is still version 2, and a client that does not use
them is unaffected.

**Too large is decided before the upload.** The server refuses an oversized
``PUT`` from its declared length and closes the connection; a client still
sending the body could see the reset instead of the ``413``, and the failure
read as a connection error. The transport therefore reads ``max_blob_bytes``
from the listing before its first upload (``transport.max_blob_bytes()``,
asked once and remembered) and refuses a larger file itself, without sending
it: ``asset PUT <sha256>: the file is larger than the server accepts for one
blob (<size> bytes; the limit is <limit>)``.

.. list-table::
   :header-rows: 1

   * - Client
     - Server
     - An oversized file
   * - this release
     - reports ``max_blob_bytes`` (every release that serves ``/blobs``)
     - refused locally with the message above; no body is sent
   * - this release
     - does not report it, or the listing could not be read
     - sent; the server's ``413`` reads "larger than the server accepts". If the
       upload is cut off instead, the listing is asked once more and the same
       reason is given when the file is over the limit it reports
   * - this release
     - no ``/blobs`` at all
     - the ``PUT`` is answered ``404`` / ``405``: "does not serve /blobs"
   * - an earlier release
     - any
     - as before: ``413``, or a connection error when the reset wins

**Housekeeping.** Nothing on the server removes a blob by itself, so the
scripts deleted or replaced over time keep counting against the quota.
``config_sync_collect_blobs(server_url, user_id, keep=None, min_age_s=86400,
dry_run=False, **options)`` deletes the account's blobs that nothing names any
more and returns ``{"deleted": [sha256...], "freed": bytes, "kept": n,
"recent": [sha256...], "failed": {sha256: why}, "dry_run": bool,
"referenced": n}``. What it keeps:

* every SHA-256 named by an entry of the server's bucket (any section, every
  candidate of an entry still in conflict), of this machine's last merged
  state and of its changes still waiting in the outbox
  (``referenced_blob_digests``);
* the digests in ``keep`` (a list or one comma-separated string) -- name
  there what you published yourself with ``publish_assets``, which no bucket
  entry refers to;
* any blob stored less than ``min_age_s`` ago (default one day): a machine
  uploads a file just before it commits the entry naming it. The age is the
  server's ``age_s``, so no two clocks are compared.

``dry_run=True`` deletes nothing and lists what would go. A server that
cannot be reached is ``ConfigSyncError`` and nothing is deleted; a blob that
cannot be deleted is listed under ``failed`` and the rest still go. A blob
removed while some machine still has the file is uploaded again by that
machine's next sync. Against a server from before ``age_s`` nothing is
collected unless ``min_age_s=0``. ``collect_unreferenced_blobs(transport,
referenced, min_age_s=..., dry_run=...)`` is the same sweep for a set of
digests you supply; it takes an ``HttpAssetTransport`` only, because a folder
behind ``DirectoryAssetTransport`` may hold other users' files.

One call, three surfaces
------------------------

``config_sync_run(server_url, user_id, **options)`` runs the whole cycle --
queue local changes, drain the outbox, merge, apply -- and returns
``{state, revision, pending, conflicts, applied, withheld, assets, error,
retry_in_s}`` with ``state`` one of ``synced`` / ``pending`` / ``conflict`` /
``offline`` / ``backing_off`` / ``cancelled`` / ``resync_required``. Being
unable to reach the server is not an exception: the changes stay queued and
the state is ``offline``.

.. list-table::
   :header-rows: 1

   * - State
     - Meaning
   * - ``offline``
     - this run tried the server and failed; ``error`` says how, ``retry_in_s``
       when the queue is sent again by itself
   * - ``backing_off``
     - this run did **not** try: an earlier failure is still inside its retry
       delay (2 s, doubling, at most 300 s). Nothing is known about the server
       now. ``retry_in_s`` is the time left; ``error`` is the earlier failure

Before, both were reported as ``offline``, so a sync asked for just after the
network came back looked like a server that was still down. Pass
``force=True`` to skip the delay once -- the *Sync now* command of the GUI
does -- or ``wait=True`` to sleep through it. ``config_sync_status`` reports
``retry_in_s`` live, and shows ``pending`` instead of ``backing_off`` once the
delay has run out.

Options: ``device_id`` (default: an id created once in
``~/.je_auto_control/config_sync_device_id``), ``secret`` (default
``$AC_SIGNALING_SECRET``), ``sections`` (below), ``assets_server``, ``scripts_dir``, ``locators_path``, ``outbox_path``, ``assets_dir``,
``timeout_s``, ``wait``, ``force``, ``max_attempts``.

**Which sections a sync covers.** ``resolve_sections(sections, scripts_dir=...,
locators_path=...)`` decides, and the report's ``sections`` lists the result.

.. list-table::
   :header-rows: 1

   * - You pass
     - Synced
   * - nothing
     - ``hotkeys``, ``triggers``, ``address_book``
   * - ``scripts_dir``
     - ``hotkeys``, ``triggers``, ``address_book``, ``scripts``
   * - ``scripts_dir`` and ``locators_path``
     - those four and ``locators``
   * - ``sections="scripts"`` and ``scripts_dir``
     - ``scripts`` only
   * - ``sections=["hotkeys", "scripts"]`` and ``scripts_dir``
     - exactly those two

A path **adds** its section to the default three; it does not narrow the sync
to it, so ``scripts_dir`` alone also syncs this machine's hotkeys, triggers
and address book. That default is deliberate -- hotkeys and triggers need
that folder to turn their script paths into portable references -- so it is
unchanged; name ``sections`` (or untick sections in the GUI tab) when you
want less. ``sections`` is a list or one comma-separated
string. An unknown name, a section whose path is missing, and a choice that
names nothing (``[]``, ``","``) are each ``ConfigSyncError``; a name given
twice is synced once.

.. list-table::
   :header-rows: 1

   * - Executor command
     - MCP tool
     - Does
   * - ``AC_config_sync_run``
     - ``ac_config_sync_run``
     - sync once
   * - ``AC_config_sync_status``
     - ``ac_config_sync_status`` (read-only)
     - recorded state, no network, creates nothing
   * - ``AC_config_sync_resolve``
     - ``ac_config_sync_resolve``
     - keep candidate ``choice`` of ``section`` / ``key``
   * - ``AC_config_sync_full_resync``
     - ``ac_config_sync_full_resync``
     - adopt the server's state after being retired; pending changes are discarded and listed
   * - ``AC_config_sync_collect_blobs``
     - ``ac_config_sync_collect_blobs``
     - delete the server's blobs no entry names any more (``keep``, ``min_age_s``, ``dry_run``)

All five are Script Builder commands under **Data**, and all five share one
shape: ``(server_url, user_id, ..., **options)`` with the options listed
above. ``config_sync_status(server_url, user_id, outbox_path=None, **options)``
reads only ``outbox_path`` (still accepted positionally); the other options
are accepted so that one options dict can be passed to every call, and an
unknown name is ``ConfigSyncError`` there as everywhere else.

.. code-block:: json

    [["AC_config_sync_run", {"server_url": "https://sync.example", "user_id": "alice",
                             "secret": "${secrets.sync}", "scripts_dir": "scripts"}]]

GUI
---

The **Config Sync** tab (category *system*) shows the state (with the seconds
until the next automatic attempt while a retry delay is running), the last merged
revision, the number of pending changes, the last successful sync and the
last error, and lists every conflict with its candidates. Its commands --
*Sync now*, *Cancel sync*, *Refresh sync status*, *Keep selected candidate*,
*Full resync*, *Delete unused blobs on the server* (after a confirmation; it
runs ``config_sync_collect_blobs`` with the defaults) -- are in the Actions
menu. A sync runs on a worker thread; cancelling, or closing the tab,
releases it.

The inputs are the server URL, the user id, the shared secret, the scripts
folder, the locator repository file and the shared assets folder, then:

* **Sections to sync** -- one checkbox per section of ``SYNCABLE_SECTIONS``.
  With every box ticked the tab passes no ``sections`` and the default above
  applies. Unticking one passes the ticked ones as ``sections``; a ticked
  section whose path is empty is left out rather than refused, and with
  nothing left the tab says so and does not sync. The status lists the
  sections the last sync covered.
* **Keep large scripts on the sync server** -- passes ``assets_server=True``
  and greys out the shared assets folder, which it replaces.

Everything but the secret is remembered between runs in the GUI settings file
(``WindowSettings.load_form`` / ``save_form``, form ``config_sync``).

Folder mirror and clipboard: no echo
------------------------------------

``FolderSyncEngine.note_received(remote_name, sha256=...)`` marks a file in
the watched folder as having come from the peer; the engine does not push it
back until its content changes locally. ``FolderSyncEngine.poll_once()`` runs
one diff pass on demand.

The receivers call it for you. ``FileTransferReceiver`` (WebRTC) and
``FileReceiver`` (TCP) write a file as ``.<name>.<id>.part`` and, just before
renaming it into place, call ``file_sync.note_incoming(final_path, part_path)``:
every live engine whose folder holds that file records the content's SHA-256.
A file received into a mirrored folder is therefore not sent back, with no
wiring in the caller; when no engine mirrors the folder the file is not even
hashed. ``FolderSyncEngine.relative_name(path)`` says whether an engine
covers a path (a subfolder only with ``include_subdirs``).

**What counts as a change.** The engine records each file's modification
time and size and pushes a file whose either one differs from the record --
no longer only a file whose time is *later*, so a file put back with an older
time is pushed too. A time alone cannot tell two writes in one clock tick
apart (an edit made right after a received file was noted went unsent), so a
file recorded within ``RACY_WINDOW_S`` (2 s) of its own last write is also
remembered by SHA-256 and compared by content until that window has passed.
An older file is never read to decide whether it changed.

**Files still being written.** A changed file is pushed only once two polls
in a row see the same size and modification time, so a large copy is sent
whole one poll later instead of truncated now (a file that never stops
changing, such as a live log, is not pushed until it does). Pass
``wait_until_stable=False`` for the earlier push-on-first-sight behaviour.
Names ending in ``.part``, ``.partial``, ``.tmp`` or ``.crdownload``
(``IN_PROGRESS_SUFFIXES``; override with ``ignore_suffixes=``) are never
mirrored -- including the receivers' own part files, which used to be pushed
while a transfer was running. A program that writes under such a name and
renames when it is done is picked up complete.

``ClipboardEchoGuard`` (``note_remote`` / ``note_sent`` / ``should_send`` /
``reset``) does the same for clipboard content. ``RemoteDesktopHost`` keeps
one per connected viewer and ``RemoteDesktopViewer`` one for its host (reset
on every connect); a received CLIPBOARD message is noted before it is
applied. ``host.broadcast_clipboard_text(text, automatic=True)`` and
``viewer.send_clipboard_text(text, automatic=True)`` (and the ``_image``
forms) are for code that forwards clipboard *changes* by itself: content
that just arrived from that peer, or was already sent to it, is not sent
again -- per viewer, so what one viewer sent still reaches the others.
Without ``automatic`` (a person pressing "send clipboard") the content is
always sent, and remembered. ``broadcast_clipboard_*`` returns how many
viewers it went to; ``send_clipboard_*`` now returns whether it was sent.
The GUI sends the clipboard on a button only, so nothing in it passes
``automatic=True`` yet.
