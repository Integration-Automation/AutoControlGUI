跨機器設定同步
==============

``je_auto_control.utils.config_sync`` 讓同一位使用者的快捷鍵、觸發器、通訊錄與其他小型設定
在多台機器上保持一致。每位使用者在同步 server 上有一個 *bucket*；signaling server
(``python -m je_auto_control.utils.remote_desktop.signaling_server``,需要 ``[signaling]`` extra)
以 ``GET`` / ``PUT /config/{user_id}`` 提供它。

Server:持久化、檢查修訂版的 bucket
-----------------------------------

Bucket 由 ``je_auto_control.utils.config_sync.store.ConfigStore`` 存在一個 SQLite 檔案,
server 重啟後仍在。檔案位置依序取自 ``--config-db PATH``、環境變數
``AC_SIGNALING_CONFIG_DB``、預設的 ``~/.je_auto_control/config_sync.sqlite3``;
在第一個 ``/config`` 請求時才開啟,不是啟動時。內嵌 app 時傳
``create_app(config_store_path=...)``。

每個 bucket 有 server 指派的 **revision**(第一次寫入為 ``1``,之後每次 commit ``+1``)。
寫入必須指明它所依據的 revision,比較與寫入在同一個 SQLite transaction 內完成:

.. code-block:: python

    from je_auto_control.utils.config_sync.store import ConfigStore, RevisionConflictError

    store = ConfigStore("buckets.sqlite3")
    revision = store.commit("alice", bucket, base_revision=0, operation_id="op-1")   # -> 1
    store.commit("alice", bucket, base_revision=0, operation_id="op-1")              # -> 仍是 1
    store.commit("alice", other, base_revision=0, operation_id="op-2")               # RevisionConflictError

重複的 ``operation_id`` 會回傳第一次 commit 產生的 revision 且不寫入任何東西,
所以沒收到回覆的 client 直接重送同一個請求即可。每位使用者保留最近 256 個 operation id。

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
**version-2 client 面對舊 server** 會被明確告知:回覆沒有 revision,``push`` 丟出
``ConfigSyncError``(「predates revision-checked writes」)—— 請先升級 server。

Client
------

.. code-block:: python

    from je_auto_control.utils.config_sync import ConfigBucket, ConfigSyncClient, ConfigSyncConflict

    client = ConfigSyncClient("https://sync.example", user_id="alice", secret="...")
    merged, conflicts = client.sync(local_bucket)     # fetch、merge、在所 fetch 的版本上 push
    print(merged.revision)                            # server 提交的 revision

``sync`` 以 fetch 到的 revision 作為 ``base_revision`` push;若期間有另一台機器 push,
它會重新 fetch 與 merge,最多 ``max_attempts``(預設 4)次,之後丟出 ``ConfigSyncConflict``。
``push(bucket)`` 以 ``bucket.revision`` 為基準,回傳已提交的 revision;落後時丟出
``ConfigSyncConflict``(``.revision`` 為 server 目前的 revision)而不是覆寫。

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

    bucket.upsert("hotkeys", "hk1", {"combo": "ctrl+a"}, origin="laptop")   # versioned
    bucket.remove("hotkeys", "hk1", origin="laptop")                        # versioned tombstone
    bucket.values("hotkeys")        # 有效值;仍在衝突中的 entry 不列入
    bucket.conflicts()              # [(section, 帶 .siblings 的 SyncEntry), ...]

*不帶* ``origin`` 的 ``upsert`` / ``remove`` 仍寫入舊式、以 ``last_modified`` 蓋章的扁平 entry,
兩筆扁平 entry 仍以「較晚者勝」合併(回報於 ``ConflictRecord``);versioned entry 會取代
同 id 的扁平副本。因果衝突的 ``ConflictRecord.unresolved`` 為 true,此時沒有任何東西被丟棄。

刪除與退休裝置
--------------

刪除是一個 tombstone。Versioned tombstone **絕不因時間而丟棄**:``collect_tombstones``
只在 bucket 的 ``peers`` 記錄的每台有效裝置都已確認包含它的 revision 之後才移除。
``ConfigSyncClient.push_operations`` 負責維護這些確認。

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
