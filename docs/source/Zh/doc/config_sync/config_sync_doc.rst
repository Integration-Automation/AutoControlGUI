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
     - ``200`` 與 ``{"user_id", "sections", "revision": <已提交>, "version": 2}``,
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
