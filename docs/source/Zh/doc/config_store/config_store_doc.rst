持久化設定交易
==============

實驗性 ``ConfigStore`` 以 SQLite 保存帳號 bucket 與操作收據。
建立 store 或 signaling app 不會開啟資料庫；第一次操作才解析
``AUTOCONTROL_CONFIG_STORE`` 或 ``~/.autocontrol/config-sync.sqlite3``。
可傳入明確路徑隔離資料庫；每次操作均釋放連線。
比較基準版本、寫入資料與保存去重收據位於同一個 ``BEGIN IMMEDIATE`` 交易。

本機 API
--------

::

    from je_auto_control import ConfigBucket, ConfigStore

    bucket = ConfigBucket("alice")
    bucket.upsert("settings", "theme", {"value": "dark"})
    store = ConfigStore("config-sync.sqlite3")
    revision = store.commit("alice", bucket, base_revision=0, operation_id="edit-1")
    assert ConfigStore("config-sync.sqlite3").get("alice").revision == revision
    assert store.commit("alice", bucket, base_revision=0, operation_id="edit-1") == revision

輸入 bucket 不會被修改，讀取回傳獨立物件。
同一帳號的相同 operation ID／基準／內容重送，會回傳原提交版本，
即使資料庫已重啟或已有後續提交，也不會覆蓋較新資料。
ID 改配其他內容或基準，以及過期基準，均拋出 ``ConfigRevisionConflict``，
其 ``current_revision`` 提供目前版本。不同帳號可使用相同操作 ID。
預設最多 1,024 帳號；容量錯誤為 ``ConfigStoreFull``，儲存錯誤為 ``ConfigStoreError``，
輸入錯誤為 ``ConfigSyncError``。Bucket 必須是有限 JSON，最多 1 MiB。
識別碼為最多 128 字元的非空可列印文字且不含斜線；修訂版為 SQLite 非負整數。
操作收據持續保留，不以時間過期去重資料。

``python -m examples.config_store`` 只使用暫存檔案，不呼叫裝置或網路。

HTTP 與 client
--------------

既有可選 signaling 服務新增資料庫參數::

    python -m je_auto_control.utils.remote_desktop.signaling_server --config-store config-sync.sqlite3

沿用 ``--shared-secret``／``AC_SIGNALING_SECRET`` 與 ``X-Signaling-Secret`` 規則。
共用秘密授權服務存取；帳號名稱隔離儲存命名空間與 payload 身分，並非各帳號獨立登入。
未授權或格式錯誤的條件寫入不會開啟設定資料庫。
SDP session 仍只保存在目前行程，與持久化設定分開。

GET 使用 ``/config/{user_id}``，新版 client 的 PUT 使用
``/config/{user_id}/commit``；原有 PUT 路由也接受第二版封套。
專用提交路徑始終拒絕舊版 body，防止舊伺服器將不支援的新版封套誤存為 bucket。
第二版 body 恰有以下欄位::

    {"version": 2, "base_revision": 0, "operation_id": "edit-1",
     "bucket": {"user_id": "alice", "revision": 0, "sections": {}}}

成功回覆 ``{"ok": true, "version": 2, "revision": 1}``；
過期基準或 ID 對應其他內容回 HTTP 409，附目前版本。
GET 保持 bucket 形狀並回傳實際提交版本，另附協定版本與 CAS 模式 header。
既有 body 上限與秘密檢查仍在解析 JSON 前執行。

``ConfigSyncClient.push(bucket, base_revision=..., operation_id=...)`` 預設使用第二版，
回傳實際提交版本；未填基準時使用 bucket 的版本。
網路結果不確定時，須保留相同 ID、基準與內容重送；未填 ID 的每次 push 都建立新操作。
``sync`` 先抓取與合併，再以抓取版本提交；衝突向外傳遞，供明確重新抓取，
不降級成盲寫。沿用 redirect 防護與 HTTP egress 政策。

相容與操作入口
--------------

預設拒絕舊版盲寫（HTTP 428）。伺服器須明確設為
``allow_legacy_config_writes=True`` 或使用 ``--allow-legacy-config-writes``；
舊協定 client 使用 ``legacy_writes=True``。
相容文件保留不透明 JSON 欄位，但版本由伺服器決定；舊 client push 回傳 ``None``，
不宣稱 CAS 或重送去重。允許盲寫時 GET 的 CAS header 為 ``legacy-enabled``。
不支援的協定版本仍拒絕。

``AC_config_store_get``／``ac_config_store_get`` 讀取本機私有資料庫，
``AC_config_store_commit``／``ac_config_store_commit`` 以版本與操作 ID 提交。
兩者要求 DRIVE 權限並遵守路徑根目錄；Script Builder 的 Data 命令提供相同欄位與 JSON bucket。
讀取不存在的 store 可初始化 schema，因此是明確的私有操作。
只儲存資料，不執行同步腳本或啟用觸發器。
MCP 在儲存前檢查取消；交易完成後不再重標為取消。

獨立的 CausalConfigStore 與第三版 /causal 協定驗證 peer 確認、退休／完整同步 epoch，
並在回收刪除 payload 後保留永久因果憑證。升級帳號拒絕普通讀寫；既有本機設定庫
命令接受帶明確 _actor 的因果 JSON。參閱 :doc:`../causal_sync/causal_sync_doc`。
目前 HTTP client／merge helper 仍使用 last-modified 排序與限時 tombstone；
工作區 peer 控制／完整重同步協調與資產整合保留在 Progress.md；明確的 CausalSyncClient.flush 已提供持久化第三版投遞與有界重合併。
本機驗證使用隔離檔案與 loopback server，不增加遠端機器或真機驗收聲明。

持久化因果 peer 註冊／確認／回收／退休與原子本機完整重同步可透過
CausalSyncClient.control 與 AC_sync_peer_control（MCP／Builder）使用。固定操作 ID、
明確待送退役同意、SQLite schema 1→2 遷移與僅查本機的 status 請參閱因果指南。

明確的本機資產 manifest 與完整驗證版本可透過 build_asset_manifest、sync_assets 與
DirectoryAssetTransport（API／AC／MCP／Builder）使用。僅暫存原始檔，不啟用設定；
因果 adapter 整合仍屬 C3。大小／雜湊／路徑限制與發布語意請參閱因果指南。

七種因果來源 adapter 已保存可攜定義，並透過資產層發布完整且未啟用的原生 profile
（API／AC／MCP／Builder）。具名 local／vault 參照避免將選定的機器值與辨識到的
憑證放入可攜 entries。Apply 不改啟用中的來源，熱鍵／觸發器保持停用。私有 schema-1
描述、明確衝突解決與尚缺的工作區／GUI 偏好／資產／完整重同步整合請參閱因果指南。

原生數值定義先檢查支援範圍再作有限值轉換；超大 JSON 整數以 ConfigSyncError
拒絕，不會開啟 adapter 儲存。

私有絕對本機路徑綁定可包含高熵名稱；僅對這些私有路徑排除熵值啟發式判定，
仍拒絕可辨識憑證格式、敏感綁定名稱與已知解析後秘密。可攜資料與共用秘密掃描器
沿用原有政策。

WorkspaceSettingsSyncAdapter 提供獨立 workspace 種類，處理四項已保存的原生 GUI INI
偏好。既有私有 AC／MCP／Builder 命令發布未啟用的 workspace.ini；明確載入 GUI 時使用
獨立工作副本。Capture 不匯入 Qt，忽略私有／幾何位置資料，並與 GUI 共用預設正規化；
詳細語意見因果指南。
