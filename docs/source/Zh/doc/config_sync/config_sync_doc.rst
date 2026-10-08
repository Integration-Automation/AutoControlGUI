跨機器設定同步
==============

``je_auto_control.utils.config_sync`` 讓同一位使用者的快捷鍵、觸發器、通訊錄與其他小型設定
在多台機器上保持一致。每位使用者在同步 server 上有一個 *bucket*；signaling server
(``python -m je_auto_control.utils.remote_desktop.signaling_server``,需要 ``[signaling]`` extra)
以 ``GET`` / ``PUT /config/{user_id}`` 提供它。

腳本需要的名稱都在套件門面上:``import je_auto_control as ac`` 之後有
``ac.config_sync_run`` 與另外三個入口、``ac.run_sync``、``ac.ConfigSyncClient``、
``ac.ConfigBucket``、``ac.SyncOutbox``、``ac.SyncEntry``、``ac.SyncOperation``、
``ac.SyncAdapter`` 與五個具體 adapter(``ac.ScriptSyncAdapter`` ……)、
``ac.DirectoryAssetTransport``、``ac.HttpAssetTransport``、``ac.ConfigStore``、``ac.BlobStore``、
各個錯誤(``ac.ConfigSyncError``、``ac.ConfigSyncConflict``、``ac.FullResyncRequired``、
``ac.OperationMismatchError``、``ac.ConfigStoreError``、``ac.RevisionConflictError``)、
blob 清理(``ac.config_sync_collect_blobs``、``ac.collect_unreferenced_blobs``、
``ac.referenced_blob_digests``)
以及 ``ac.CONFIG_SYNC_WIRE_VERSION``(模組內的 ``WIRE_VERSION``,值為 ``2``)。
其餘的仍可從 ``je_auto_control.utils.config_sync`` 匯入。

Server:持久化、檢查修訂版的 bucket
-----------------------------------

Bucket 由 ``je_auto_control.utils.config_sync.store.ConfigStore`` 存在一個 SQLite 檔案,
server 重啟後仍在。檔案位置依序取自 ``--config-db PATH``、環境變數
``AC_SIGNALING_CONFIG_DB``、預設的 ``~/.je_auto_control/config_sync.sqlite3``;
在第一個 ``/config`` 請求時才開啟,不是啟動時。內嵌 app 時傳
``create_app(config_store_path=...)``。

每個 bucket 有 server 指派的 **revision**\ (第一次寫入為 ``1``,之後每次 commit ``+1``)。
寫入必須指明它所依據的 revision,比較與寫入在同一個 SQLite transaction 內完成:

.. code-block:: python

    from je_auto_control.utils.config_sync.store import ConfigStore, RevisionConflictError

    store = ConfigStore("buckets.sqlite3")
    revision = store.commit("alice", bucket, base_revision=0, operation_id="op-1")   # -> 1
    store.commit("alice", bucket, base_revision=0, operation_id="op-1")              # -> 仍是 1
    store.commit("alice", other, base_revision=0, operation_id="op-2")               # RevisionConflictError

重複的 ``operation_id`` 會回傳第一次 commit 產生的 revision 且不寫入任何東西,
所以沒收到回覆的 client 直接重送同一個請求即可。每位使用者保留最近 256 個 operation id。

一個 operation id 只代表 *一次* 寫入。Store 會記下每個 id 寫入內容的 SHA-256
(base revision 加上去掉 ``revision`` 欄位的 bucket),同一個 id 帶著不同的 bucket 或
base revision 送來時丟出 ``OperationMismatchError``\ (``.operation_id``、第一次寫入的
``.revision``)且不寫入 —— 以前會被當成已提交來回覆。沒有記 hash 的舊版所留下的 id
仍照舊方式回覆;既有資料庫在第一次使用時補上這個欄位。

傳輸格式(version 2)
---------------------

.. list-table::
   :header-rows: 1

   * - 請求
     - 回覆
   * - ``GET /config/{user_id}``
     - ``200`` 與 ``{"user_id", "sections", "peers", "revision": <已提交>, "version": 2}``,
       使用者沒有 bucket 時為 ``404``。
   * - ``PUT /config/{user_id}``,body 為
       ``{"version": 2, "base_revision": N, "operation_id": "...", "bucket": {...}}``
     - ``200 {"ok": true, "revision": N + 1, "version": 2}``;bucket 已不在 ``N`` 時
       ``409 {"detail": "revision conflict", "revision": <目前>}``(不寫入);
       ``operation_id`` 已被用於另一次寫入時
       ``409 {"code": "operation_mismatch", "revision": <第一次寫入的>}``(不寫入);
       envelope 或 bucket 格式錯誤、或 bucket 指名另一位使用者時 ``400``。
   * - ``PUT /config/{user_id}``,body 為裸 bucket(version 2 之前的格式)
     - ``428`` —— 除非 server 以 ``--allow-blind-config-writes``
       (``create_app(allow_blind_config_writes=True)``)啟動,此時不檢查直接覆寫,
       回覆 ``200 {"ok": true, "revision": ...}``。

