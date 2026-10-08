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
不認得的 peer 會忽略。請讓每台機器都先用這個版本同步一次,再在任何一台上刪除 entry ——
tombstone 只會等已列在 ``peers`` 下的裝置。

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
     - ``TriggerEngine`` 的 image / window / pixel / file / cron 觸發器
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
  沒有任何 adapter 會啟動引擎或執行腳本。複合觸發器(all-of / any-of / sequence)不同步。

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
檢查失敗時不動既有檔案,並拒絕會離開資料夾的路徑。隨附的 transport 是
``DirectoryAssetTransport``;其他 blob 儲存請實作 ``fetch`` / ``store`` / ``has``。

一個呼叫,三個介面
------------------

``config_sync_run(server_url, user_id, **options)`` 執行整個循環 —— 把本機變更入列、
清空 outbox、合併、套用 —— 並回傳
``{state, revision, pending, conflicts, applied, withheld, assets, error}``,
``state`` 為 ``synced`` / ``pending`` / ``conflict`` / ``offline`` / ``cancelled`` /
``resync_required`` 之一。連不到 server 不是例外:變更留在佇列,狀態為 ``offline``。

選項:``device_id``(預設:在 ``~/.je_auto_control/config_sync_device_id`` 建立一次的 id)、
``secret``(預設 ``$AC_SIGNALING_SECRET``)、``sections``(預設 ``hotkeys``、``triggers``、
``address_book``;給了路徑時加入 ``scripts`` 與 ``locators``)、``scripts_dir``、
``locators_path``、``outbox_path``、``assets_dir``、``timeout_s``、``wait``、``max_attempts``。

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

四個都是 Script Builder **Data** 分類下的指令。

.. code-block:: json

    [["AC_config_sync_run", {"server_url": "https://sync.example", "user_id": "alice",
                             "secret": "${secrets.sync}", "scripts_dir": "scripts"}]]

GUI
---

**設定同步** 分頁(分類 *system*)顯示狀態、最後合併的 revision、待送變更數、
上次成功同步與最後的錯誤,並列出每個衝突及其候選。它的指令 —— *立即同步*、*取消同步*、
*重新整理同步狀態*、*保留所選候選*、*完整重新同步* —— 在 Actions 選單。
同步在 worker 執行緒上執行;取消或關閉分頁都會釋放它。

資料夾鏡像與剪貼簿:不回送
--------------------------

``FolderSyncEngine.note_received(remote_name, sha256=...)`` 把監看資料夾中的檔案標記為
來自對端;在內容於本機變更之前,引擎不會把它推回去。``FolderSyncEngine.poll_once()``
可隨時執行一次差異比對。``ClipboardEchoGuard``(``note_remote`` / ``should_send`` / ``reset``)
為自動轉送剪貼簿變更的程式做同樣的事:剛從對端送達、或已經送過的內容不會再送一次。
