Cross-Machine Config Sync
=========================

``je_auto_control.utils.config_sync`` keeps one user's hotkeys, triggers,
address book and other small settings the same on several machines. Each user
has one *bucket* on a sync server; the signaling server
(``python -m je_auto_control.utils.remote_desktop.signaling_server``, the
``[signaling]`` extra) serves it at ``GET`` / ``PUT /config/{user_id}``.

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
(default 4) times, then raises ``ConfigSyncConflict``. ``push(bucket)`` uses
``bucket.revision`` as the base, returns the committed revision and raises
``ConfigSyncConflict`` (``.revision`` is the server's current one) instead of
overwriting.

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

    bucket.upsert("hotkeys", "hk1", {"combo": "ctrl+a"}, origin="laptop")   # versioned
    bucket.remove("hotkeys", "hk1", origin="laptop")                        # versioned tombstone
    bucket.values("hotkeys")        # live values; entries still in conflict are left out
    bucket.conflicts()              # [(section, SyncEntry with .siblings), ...]

``upsert`` / ``remove`` *without* ``origin`` still write the older flat entry
stamped with ``last_modified``, and two flat entries still merge by "later
wins" (reported in ``ConflictRecord``); a versioned entry supersedes a flat
copy of the same id. ``ConflictRecord.unresolved`` is true for a causal
conflict, where nothing was dropped.

Deletions and retired devices
-----------------------------

A deletion is a tombstone. A versioned tombstone is **never dropped by age**:
``collect_tombstones`` removes it only when every active device recorded
under the bucket's ``peers`` has acknowledged a revision that includes it.
``ConfigSyncClient.push_operations`` maintains those acknowledgements.

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
     - a ``TriggerEngine``'s image / window / pixel / file / cron triggers
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
  and no adapter starts an engine or runs a script. Composite triggers
  (all-of / any-of / sequence) are not synced.

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
``DirectoryAssetTransport`` is the transport that ships; implement
``fetch`` / ``store`` / ``has`` for any other blob store.

One call, three surfaces
------------------------

``config_sync_run(server_url, user_id, **options)`` runs the whole cycle --
queue local changes, drain the outbox, merge, apply -- and returns
``{state, revision, pending, conflicts, applied, withheld, assets, error}``
with ``state`` one of ``synced`` / ``pending`` / ``conflict`` / ``offline`` /
``cancelled`` / ``resync_required``. Being unable to reach the server is not
an exception: the changes stay queued and the state is ``offline``.

Options: ``device_id`` (default: an id created once in
``~/.je_auto_control/config_sync_device_id``), ``secret`` (default
``$AC_SIGNALING_SECRET``), ``sections`` (default ``hotkeys``, ``triggers``,
``address_book``; ``scripts`` and ``locators`` join when their path is
given), ``scripts_dir``, ``locators_path``, ``outbox_path``, ``assets_dir``,
``timeout_s``, ``wait``, ``max_attempts``.

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

All four are Script Builder commands under **Data**.

.. code-block:: json

    [["AC_config_sync_run", {"server_url": "https://sync.example", "user_id": "alice",
                             "secret": "${secrets.sync}", "scripts_dir": "scripts"}]]

GUI
---

The **Config Sync** tab (category *system*) shows the state, the last merged
revision, the number of pending changes, the last successful sync and the
last error, and lists every conflict with its candidates. Its commands --
*Sync now*, *Cancel sync*, *Refresh sync status*, *Keep selected candidate*,
*Full resync* -- are in the Actions menu. A sync runs on a worker thread;
cancelling, or closing the tab, releases it.

Folder mirror and clipboard: no echo
------------------------------------

``FolderSyncEngine.note_received(remote_name, sha256=...)`` marks a file in
the watched folder as having come from the peer; the engine does not push it
back until its content changes locally. ``FolderSyncEngine.poll_once()`` runs
one diff pass on demand. ``ClipboardEchoGuard`` (``note_remote`` /
``should_send`` / ``reset``) does the same for code that forwards clipboard
changes automatically: content that just arrived from the peer, or was
already sent, is not sent again.