``base_revision`` 為 ``0`` 表示「還沒有 bucket」。共享密鑰(``X-Signaling-Secret``)、
1 MiB body 上限(``413``,讀取 body 前檢查)、必須帶 ``Content-Length``(``411``)與
1,024 位使用者上限(``503``)都不變。Bucket 現在在進入時驗證:section 必須是
entry id 對應到物件的 mapping。

**早於 version 2 的 client** 送出裸 bucket。面對預設模式的 server,它們的 ``push`` / ``sync``
會以 ``ConfigSyncError: config sync PUT returned HTTP 428`` 失敗且不寫入任何東西;
``fetch`` 照常運作(回覆欄位相同,多一個它們會忽略的 ``version``)。要繼續服務它們,
以 ``--allow-blind-config-writes`` 啟動 server,並接受兩個這種 client 同時 push 仍可能互相覆寫。
**version-2 client 面對舊 server** 會被明確告知:回覆沒有 revision, ``push`` 丟出
``ConfigSyncError``\ (「predates revision-checked writes」)—— 請先升級 server。

Client
------

.. code-block:: python

    from je_auto_control.utils.config_sync import ConfigBucket, ConfigSyncClient, ConfigSyncConflict

    client = ConfigSyncClient("https://sync.example", user_id="alice", secret="...")
    merged, conflicts = client.sync(local_bucket)     # fetch、merge、在所 fetch 的版本上 push
    print(merged.revision)                            # server 提交的 revision

``sync`` 以 fetch 到的 revision 作為 ``base_revision`` push;若期間有另一台機器 push,
它會重新 fetch 與 merge,最多 ``max_attempts``(預設 4)次,之後丟出 ``ConfigSyncConflict``。
每次 ``sync`` 也會把 client 的裝置
(``ConfigSyncClient(..., device_id=...)``,預設為本機儲存的 id)記在 bucket 的 ``peers`` 下,
表示它已合併所提交的 revision,並移除每台裝置都看過的 tombstone —— 和 ``push_operations``
做的記帳相同。被群組退休的裝置呼叫 ``sync`` 同樣會得到 ``FullResyncRequired``。
``push(bucket)`` 以 ``bucket.revision`` 為基準,回傳已提交的 revision;落後時丟出
``ConfigSyncConflict``(``.revision`` 為 server 目前的 revision)而不是覆寫。
``code`` 為 ``operation_mismatch`` 的 ``409`` 則丟出 ``OperationMismatchError``;
它是 ``ConfigSyncError`` 但不是 ``ConfigSyncConflict``,所以 ``sync`` 不會重新 fetch 重試。
還不認得這個 code 的 client 會把這個回覆當成一般的衝突。

因果合併:時鐘不決定勝負
------------------------

帶裝置 id 寫入的 entry 是 *versioned*
(``je_auto_control.utils.config_sync.versions.SyncEntry``):它帶有 version vector
(每台裝置的變更有幾次已包含在內)、``origin`` 裝置與 ``operation_id``。
``merge_entries(left, right)`` 回傳 ``MergeDecision``:

* *知道* 對方而做出的那一筆取代對方 —— 不回報任何東西;
* 分開進行、針對同一 key 的兩個變更 **兩份都保留**:``decision.conflict`` 是
  ``SyncConflict(key, local, remote)``,``decision.entry`` 以 ``siblings`` 保存候選,
  直到有人呼叫 ``entry.resolved(value, origin)``。與刪除並行的編輯同樣是衝突;
* 不同 key 的變更不會衝突(``merge_collections``)。

``modified_at`` 只供顯示。無論各機器的時鐘怎麼說,決定都相同,而且每台機器算出的結果一致。

.. code-block:: python

    bucket.upsert("hotkeys", "hk1", {"combo": "ctrl+a"})                    # versioned,由本機寫入
    bucket.upsert("hotkeys", "hk1", {"combo": "ctrl+b"}, origin="laptop")   # ……或指名裝置
    bucket.remove("hotkeys", "hk1")                                         # versioned tombstone
    bucket.values("hotkeys")        # 有效值;仍在衝突中的 entry 不列入
    bucket.conflicts()              # [(section, 帶 .siblings 的 SyncEntry), ...]

``origin`` 預設為本機的裝置 id(``default_device_id()``,存在
``~/.je_auto_control/config_sync_device_id``),所以在 version vector 之前寫的程式 ——
``bucket.upsert(section, id, value)`` 與 ``client.sync(bucket)`` —— 不必修改就是因果合併。
傳給 ``upsert`` 的值裡若有 ``last_modified``,它會成為 entry 的顯示時間,不存進值裡。
對扁平 entry 呼叫 ``remove`` 會寫入 versioned tombstone,並取代所有扁平副本。

.. warning::

   這改變了 ``upsert`` 儲存的內容。Entry 現在是
   ``{"value": {...}, "vector": {...}, "origin": ..., "operation_id": ...,
   "deleted": false, "last_modified": ...}`` 而不是值本身,所以請用
   ``bucket.values(section)``\ (兩種形狀都適用)讀值,不要用
   ``bucket.sections[section][id]["field"]``。要繼續寫扁平 entry,對 ``upsert`` / ``remove``
   傳 ``versioned=False``;兩筆扁平 entry 仍以「較晚者勝」合併(回報於 ``ConflictRecord``),
   versioned entry 會取代同 id 的扁平副本。因果衝突的 ``ConflictRecord.unresolved`` 為 true,
   此時沒有任何東西被丟棄。

**既有 bucket 在第一次用這個版本同步之後。** 本機沒碰過的扁平 entry 原封不動
(位元組相同,彼此之間仍是「較晚者勝」)。本機新增、編輯或移除的 entry 以 versioned 形式儲存,
vector 為 ``{"<裝置 id>": n}``。``peers`` 多出
``{"<裝置 id>": {"acked_revision": <提交的 revision>, "last_seen": ..., "retired": false}}``。
這個版本之前的 version-2 client 讀得懂全部內容:它本來就認得兩種 entry 形狀,
不認得的 peer 會忽略。Tombstone 只會 *等* 已列在 ``peers`` 下的裝置,還沒同步過的機器改由下面說明的
保留期涵蓋:刪除會在 bucket 裡留三十天,這樣的機器在這段時間內第一次同步時會遇到它。
請讓每台機器在刪除後的三十天內同步一次,或是在刪除之前就先同步過。

刪除與退休裝置
--------------

刪除是一個 tombstone。Versioned tombstone **絕不因時間而丟棄**:``collect_tombstones``
只在 bucket 的 ``peers`` 記錄的每台有效裝置都已確認包含它的 revision 之後才移除。
``ConfigSyncClient.push_operations`` 負責維護這些確認。

**為 bucket 還沒列出的機器保留。** 確認只涵蓋 ``peers`` 下的裝置。手上有那筆 entry、
但從沒同步過的機器不在其中;tombstone 一旦被移除,它的第一次同步就會把 entry 直接加回來,
沒有衝突也沒有回報。所以已被確認的 tombstone 還會從第一次帶著它的那次提交起再保留
``TOMBSTONE_HOLD_S``(三十天)。在這段時間內加入的機器會遇到這筆刪除:它的 versioned 副本變成
**衝突**(刪除與副本並存,由人用 ``config_sync_resolve`` 決定),扁平副本則維持刪除並回報於
``ConflictRecord``。保留期過後,任何裝置的下一次提交會移除 tombstone,所以 bucket 不會無限成長;
比這更晚才第一次同步的機器仍然可能把 entry 帶回來。

第一次帶著 tombstone 的那次提交,會在 ``deleted_revision`` 旁邊蓋上 ``deleted_at``(該裝置的時鐘)。
時間只會是 *多留一陣子* 的理由:時鐘不準只會讓保留期變短或變長,不會影響對已列出裝置的等待。
``ConfigSyncClient(..., tombstone_hold_s=0)`` 可讓該 client 提交的 bucket 回到先前的規則;
``collect_tombstones(entries, peers, now=..., hold_s=...)`` 只有在給了 ``now`` 時才套用保留期。
這個版本之前蓋章的 tombstone 沒有 ``deleted_at``,和以前一樣在確認後就移除;那樣的版本也不會保留
已確認的 tombstone,所以保留期的效果取決於仍在提交的最舊 client。

裝置在第一次 push 時加入 ``peers``;bucket 還沒列出的裝置呼叫 ``push_operations([])``,
在 bucket 有 entry 時就是這樣的一次 push(之後的刪除必須等它),在 bucket 沒有任何 entry 時
不寫入任何東西 —— 空帳號的第一次同步不會提交 revision。

不會再回來的裝置以 ``client.retire_peer(device_id)`` 退休(或以
``push_operations(..., max_offline_s=...)`` 自動退休,它比較 ``last_seen`` ——
這是唯一用到時鐘的地方,而且從不在兩個值之間做決定)。Tombstone 不再等待已退休的裝置,
所以它回來時 push 會被 ``FullResyncRequired`` 拒絕;它必須呼叫
``client.full_resync(device_id=...)``,以回傳的 bucket 取代本機狀態並丟棄待送操作。
改用合併可能讓已刪除的 entry 復活。

離線 outbox
-----------

``SyncOutbox(db_path, account=..., endpoint=...)`` 是尚未送達 server 的
``SyncOperation(section, entry)`` 的 SQLite 佇列(預設檔案
``~/.je_auto_control/config_sync_outbox.sqlite3``;一個檔案可容納多個帳號與 endpoint,彼此隔離)。

.. code-block:: python

    from je_auto_control.utils.config_sync import SyncEntry, SyncOperation, SyncOutbox

    outbox = SyncOutbox(account="alice", endpoint="https://sync.example")
    outbox.enqueue(SyncOperation("hotkeys", SyncEntry.create("hk1", {"combo": "ctrl+a"}, "laptop")))
    report = outbox.drain(
        lambda batch: client.push_operations(batch, device_id="laptop"), cancel=stop_event)
    # DrainReport(sent, pending, attempts, offline, cancelled, error)

操作以 operation id 入列(同一筆入列兩次不會重複)、重啟後仍在,並以相同 id 重送 ——
套用 server 已有的批次不會改變任何東西。送出失敗時退避 2 秒、4 秒、8 秒……最多 300 秒
(``base_delay_s`` / ``max_delay_s``),一次 drain 最多送 ``max_attempts`` 次(預設 5),
``wait=False`` 會直接返回而不在退避期間睡眠,設定 ``cancel`` 即使在等待中途也會結束 drain。

佇列仍在退避期間時,drain 不送任何東西,回傳
``DrainReport(backing_off=True, retry_in_s=<剩餘秒數>)``;``offline`` 同時為 true(佇列沒有送出去),
``error`` 是造成等待的那次失敗。``drain(..., force=True)`` 不管延遲直接送一次;
如果這次也失敗,就遵守它換來的(更長的)延遲。

Adapter:同步什麼、什麼留在本機
--------------------------------

``je_auto_control.utils.config_sync.adapters`` 把一個 bucket section 接到一個本機儲存。
``SyncAdapter.snapshot()`` 回傳以上次合併狀態為基準的 ``{key: SyncEntry}``,
``apply(entries)`` 把合併後的 entry 寫回並回傳 ``ApplyReport``
(``written`` / ``removed`` / ``skipped`` / ``conflicts`` / ``left_disabled``)。

.. list-table::
   :header-rows: 1

   * - Section
     - Adapter
     - 本機儲存
   * - ``scripts``
     - ``ScriptSyncAdapter(origin, scripts_dir)``
     - 資料夾下的 ``*.json`` 動作檔,以相對路徑為 key
   * - ``locators``
     - ``LocatorSyncAdapter(origin, repository)``
     - 一個 ``ElementRepository``
   * - ``hotkeys``
     - ``HotkeySyncAdapter(origin, daemon, scripts_dir=...)``
     - ``HotkeyDaemon`` 的綁定
   * - ``triggers``
     - ``TriggerSyncAdapter(origin, engine, scripts_dir=...)``
     - ``TriggerEngine`` 的 image / window / pixel / file / cron 觸發器,
       以及由它們組成的 all-of / any-of / sequence 複合觸發器
   * - ``address_book``
     - ``AddressBookSyncAdapter(origin, book)``
     - 遠端桌面的 ``AddressBook``

每個 adapter 都遵守三條規則:

* **秘密留在本機。** 名稱顯示為秘密的欄位(``password``、``token``、``api_key`` ……)
  以 ``{"$local": "secret"}`` 送出;接收端保留自己的值。``${secrets.NAME}`` 參照原樣傳送。
  含有明文秘密的腳本完全不同步,並列在 ``withheld``。
* **機器路徑留在本機。** ``scripts_dir`` 內的路徑以相對參照傳送,並對接收端自己的資料夾解析。
  其他路徑變成 ``{"$local": "path"}``;需要它而本機沒有對應值的項目回報在 ``skipped``
  —— 而且它在本機不存在 *不會* 被當成對其他機器的刪除。
* **同步絕不啟用任何東西。** ``enabled`` 不同步。送達的快捷鍵或觸發器以 **停用** 狀態建立
  (``HotkeyDaemon.bind(..., enabled=False)``),既有的保留本機給它的狀態,
  沒有任何 adapter 會啟動引擎或執行腳本。

**複合觸發器。** ``AllOfTrigger`` / ``AnyOfTrigger`` / ``SequenceTrigger`` 以自己的欄位
加上一個 ``children`` 定義清單傳送,巢狀幾層就傳幾層:

.. code-block:: json

    {"type": "AllOfTrigger", "repeat": true, "cooldown_seconds": 30.0,
     "script_path": {"$local": "path", "root": "scripts", "relative": "report.json"},
     "children": [
       {"type": "CronTrigger", "trigger_id": "at-nine", "cron": "0 9 * * *", "...": "..."},
       {"type": "ImageAppearsTrigger", "trigger_id": "logo", "threshold": 0.9,
        "image_path": {"$local": "path", "root": "scripts", "relative": "logo.png"}}]}

子觸發器保留它的 ``trigger_id``,路徑和其他路徑一樣轉成可攜形式;它的 ``enabled``、``fired`` 與
``script_path`` 在複合觸發器內沒有意義,不會送出。複合觸發器以 **停用** 狀態建立,子觸發器也是停用;
之後的更新會保留本機對 ``enabled`` 的選擇。定義會先完整建好才加入引擎,所以只要有一個子觸發器不對
(不認得的型別、無效的 cron、超過 64 個子觸發器、超過 8 層)整個複合觸發器就跳過,並回報在 ``skipped``。
含有上述型別以外的子觸發器的複合觸發器留在本機,列在 ``withheld``。註冊觸發器的 RBAC 身分
(``owner``)絕不送出。執行較舊版本的機器收到複合觸發器時會回報在 ``skipped``
(「unknown trigger type」),bucket 裡的 entry 不受影響。

資產
----

64 KiB 以內的腳本連同它的 SHA-256 放在 entry 內傳送;內容與 hash 不符就不寫入。
更大的腳本與其他檔案(樣板圖)經由 ``AssetTransport`` 傳送:

.. code-block:: python

    from je_auto_control.utils.config_sync.assets import (
        AssetManifest, DirectoryAssetTransport, publish_assets, sync_assets)

    transport = DirectoryAssetTransport("//nas/autocontrol-assets")   # 兩台機器都能存取的資料夾
    manifest = AssetManifest.from_directory("scripts", ("*.png",))
    publish_assets(manifest, transport)                              # 傳送端
    result = sync_assets(AssetManifest(root=their_scripts, assets=manifest.assets), transport)
    # AssetSyncResult(transferred, unchanged, failed, hashes, cancelled)

``sync_assets`` 在寫入 *之前* 以 SHA-256 與大小檢查每個檔案、以原子方式取代目的檔、
檢查失敗時不動既有檔案,並拒絕會離開資料夾的路徑。隨附兩種 transport;
其他 blob 儲存請實作 ``fetch`` / ``store`` / ``has``。

.. list-table::
   :header-rows: 1

   * - Transport
     - 適用情況
   * - ``DirectoryAssetTransport(folder)``
     - 兩台機器都能存取同一個資料夾(共用磁碟、掛載的 bucket);
       ``config_sync_run(..., assets_dir=folder)``
   * - ``HttpAssetTransport(server_url, user_id=..., secret=...)``
     - 兩台機器只共用同步 server;
       ``config_sync_run(..., assets_server=True)``

同時給 ``assets_dir`` 與 ``assets_server`` 是錯誤。

**同步 server 上的 blob。** Signaling server 以「依內容定址、依帳號分開」的 blob 保存資產:

.. list-table::
   :header-rows: 1

   * - 請求
     - 回覆
   * - ``PUT /blobs/{user_id}/{sha256}``,body 為原始位元組
     - ``201 {"ok": true, "sha256", "size", "stored": true}``;帳號已有該內容時 ``200`` 且
       ``"stored": false``;位元組的 hash 與路徑中的 digest 不符、或 digest 格式錯誤時 ``400``;
       超過單一 blob 上限時 ``413``、沒有 ``Content-Length`` 時 ``411``(都在讀取 body 之前);
       會超過帳號配額時 ``507``;帳號數過多或儲存失敗時 ``503``
   * - ``GET /blobs/{user_id}/{sha256}``
     - ``200`` 與位元組(``application/octet-stream``),或 ``404``
   * - ``HEAD /blobs/{user_id}/{sha256}``
     - ``200`` 或 ``404``,沒有 body
   * - ``DELETE /blobs/{user_id}/{sha256}``
     - ``200 {"deleted": true | false}``
   * - ``GET /blobs/{user_id}``
     - ``200 {"used", "quota", "count", "max_blob_bytes", "blobs": [{"sha256", "size",
       "age_s"}]}``;``age_s`` 是以 server 的時鐘計算、距離該 blob 上次被存入的秒數
       (``PUT`` 已經持有的內容也算一次)

規則和 ``/config`` 相同:每個請求都要帶共享密鑰(``X-Signaling-Secret``,否則 ``401``);
帳號就是路徑中的那個,所以一個帳號無法讀取、列出或刪除另一個帳號的 blob;
大小上限在讀取 body 之前就以 ``Content-Length`` 檢查。除此之外每個帳號還有 **總配額**。

.. list-table::
   :header-rows: 1

   * - 設定
     - 預設
     - 旗標 / ``create_app`` 參數
   * - 單一 blob 上限
     - 16 MiB
     - ``--max-blob-bytes`` / ``max_blob_bytes``
   * - 每個帳號的總量
     - 256 MiB
     - ``--blob-quota-bytes`` / ``blob_quota_bytes``
   * - blob 存放位置
     - config 資料庫路徑加上 ``.blobs``
       (``~/.je_auto_control/config_sync.sqlite3.blobs``)
     - ``--blob-dir`` / ``blob_store_path``
   * - 持有 blob 的帳號數
     - 1,024
     - --

資料夾在第一次上傳時才建立,不是啟動時。儲存由
``je_auto_control.utils.config_sync.blobs.BlobStore`` 負責(``put`` / ``get`` / ``has`` /
``delete`` / ``usage``);每個帳號的 blob 放在以帳號 id 的 hash 命名的資料夾,blob 先寫到暫存檔再改名。
寫入時會持有鎖檔 ``<blob 資料夾>/store.lock``(和共用 JSON store 相同的 helper),
所以配額檢查與寫入對 **每一個** 共用該資料夾的 server 行程都是同一步,不只是單一行程內的執行緒。
鎖被另一個行程持有超過十秒時是 ``BlobStoreBusyError``(``503``),不寫入任何東西;
行程當掉留下的鎖會在三十秒後被接手。

``HttpAssetTransport`` 經由 ``je_auto_control.utils.http_client``(egress policy 適用),不跟隨轉址。
被拒絕的上傳會說明原因 —— 太大、配額用完、密鑰錯誤、或 server 還沒有 ``/blobs`` ——
``publish_assets`` 會把它逐檔回報在 ``failed``,不會中斷其他檔案。``/blobs`` 路由是新增的:
``/config`` 的傳輸格式仍是 version 2,不使用它們的 client 不受影響。

**「太大」在上傳之前就決定。** Server 依宣告的長度拒絕過大的 ``PUT`` 並關閉連線;
還在送 body 的 client 可能先看到連線被重設而不是 ``413``,失敗就被讀成連線錯誤。
所以 transport 會在第一次上傳前從清單讀出 ``max_blob_bytes``
(``transport.max_blob_bytes()``,只問一次並記住),比它大的檔案由本機直接拒絕、不送出:
``asset PUT <sha256>: the file is larger than the server accepts for one blob
(<size> bytes; the limit is <limit>)``。

.. list-table::
   :header-rows: 1

   * - Client
     - Server
     - 過大的檔案
   * - 這個版本
     - 回報 ``max_blob_bytes``(所有提供 ``/blobs`` 的版本)
     - 在本機以上述訊息拒絕;不送出 body
   * - 這個版本
     - 沒有回報,或清單讀不到
     - 照常送出;server 的 ``413`` 會讀成「larger than the server accepts」。若上傳是被切斷的,
       會再問一次清單,檔案超過它回報的上限時給出同樣的原因
   * - 這個版本
     - 完全沒有 ``/blobs``
     - ``PUT`` 得到 ``404`` / ``405``:「does not serve /blobs」
   * - 較早的版本
     - 任何
     - 和以前一樣:``413``,或在重設先到時是連線錯誤

**清理。** Server 上沒有任何東西會自動移除 blob,所以被刪除或被取代的腳本會一直佔用配額。
``config_sync_collect_blobs(server_url, user_id, keep=None, min_age_s=86400,
dry_run=False, **options)`` 刪除該帳號已經沒有任何東西引用的 blob,並回傳
``{"deleted": [sha256...], "freed": bytes, "kept": n, "recent": [sha256...],
"failed": {sha256: 原因}, "dry_run": bool, "referenced": n}``。會保留的有:

* server 的 bucket、本機上次合併的狀態、以及本機還在 outbox 等待送出的變更中,
  任何 entry 指名的 SHA-256(任何 section,包含仍在衝突中的每個候選;``referenced_blob_digests``);
* ``keep`` 裡的 digest(list 或一個逗號分隔的字串)—— 自己用 ``publish_assets`` 發佈、
  沒有任何 bucket entry 引用的內容請列在這裡;
* 存入不到 ``min_age_s`` 的 blob(預設一天):機器會在提交引用它的 entry 之前先上傳檔案。
  年齡用的是 server 的 ``age_s``,不會比較兩台機器的時鐘。

``dry_run=True`` 不刪除任何東西,只列出會被刪的。連不到 server 是 ``ConfigSyncError``,
不會刪除任何東西;刪不掉的 blob 列在 ``failed``,其餘照常處理。某台機器還有檔案時被移除的 blob,
會在那台機器下次同步時重新上傳。面對還沒有 ``age_s`` 的 server,除非 ``min_age_s=0`` 否則什麼都不收。
``collect_unreferenced_blobs(transport, referenced, min_age_s=..., dry_run=...)``
是對你自己提供的 digest 集合做同樣的清理;它只接受 ``HttpAssetTransport``,因為
``DirectoryAssetTransport`` 背後的資料夾可能有其他使用者的檔案。

一個呼叫,三個介面
------------------

``config_sync_run(server_url, user_id, **options)`` 執行整個循環 —— 把本機變更入列、
清空 outbox、合併、套用 —— 並回傳
``{state, revision, pending, conflicts, applied, withheld, assets, error, retry_in_s}``,
``state`` 為 ``synced`` / ``pending`` / ``conflict`` / ``offline`` / ``backing_off`` /
``cancelled`` / ``resync_required`` 之一。連不到 server 不是例外:變更留在佇列,狀態為 ``offline``。

.. list-table::
   :header-rows: 1

   * - 狀態
     - 意義
   * - ``offline``
     - 這次執行連過 server 而且失敗;``error`` 說明原因,``retry_in_s`` 是佇列自己再送一次的時間
   * - ``backing_off``
     - 這次執行 **沒有** 連 server:先前的失敗還在退避期間(2 秒起、加倍、最長 300 秒)。
       現在 server 的狀況未知。``retry_in_s`` 是剩餘時間,``error`` 是先前那次失敗

以前兩者都回報 ``offline``,所以網路剛恢復時要求同步,看起來就像 server 還沒好。
傳 ``force=True`` 可以跳過一次延遲(GUI 的 *立即同步* 會這樣做),或傳 ``wait=True`` 睡到延遲結束。
``config_sync_status`` 的 ``retry_in_s`` 是即時計算的,延遲結束後顯示 ``pending`` 而不是 ``backing_off``。

選項:``device_id``(預設:在 ``~/.je_auto_control/config_sync_device_id`` 建立一次的 id)、
``secret``(預設 ``$AC_SIGNALING_SECRET``)、``sections``(見下)、``assets_server``、``scripts_dir``、
``locators_path``、``outbox_path``、``assets_dir``、``timeout_s``、``wait``、``force``、
``max_attempts``。

**一次同步涵蓋哪些 section。** 由 ``resolve_sections(sections, scripts_dir=...,
locators_path=...)`` 決定,回報的 ``sections`` 會列出結果。

.. list-table::
   :header-rows: 1

   * - 傳入
     - 同步的 section
   * - 什麼都不傳
     - ``hotkeys``、``triggers``、``address_book``
   * - ``scripts_dir``
     - ``hotkeys``、``triggers``、``address_book``、``scripts``
   * - ``scripts_dir`` 與 ``locators_path``
     - 以上四個再加 ``locators``
   * - ``sections="scripts"`` 與 ``scripts_dir``
     - 只有 ``scripts``
   * - ``sections=["hotkeys", "scripts"]`` 與 ``scripts_dir``
     - 正好這兩個

路徑是把它的 section **加到** 預設的三個上,不是把同步縮小到它,所以只傳 ``scripts_dir``
也會同步本機的快捷鍵、觸發器與通訊錄。這個預設是刻意的 —— 快捷鍵與觸發器需要那個資料夾
才能把腳本路徑變成可攜的參照 —— 所以維持不變;
想少同步一些就指名 ``sections``(或在 GUI 分頁取消勾選 section)。``sections`` 可以是 list 或一個逗號分隔的字串。
不認得的名稱、缺少路徑的 section、以及什麼都沒指名的選擇(``[]``、``","``)都是
``ConfigSyncError``;同一個名稱寫兩次只同步一次。

.. list-table::
   :header-rows: 1

   * - Executor 指令
     - MCP 工具
     - 作用
   * - ``AC_config_sync_run``
     - ``ac_config_sync_run``
     - 同步一次
   * - ``AC_config_sync_status``
     - ``ac_config_sync_status``\ (唯讀)
     - 已記錄的狀態;不連網、不建立任何東西
   * - ``AC_config_sync_resolve``
     - ``ac_config_sync_resolve``
     - 保留 ``section`` / ``key`` 的第 ``choice`` 個候選
   * - ``AC_config_sync_full_resync``
     - ``ac_config_sync_full_resync``
     - 被退休後採用 server 的狀態;待送變更會被捨棄並列出
   * - ``AC_config_sync_collect_blobs``
     - ``ac_config_sync_collect_blobs``
     - 刪除 server 上已沒有 entry 指名的 blob(``keep``、``min_age_s``、``dry_run``)

五個都是 Script Builder **Data** 分類下的指令,而且形狀一致:
``(server_url, user_id, ..., **options)``,options 即上面列的那些。
``config_sync_status(server_url, user_id, outbox_path=None, **options)`` 只讀 ``outbox_path``
(仍可用位置參數傳);其他選項會被接受,讓同一個 options dict 可以傳給每一個呼叫,
不認得的名稱和其他地方一樣是 ``ConfigSyncError``。

.. code-block:: json

    [["AC_config_sync_run", {"server_url": "https://sync.example", "user_id": "alice",
                             "secret": "${secrets.sync}", "scripts_dir": "scripts"}]]

GUI
---

**設定同步** 分頁(分類 *system*)顯示狀態(退避期間會附上距離下次自動重試的秒數)、最後合併的 revision、待送變更數、
上次成功同步與最後的錯誤,並列出每個衝突及其候選。它的指令 —— *立即同步*、*取消同步*、
*重新整理同步狀態*、*保留所選候選*、*完整重新同步*、*刪除伺服器上未使用的 blob*
(會先確認;以預設值執行 ``config_sync_collect_blobs``)—— 在 Actions 選單。
同步在 worker 執行緒上執行;取消或關閉分頁都會釋放它。

輸入欄位有 server URL、使用者 id、共享密鑰、腳本資料夾、定位器儲存庫檔案與共享資產資料夾,另外還有:

* **要同步的區段** —— ``SYNCABLE_SECTIONS`` 的每個 section 一個核取方塊。全部勾選時分頁不傳
  ``sections``,套用上面的預設。取消勾選任何一個,就把勾選的那些當成 ``sections`` 傳入;
  勾選了但路徑是空的 section 會被略過而不是拒絕,若一個都不剩,分頁會說明並且不同步。
  狀態會列出上次同步涵蓋的 section。
* **把大型腳本存放在同步伺服器上** —— 傳 ``assets_server=True``,並把它取代的共享資產資料夾欄位反灰。

除了密鑰之外,其餘都會記在 GUI 設定檔裡(``WindowSettings.load_form`` / ``save_form``,
表單 ``config_sync``),下次開啟時還原。

資料夾鏡像與剪貼簿:不回送
--------------------------

``FolderSyncEngine.note_received(remote_name, sha256=...)`` 把監看資料夾中的檔案標記為
來自對端;在內容於本機變更之前,引擎不會把它推回去。``FolderSyncEngine.poll_once()``
可隨時執行一次差異比對。

接收端會替你呼叫它。``FileTransferReceiver``(WebRTC)與 ``FileReceiver``(TCP)把檔案先寫成
``.<name>.<id>.part``,在改名到定位之前呼叫 ``file_sync.note_incoming(final_path, part_path)``:
每個資料夾包含該檔案、而且還存在的引擎都會記下內容的 SHA-256。所以收進鏡像資料夾的檔案不會被送回去,
呼叫端不需要接線;沒有引擎鏡像那個資料夾時,檔案連 hash 都不會算。
``FolderSyncEngine.relative_name(path)`` 回報引擎是否涵蓋某個路徑(子資料夾需要 ``include_subdirs``)。

**什麼算是變更。** 引擎記下每個檔案的修改時間與大小,兩者任一和紀錄不同就推送 ——
不再只看時間是否 *較晚*,所以被換回較舊時間的檔案也會推送。光靠時間分不出同一個時間刻度內的兩次寫入
(剛把收到的檔案記下之後緊接著的本機編輯,以前不會被送出),所以在檔案自己最後一次寫入後
``RACY_WINDOW_S``\ (2 秒)內被記錄的檔案,還會以 SHA-256 記下內容,在這段時間過去之前以內容比對。
較舊的檔案不會為了判斷是否變更而被讀取。

**還在寫入的檔案。** 變更過的檔案要連續兩次輪詢看到相同的大小與修改時間才會推送,
所以大檔案的複製會晚一次輪詢整個送出,而不是現在就送出截斷的前半段(一直在變的檔案,例如
寫入中的 log,要等它停下來才會推送)。傳 ``wait_until_stable=False`` 可回到先前「一看到就推」的行為。
名稱以 ``.part``、``.partial``、``.tmp`` 或 ``.crdownload`` 結尾的檔案
(``IN_PROGRESS_SUFFIXES``;可用 ``ignore_suffixes=`` 覆寫)永遠不鏡像 —— 包含接收端自己的 part 檔,
它們以前會在傳輸進行中被推送。先用這類名稱寫、寫完再改名的程式,會被完整地撿起來。

``ClipboardEchoGuard``(``note_remote`` / ``note_sent`` / ``should_send`` / ``reset``)
為剪貼簿內容做同樣的事。``RemoteDesktopHost`` 為每個連線中的 viewer 各持有一個,
``RemoteDesktopViewer`` 為它的 host 持有一個(每次連線時重設);收到的 CLIPBOARD 訊息會在套用之前先記下。
``host.broadcast_clipboard_text(text, automatic=True)`` 與
``viewer.send_clipboard_text(text, automatic=True)``(以及 ``_image`` 版本)是給自動轉送剪貼簿
*變更* 的程式用的:剛從那個對端送達、或已經送給它的內容不會再送一次 —— 以 viewer 為單位,
所以某個 viewer 送來的內容仍會送到其他 viewer。不帶 ``automatic``(使用者按「送出剪貼簿」)時一律送出並記下。
``broadcast_clipboard_*`` 回傳送達的 viewer 數;``send_clipboard_*`` 現在回傳是否有送出。
GUI 只在按鈕按下時送剪貼簿,所以目前沒有任何地方傳 ``automatic=True``。
