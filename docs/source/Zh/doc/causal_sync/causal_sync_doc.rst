因果審閱與持久化本機 outbox
================================================================

實驗性基礎元件提供因果 entry 判斷、可序列化 peer ledger 與持久化本機重送佇列。
既有 ConfigSyncClient 仍使用時間戳合併；明確的 CausalSyncClient 已接上 outbox
HTTP 投遞、持久化 peer 控制與原子本機世代採用。以下因果設定庫與獨立 HTTP 協定已驗證裝置確認及
刪除回收；本機命令不連線伺服器，也不套用設定。

Entry 與明確衝突
----------------------------------------------------------------

::

    from je_auto_control import SyncEntry, merge_entries

    left = SyncEntry("settings", "theme", {"value": "dark"},
                     {"desktop": 1}, "edit-desktop", "desktop")
    right = SyncEntry("settings", "theme", {"value": "light"},
                      {"laptop": 1}, "edit-laptop", "laptop")
    decision = merge_entries(left, right)
    assert decision.conflict.local == left
    assert decision.conflict.remote == right
    resolved = left.evolve({"value": "chosen"}, origin="desktop",
                           operation_id="resolution", observed=(right,))
    assert merge_entries(right, resolved).entry == resolved

``MergeDecision`` 包含關係、選出的 entry 或 ``SyncConflict``。
只有向量能證明因果後繼時才選取；並行向量或同版本分叉會保留兩份資料。
相同 origin／operation 改配其他資料會拒絕，JSON 布林與數字也不混同。
value 可保留時間戳資料，但不以 wall clock 決定勝負。
不同 section／entry key 不可合併；``is_deleted=True`` 是版本化 tombstone，
並非刪除本機檔案或執行動作的指令。

Entry 複製有限 JSON 並封存因果證據，事後變更會在合併／序列化時拒絕。
向量最多 128 裝置，key 為最多 512 字元的非空可列印文字。
origin／operation ID 與正整數 counter 沿用設定契約。
``evolve`` 可明確觀察所有待選版本後建立可解決衝突的後繼。

Peer 確認與 epoch
----------------------------------------------------------------

``SyncPeers`` 管理 ``SyncPeer`` 的註冊、確認版本與明確退休。
退休、未知或 epoch 過期的裝置不可增量使用，會拋出 ``FullResyncRequired``。
``register(..., full_resync=True)`` 在完整快照後推進 epoch，不能退回已確認版本之前。
不依經過多久自動忘記離線 peer。

``can_collect(deletion_revision)`` 只判斷資格：已提交的正版本必須經所有有效 peer 確認，
沒有有效 peer 或版本為零均為 false，不會移除資料。
``to_dict/from_dict`` 保留 ledger 並拒絕重複 ID。``CausalConfigStore`` 依已提交 ledger
驗證這些轉換；單純轉換呼叫者提供的 peer-state 不會改變正式確認或裝置成員狀態。

持久化操作與重送
----------------------------------------------------------------

::

    from je_auto_control import SyncOperation, SyncOutbox

    operation = SyncOperation("delivery-1", "https://sync.example", "alice",
                              "desktop", (resolved,))
    queue = SyncOutbox("config-outbox.sqlite3")
    queue.enqueue(operation)
    print(queue.status(endpoint=operation.endpoint, user_id=operation.user_id))

``enqueue`` 回傳 ``None``；相同命名空間／ID／內容可重複呼叫，改配其他內容則拒絕。
帳號與 endpoint 分開隔離；HTTP URL 正規化並拒絕認證資訊、query 與 fragment。
命名空間建立時綁定 origin／epoch，既有 epoch 不符時需另外的完整重同步流程。
預設在第一次使用才解析 ``AUTOCONTROL_SYNC_OUTBOX`` 或
``~/.autocontrol/config-outbox.sqlite3``；SQLite 延後載入，每次操作均釋放連線，
不會在外來資料庫加入 outbox 表。

``prepare(operation, base_revision=..., bucket=...)`` 在傳送前保存獨立且固定的請求。
帳號須相符；只有明確收到過期基準拒絕後，才能呼叫
``reject_prepared(..., rejected_base=...)`` 清除待重建請求。
未知或內容已變的操作不能清除原請求，重啟後仍保留不確定結果的重送依據。

``flush(sender, endpoint=..., user_id=..., policy=..., cancelled=...)`` 呼叫使用者提供的同步 sink，
sink 接收相同操作／準備請求並回傳正修訂版；以 ``operation.delivery_id`` 作穩定收據身分。
sink 須處理至少一次投遞；通用本機 callback 不會自行重建 HTTP／CAS，
下方 ``CausalSyncClient.flush`` 提供專用第三版投遞。
成功提交後的取消不會把完成投遞改標失敗。
取消與硬中斷，包括明確包裝在 cause 中的訊號，會向外傳遞，不記成一般離線失敗。

``SyncRetryPolicy`` 限制每次 drain 每操作 1–10 次嘗試、最多 1–1000 個操作。
退避保存於資料庫並限制在 30 秒內，不靠 sleep 阻塞 worker。
有效 lease 在到期前排除其他嘗試；callback 可在到期後才完成，
過期擁有者不能發佈新擁有者的結果，sink 仍須提供傳輸 timeout 與冪等性。
失敗保留 pending／offline，衝突與需重同步狀態保持可見，不悄悄重試。
status 提供完整數量、確認投遞版本與最多十筆已清理錯誤預覽。

pending 檢視為追加順序的有界前段（1–1000 筆、序列化資料最多 16 MiB），總數仍完整。
每個邏輯操作的 entry 資料最多 1 MiB。
不序列化 client 認證或 HTTP header，已知解析後秘密值會拒絕；payload 應使用秘密參照。
來源 adapter 與協調說明見下方；資產整合仍列於 C3。

命令與 Builder
----------------------------------------------------------------

* ``AC_sync_entry_merge``／``ac_sync_entry_merge`` 審閱輸入的 entry JSON。
* ``AC_sync_peer_state``／``ac_sync_peer_state`` 只轉換輸入 ledger：register、acknowledge、
  retire、require_active、can_collect；回傳 JSON 不代表遠端 peer 已變更。
* ``AC_sync_outbox_enqueue``／``ac_sync_outbox_enqueue`` 保存本機待送操作。
* ``AC_sync_outbox_status``／``ac_sync_outbox_status`` 檢視總數及可選的有界操作快照。

純資料轉換允許 observe；私有 outbox 操作要求 DRIVE、遵守目前 MCP roots 並在開始前檢查取消。
查閱可初始化不存在的資料庫；Script Builder 的 Data 命令提供四個明確操作。
不執行同步腳本、不啟用觸發器，也不呼叫裝置或模型；既有 action-file CLI 可執行這些 AC 命令。

``python -m examples.causal_sync`` 只使用暫存檔案與受控 callback，展示衝突保留、明確解決、
peer epoch 及相同請求重送，HTTP／裝置呼叫為零；這不代表遠端收斂或真機驗收。

伺服器因果設定庫與第三版協定
----------------------------------------------------------------

``CausalConfigStore(path)`` 與 ``ConfigStore`` 共用延後開啟的 SQLite、帳號容量、
原子 CAS 與持久化歷史收據。``get(user_id)`` 回傳封存的 ``CausalBucket``；
未知帳號是 revision 為零的空快照。可辨識的舊 bucket 轉換時不會讓舊 tombstone
因時間到期而消失；不透明的根欄位要求明確遷移，避免無聲遺失。

編輯前先明確註冊完整快照::

    from je_auto_control import CausalConfigStore, SyncActor

    store = CausalConfigStore("config-sync.sqlite3")
    state = store.get("alice")
    peers = state.peers
    peer = peers.register("desktop", full_revision=state.revision)
    revision = store.commit(
        "alice", state.with_peers(peers), base_revision=state.revision,
        operation_id="register-desktop",
        actor=SyncActor("desktop", peer.epoch, "full_sync", revision=state.revision))

``SyncActor`` 模式為 edit、full_sync、ack、retire、collect。完整同步必須保留現有
全部資料並確認精確的 base 快照；既有裝置以新 epoch 明確重新加入。其餘操作必須
符合活躍裝置的 epoch。只有 actor 能提高自己的確認版本，且不可確認未來版本；
退休需指定單一目標。中繼資料操作不能編輯值，伺服器會核對整份 ledger 是否只包含
該次 actor 允許的轉換。

``with_entries`` 保存全部非支配替代值；``conflicts`` 包含所有衝突選項及最小刪除
憑證，``live_entries`` 排除有歧義與已刪除的鍵。新修改必須來自 actor origin、
增加自己的計數且不能捏造其他來源的觀察版本。交易禁止遺漏衝突選項、同一修改
更換 payload 或偽造伺服器指派的 change revision。

``collect()`` 只提出回收提案：未衝突的 tombstone 必須有正值的伺服器提交版本，
而且所有活躍裝置都已確認。以 ``SyncActor(origin, epoch, "collect")`` 提交時，
伺服器依已提交狀態重新驗證。永久 ``DeletionFence`` 保留鍵、版本向量、origin、
操作 ID 與刪除版本，但不保留舊值。重啟後舊快照仍被支配；並行修改會顯示衝突。
明確復原需觀察刪除版本下限與其他衝突。沒有時間到期或推測退休。

經驗證的 ``GET /config/{user_id}/causal`` 對新帳號也回傳 version 3 與 bucket。
``PUT`` 僅接受 version、base_revision、operation_id、bucket；提交 bucket 內需加
``_actor: actor.to_dict()``，驗證後不會把 actor 存成帳號資料。快照／刪除憑證的
schema 為第一版，既有 entry／outbox wire 格式保持相容。

回應包含 version 3、該次操作的收據 revision 與最新已提交 bucket。歷史相同請求
可能回傳較舊收據與較新 bucket。過期或重用請求回 409；失效裝置回 409，code 為
full_resync_required；格式錯誤回 400。共用秘密與讀取 body 前的大小限制仍生效；
帳號只是服務共用驗證之下的 namespace，並沒有新增每帳號登入。

升級後，舊 typed／HTTP 讀取與普通條件／盲寫都拒絕該帳號，避免丟棄因果資料；
已提交的歷史相同收據仍可在不修改內容的情況下回傳原版本。沒有自動降級。
獨立路由讓不支援的舊伺服器無法把因果資料當成不透明舊設定接受。

既有私有 ``AC_config_store_get``／``AC_config_store_commit`` 與對應 MCP／Builder
Data 命令以第三版讀寫因果快照；提交 bucket 必須含明確且暫存的 _actor。
路徑限制、DRIVE 與開始前取消仍生效。新建因果帳號需使用上例的 CausalBucket。
命令只保存資料，不執行腳本或啟用觸發器；下方明確 client 提供 HTTP 投遞與有界
重合併；以下持久化控制工作流負責原子本機世代採用。

明確的因果 HTTP 投遞
----------------------------------------------------------------

``CausalSyncClient(server_url, user_id=..., secret=None, timeout_s=5)`` 使用獨立第三版
路由及既有 HTTP egress／redirect 保護。這是明確選用的 API；ConfigSyncClient
保留既有時間戳合併。timeout 必須為有限正數且不超過 300 秒；不支援的舊路由或
錯誤協定資料會拒絕，不會退回舊版盲寫。

``fetch()`` 回傳完整 CausalBucket。``push(bucket, actor=..., operation_id=...,
base_revision=None)`` 提交精確請求並回傳 CausalReceipt，包含原收據版本與最新完整
快照。控制交易的結果不明時，需保留同一個 ID 與 body 重送；base 預設使用 bucket
版本，兩者必須一致。full_sync／ack／retire／collect actor 遵循前述伺服器規則。
原始 push 提交不採用本機 epoch；請使用以下持久化控制工作流。

明確註冊裝置後，先保存有版本的修改，再執行網路投遞::

    from je_auto_control import CausalSyncClient, SyncOperation, SyncOutbox

    client = CausalSyncClient("https://sync.example", user_id="alice")
    queue = SyncOutbox("config-outbox.sqlite3")
    # resolved.origin/epoch must match the stable registered queue identity.
    operation = SyncOperation("delivery-1", "https://sync.example", "alice",
                              resolved.origin, (resolved,))
    queue.enqueue(operation)
    report = client.flush(queue, max_rebases=3)
    confirmed = queue.snapshot(endpoint=operation.endpoint, user_id="alice")

``flush`` 優先重送已持久化的原 prepared 請求，之後才可重新抓取；已被接受但結果
不明的投遞，在重啟後仍保留原 ID／base。只有明確的 stale_revision 409 才清除該
準備版本，並在有界預算內重新抓取、合併及準備。操作 ID 衝突不重合併；未知／退休
epoch 維持 blocked。每次 attempt 允許 0–10 次 rebase，另外仍受既有 attempt／
batch／退避限制。耗盡預算會保留 offline 修改，供下次 drain 重試；並行值仍是衝突，
不會被選出或套用。取消在請求之間檢查；已收到成功交易會確認，不重標為取消。
包裝的取消／硬中斷仍傳播並保留工作。

CausalReceipt 要求快照每個修改都具有正值的提交版本；歷史重送的快照版本可高於
原操作收據。outbox 在同一個 SQLite 交易內，以目前 lease 擁有權確認成功、收據與
最新完整快照。快照寫入失敗會回滾成功標記；lease 已轉交後的舊擁有者不能發布，舊版本不能倒退
快取，相同版本的不同資料會拒絕。舊 int callback 仍相容，但不更新快照。
憑證 header 不序列化，回應中的已知解析憑證會在保存前拒絕。``snapshot`` 在首筆
因果投遞確認前回傳 None；它是伺服器快照，不會套用本機設定。

私有 ``AC_config_causal_fetch``、``AC_config_causal_commit``、``AC_sync_outbox_flush``
均有對應 MCP 與 Builder Data 命令。fetch／commit 接受 endpoint、user_id、選用的
options；commit 另需 bucket、actor、operation_id。flush 接受 path、endpoint、
user_id、選用的 options。options 支援 secret_env（即時環境變數名稱）與 timeout_s；
flush 另可設定 max_rebases，以及 policy 的 max_attempts、max_batch、backoff、
max_delay、lease_seconds；未知欄位會拒絕。憑證只在 client 執行時讀取，不回傳或排入
佇列。包含遠端讀取在內的全部命令要求 DRIVE；flush 遵守目前路徑根目錄與開始前
取消。既有 action-file CLI 可使用同一命令；只保存／投遞資料，不執行同步腳本、
啟用觸發器或套用設定。

持久化 peer 控制與本機完整重同步
----------------------------------------------------------------

``CausalSyncClient.control(queue, kind, peer_id=None, discard_pending=False,
policy=None, cancelled=None)`` 持久化處理 register、ack、collect、retire、full_resync。
只有 retire 接受目標 peer_id。應用程式明確決定何時確認、回收與退休，沒有定時工作。

::

    from je_auto_control import CausalSyncClient, SyncControlRequest, SyncOutbox

    queue = SyncOutbox("config-outbox.sqlite3")
    queue.identity("https://sync.example", "alice", origin="desktop")
    client = CausalSyncClient("https://sync.example", user_id="alice")
    client.control(queue, SyncControlRequest("register", operation_id="join-desktop"))
    client.flush(queue)  # 初次註冊保留原本待送編輯
    client.control(queue, "ack")
    client.control(queue, "collect")

可能在完成後或重啟後重試的 RPC 應使用固定 ``SyncControlRequest.operation_id``。
已完成的同 ID／同意圖重試直接回傳原始 revision，不發 HTTP，也不重播效果，即使其間
已有其他控制亦然。同 ID 改變意圖會失敗。沒有明確 ID 時，相同的未完成控制會續送，
已完成後再呼叫則是新的邏輯操作。

每個 endpoint／帳號最多一筆未完成控制。結果不明的固定請求優先於 GET 重送；只有明確
stale_revision 拒絕允許有界重合併，每次嘗試最多三次。衝突保持固定，世代失效保持
blocked，直到明確恢復。有效 lease 排除第二個傳送者；取消與硬中斷釋放自己的 lease，
不記成一般離線錯誤。已收到成功收據仍會確認。

若仍有待送舊編輯，full_resync 必須明確提供 ``discard_pending=True``。轉換期間拒絕
新編輯，同一 enqueue 的冪等重試仍可使用。只有確認收據後，才在同一交易更新身分、
權威快照與 revision、記錄控制收據，並將待送舊編輯標成 retired。原始 wire 封存保留，
不會在新 epoch 重播。本機交易失敗時保留全部舊狀態，重試相同固定請求。伺服器重設或
未知世代會使用新的穩定 origin，並可採用較低 root revision。此處僅採用同步狀態；
來源基準協調見下方；C3 的資產整合與同步 UI 仍待實作。

``queue.request_control(...)`` 只持久化意圖，不發 HTTP；``control_status`` 檢視狀態；
``control_receipt(endpoint, user_id, operation_id)`` 回傳已確認的原始 revision 或 None。
``client.flush`` 先投遞未完成控制，再傳增量編輯，其報告包含兩者；原始 queue status／
pending 計數只包含編輯。自有 outbox SQLite schema 1／2 驗證舊表格後原子遷移至 3；
編輯與控制 wire schema 維持 1。精簡控制歷史只保存邏輯意圖與 revision，不累積完整快照。

私有 ``AC_sync_peer_control``／``ac_sync_peer_control`` 與 Builder Data 表單接受 path、
endpoint、user_id、operation（預設 status）及 options。選項有 operation_id、peer_id、
discard_pending、secret_env、timeout_s、policy。所有模式都要求 DRIVE 及目前路徑 roots。
status 僅查本機，不發 HTTP，也不解析 secret_env；即時憑證不持久化。
``python -m examples.causal_peer_control`` 使用暫存檔與 loopback HTTP 示範註冊、刪除回收、
退休、明確完整重同步及歷史收據重試，不呼叫裝置或外部 API。

經驗證的本機資產版本
----------------------------------------------------------------

``AssetFile(path, sha256, size)`` 描述可攜相對名稱、小寫 SHA-256 與精確位元組數。
``AssetManifest(files)`` 對不可變 tuple 排序，以正規化第一版 JSON 計算 digest。
未知欄位、不安全名稱、大小寫／Unicode 別名與檔案／目錄衝突都在儲存前拒絕。
同一父目錄在所有項目中的拼寫必須一致。
每版最多 1024 個資產、每檔 64 MiB、整版合計 256 MiB。

::

    from je_auto_control import DirectoryAssetTransport, build_asset_manifest, sync_assets

    manifest = build_asset_manifest("selected-assets", ["script.json", "templates/button.png"])
    transport = DirectoryAssetTransport("selected-assets", "local-asset-cache")
    result = sync_assets(manifest, transport)
    # result.directory 內含完整且經驗證的兩個檔案，不執行或啟用任何內容。

manifest 只包含相對名稱、雜湊與大小；機器根路徑保留在即時 transport。
這是明確選擇、不解讀內容的原始檔案複製，保留原始位元組。下方來源 adapters 將明確選定的秘密與機器路徑換成
參照；資產／因果工作區協調仍屬 C3；這裡不自動蒐集工作區檔案或上傳。

``build_asset_manifest(source_root, paths, cancelled=None)`` 讀取單一 root 內明確選定
的一般檔案。``DirectoryAssetTransport`` 延遲使用檔案且不連網。``AssetTransport``
protocol 提供 target_root 與可作 context manager 的二進位 ``open(asset)``；自訂
transport 自行設定 I/O timeout。工作前與每次有界 64 KiB 讀取之間檢查取消；明確包裝的
硬中斷／取消訊號保持傳遞。發布成功後才發生取消時，保留成功結果。

``sync_assets(manifest, transport, cancelled=None)`` 先暫存全部資產，逐一驗證精確大小
與 SHA-256，再以一次 rename 發布整份版本目錄。樣板在最後失敗時，不會發布只含腳本的
不完整版本。發布前會 flush 暫存檔。這是完整的不可變版本，不直接替換啟用中的工作區
檔案。AssetSyncResult 含 directory、manifest_digest、reused、file_count、byte_count。
重複／並行投遞只重用完整重驗成功的版本。缺檔、修改、未列入 manifest 的快取內容與
符號連結均拒絕使用，受損證據保留。失敗／取消時清除自己的暫存目錄，保留既有版本。
不修改目前工作區指標，也不執行腳本或啟用觸發器。

私有 ``AC_sync_asset_manifest``／``ac_sync_asset_manifest`` 接受 source_root 與 paths
JSON 陣列，回傳 manifest／digest。``AC_sync_assets``／``ac_sync_assets`` 接受 manifest、
source_root、target_root，回傳 JSON 結果。Builder Data 表單保留完全相同欄位。兩個命令
即使僅讀本機都要求 DRIVE，交集套用預設及目前 MCP roots，傳輸期間持續檢查即時 roots
與取消。``python -m examples.sync_assets`` 僅使用本機暫存檔，不呼叫網路、裝置或 API。

持久化來源 adapters 與未啟用的原生 profile
----------------------------------------------------------------

``ScriptSyncAdapter``、``LocatorSyncAdapter``、``HotkeySyncAdapter``、
``TriggerSyncAdapter``、``AddressBookSyncAdapter``、``SettingsSyncAdapter`` 與 ``WorkspaceSettingsSyncAdapter``
讀取明確選定的真實來源，不啟動 backend 或 callback。腳本以單一 root 內的相對檔名選取；
設定來源是 JSON 物件，GUI QSettings 偏好設定使用下方獨立的 workspace adapter。Locator 保留 name/role/app_name；
熱鍵／觸發器只取定義，不取執行中的 enabled/fired。通訊錄排除 last-used 與本機連線／喚醒欄位。

::

    from je_auto_control import ScriptSyncAdapter, SyncAdapterState, SyncLocalIdentity

    identity = SyncLocalIdentity("https://sync.example", "alice", "desktop", 0, 0)
    state = SyncAdapterState("adapter-state.sqlite3", identity)
    adapter = ScriptSyncAdapter("selected-scripts", state, paths=["login.json"])
    entries = adapter.snapshot()  # change_id -> SyncEntry，保留每個並行版本

建構狀態不開啟資料庫；預設路徑依 ``AUTOCONTROL_SYNC_ADAPTER_STATE`` 或
``~/.autocontrol/sync-adapters.sqlite3``。自有 SQLite schema 2 依 endpoint／帳號／
origin／epoch／profile／種類隔離資料。只有可攜來源指紋變動才新增操作。
``apply(entries)`` 先驗證整批，再以單一交易保存 heads／操作收據／來源基準，回傳
stored／unchanged／conflicts／unresolved。接收資料不替換啟用中的來源、不註冊熱鍵或啟動
觸發器。尚未啟用接收版本時，舊本機來源的編輯仍與外來版本並行；重送舊操作不復活刪除，
同一操作 ID 不得換內容。

``resolve(entry_id, value, observed=head_ids, is_deleted=False)`` 要求完全相同的已檢閱
change-ID 集合，且先捕捉目前來源變更；過期檢閱會失敗。選擇刪除時使用空 value 與
``is_deleted=True``。衝突、缺少參照與原生本機值型別錯誤都保留待檢閱；``definitions()``
與完整發布會拒絕，而非靜默省略。``materialize_sync_profile(adapters, target_root)``
接受 1–7 個不同種類，透過已驗證的資產層一次發布原生檔與 ``profile/<kind>.json``
版本中繼資料。熱鍵／觸發器的 enabled 遞迴設為 false；不改工作區指標或來源，不執行腳本。

具名參照
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

``SyncReference("secret", "LOGIN")`` 與 ``SyncReference("local", "downloads")``
採用 ``{"$autocontrol_ref": {"kind": "local", "name": "downloads"}}`` 格式。
``SyncBindings(fields={entry_id: {json_pointer: reference}}, local_values={...})``
在保存前替換明確欄位；JSON pointer 對準可攜 record，例如腳本的 ``/actions/0/1/password``。
既有 ``${secrets.LOGIN}`` 自動轉為 secret 參照；與不歧義本機字串值完全相同的欄位也可自動
轉換。Local 值僅接受有限、不可變的 JSON scalar；不接受 vault 原值，也不讀取 vault。
Secret 名稱遵循 vault placeholder 語法。腳本／JSON 設定在發布時保留 secret placeholder；
locator／熱鍵／觸發器／通訊錄原生欄位僅允許 local 參照，workspace 偏好僅接受原始值。
缺少本機名稱或型別不合會阻止完整發布。辨識到的憑證欄位、
私有秘密命令參數、絕對機器路徑與裝置／螢幕選取值要求參照。此檢查無法推斷任意語意秘密；
呼叫端仍須選擇可攜資料，並明確綁定敏感欄位。

私有命令描述
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

四個 Data 命令及對應 MCP 工具均要求 DRIVE，交集套用預設與目前 MCP roots：
``AC_sync_adapter_snapshot(profile)``、``AC_sync_adapter_apply(profile, entries)``、
``AC_sync_adapter_resolve(profile, entry_id, value, observed, is_deleted=False)``、
``AC_sync_profile_materialize(profiles, target_root)``。Snapshot 回傳 kind／entries，
entries 以 change-ID 對應版本 wire 物件；apply 回傳 ApplyReport 欄位，resolve 回傳單筆 wire。
Profiles 為 1–7 筆私有描述陣列。Builder 保留全部 JSON；直到最後發布仍檢查來源／狀態的
即時路徑權限與取消。未完成 merge 會整批回滾；明確包裝的硬中斷／取消訊號保持傳遞。

::

    {
      "schema_version": 1,
      "kind": "scripts",
      "state_path": "adapter-state.sqlite3",
      "identity": {"endpoint": "https://sync.example", "user_id": "alice",
                   "origin": "desktop", "epoch": 0, "confirmed_revision": 0},
      "profile_id": "main",
      "source": {"path": "selected-scripts", "paths": ["login.json"]},
      "bindings": {"fields": {}, "local_values": {}}
    }

``adapter_from_profile`` 依此私有 schema 1 延遲建構。Kind 支援 scripts／locators／
hotkeys／triggers／address_book／settings／workspace。Source 擇一使用明確 path（僅 scripts 接受 paths）
或 inline records 物件。檔案來源使用各領域原生 JSON：locator 物件、通訊錄 entries 陣列、
schema-1 熱鍵／觸發器陣列或一般設定物件。描述內含本機路徑與綁定值，必須保持私有；
只有可攜 entries 才放上 wire。``python -m examples.sync_adapters`` 使用六種真實來源產生
十二個暫存原生／中繼檔，不執行腳本、不註冊接收熱鍵／觸發器、不讀 vault、不連網。
來源／outbox 與完整重同步基準協調見下方。GUI 即時偏好套用、資產參照／傳輸、明確原生載入、
Sync UI 與 folder／clipboard／斷線回歸仍列於 Progress.md 的 C3。

日誌沿用既有的保守秘密欄位政策：內嵌定義只要包含 password 欄位，即使值為參照也會遮罩，
候選產生器因此排除該動作，不重建不完整的 apply／resolve。私有參照描述與發布命令仍可
保留重現；不以可用憑證代替已遮罩值。

原生數值定義先檢查支援範圍再作有限值轉換；超大 JSON 整數以 ConfigSyncError
拒絕，不會開啟 adapter 儲存。

私有絕對本機路徑綁定可包含高熵名稱；僅對這些私有路徑排除熵值啟發式判定，
仍拒絕可辨識憑證格式、敏感綁定名稱與已知解析後秘密。可攜資料與共用秘密掃描器
沿用原有政策。

已保存的原生 GUI 工作區偏好
----------------------------------------------------------------

``WorkspaceSettingsSyncAdapter(source_path, state)`` 讀取已保存的原生 GUI INI，
通常位於 ``~/.je_auto_control/gui.ini``。因果種類為 ``workspace``；四個獨立 key 是
theme／font_pt／navigation_visible／navigation_width，各以 ``{"value": ...}`` 包裝。
不選取其他區段、秘密、幾何位置或裝置狀態。來源檔案不存在時沒有本機編輯；刪除已存偏好
會產生因果 tombstone。來源的安全預設正規化與 GUI 共用。
接收值要求 theme 為 dark/light、font_pt 為 0/10/12/14/16/20、navigation_visible 為
JSON boolean、navigation_width 為 200–1200 的整數；不接受參照或未知 key。
來源為至多一 MiB 的 UTF-8 INI；損壞輸入與歧義的原生別名在開啟 adapter 儲存前失敗。
區段／key 大小寫遵循本機 QSettings 規則，不啟用 Python DEFAULT 繼承。
參閱 `Qt key 語法文件 <https://doc.qt.io/qt-6/qsettings.html#section-and-key-syntax>`_。

::

    from je_auto_control import WorkspaceSettingsSyncAdapter

    adapter = WorkspaceSettingsSyncAdapter("saved-gui.ini", state)
    entries = adapter.snapshot()
    # 明確設定的接收端將這些版本套用至未啟用的 profile。

既有 snapshot／apply／resolve／materialize 命令的私有描述可使用 ``kind: "workspace"``，
搭配 ``source: {"path": "saved-gui.ini"}`` 或明確 inline records。四個偏好各自保留衝突，
解決時須提供完全相同的已檢閱版本集合。最多七種資料可一起發布，完整版本包含
``workspace.ini`` 與 ``profile/workspace.json``。INI 中缺少／刪除的偏好採安全原生預設，
不改來源或目前 GUI。

明確交給新 GUI 載入前，先將產生的 workspace.ini 複製為獨立且可寫的工作檔，再以
``QSettings(working_file, QSettings.Format.IniFormat)`` 傳給
``AutoControlGUIUI(settings=...)``。不要讓 GUI 直接寫入不可變快取；GUI 關閉時會保存
偏好。Capture 讀已保存值，接收版本不會重載執行中的視窗。專用 Sync UI 與即時偏好套用
仍屬 C3 待辦。``python -m examples.sync_workspace`` 示範捕捉、未啟用發布與明確工作副本，
不匯入 Qt、不呼叫網路／裝置／API，也不修改既有工作區。


來源工作區協調
----------------------------------------------------------------

``SyncWorkspace(configuration, path_policy=None, cancelled=None)`` 延遲選取 1-7 種
不同來源。建構只驗證即時路徑權限，不開來源檔案、憑證或 SQLite。私有設定使用 schema 1::

    {
      "schema_version": 1,
      "endpoint": "https://sync.example",
      "user_id": "alice",
      "outbox_path": "workspace-outbox.sqlite3",
      "profiles": [{"kind": "workspace", "state_path": "adapter-state.sqlite3",
                    "source": {"path": "saved-gui.ini"}}]
    }

Profiles 沿用上述 source／profile_id／bindings 規則，不另帶 identity／schema_version。
Outbox 提供 origin／epoch；每個 kind 固定綁定 state_path／profile_id，不同 kind 可共用
adapter 資料庫。來源檔、adapter 狀態與 outbox 角色不可重疊。私有綁定與設定不傳上 wire。

``capture()`` 不連網、不讀憑證，將可攜 heads 冪等排入持久佇列。每批最多 10,000 筆／
16 MiB，整批成功或回滾。重啟先匯入待送 frontier，再觀察來源，保留 actor counter。
``synchronize(options=...)`` 捕捉離線編輯、必要時註冊、在 GET 前優先重送結果不明的固定
請求、投遞編輯並協調已驗證快照。全部七種領域與永久刪除憑證都在 cache／prepare／確認
之前驗證。非法快照拋固定代碼的 SyncWorkspaceError；傳輸失敗保留待送工作。
既有通用 CausalSyncClient 保留可選驗證，不改既有使用者的資料模型。

WorkspaceSyncResult 包含 captured／delivered／pending／revision／conflicts／unresolved／state。
Delivered 只計定義編輯；pending 包含編輯與控制。``status()`` 只讀本機中繼資料，
不讀來源／憑證、不連網。短期 workspace lease 排除其他變更協調器；每次 RPC 前重查
權限、取消及即時憑證參照。網路操作在來源捕捉前就記住宣告的秘密遮罩，短憑證也不可進入
定義；純本機 capture 不查憑證。原生 INI 解析錯誤不保留可能含私有內容的來源行。

``review(kind)`` 不觀察來源，只傳回既有 heads。``resolve(kind, entry_id, value,
observed=change_ids, is_deleted=False)`` 依精確檢視集合建立並排入明確選擇。
``materialize(target_root)`` 發布完整驗證且未啟用的版本；未完成重設、退休 peer、衝突
或未解析參照都拒絕發布。不執行腳本、不啟用熱鍵／觸發器、不改目前偏好。

``control(SyncControlRequest(...), options=...)`` 明確註冊、確認、回收、退休或完整重同步。
來源指紋與持久 reset 意圖在同一 outbox 交易提交；只在成功收據確認後採用身分／cache 並
退休舊待送編輯。每個新 adapter 世代只採用一次權威 frontier 與預先來源基準，未改動的
舊檔不會重播退休編輯；結果不明期間的新來源變更仍會在之後捕捉。相同控制 ID 重送只回
原始收據，不退休後來工作。舊版／外部 reset 或缺少相符基準的新來源選取以 missing_baseline
拒絕，需建立新的協調完整重同步；已採用世代可在之後改選來源。
自有 outbox schema 1／2 遷移至 3，adapter schema 1 遷移至 2，保留 heads、來源指紋、
編輯 wire 與精簡控制收據；wire schemas 維持 1。

私有 ``AC_sync_workspace``／``ac_sync_workspace``／Builder Data 接受 configuration、
operation（預設 status）與可選 options；所有模式都需要 DRIVE／目前 roots。
status／capture 不接受 options；review 使用 kind；resolve 使用 kind／entry_id／value／
observed／is_deleted；materialize 使用 target_root。網路操作 sync 與 register／ack／collect／
retire／full_resync 接受 secret_env／timeout_s／policy／max_rebases；控制另依規則接受
operation_id／peer_id／discard_pending。
``python -m examples.sync_workspace_http`` 以兩組真實暫存來源與 loopback HTTP 示範離線並行、
精確解決、重啟、未啟用發布與退休編輯不重播。資產參照／傳輸、GUI 即時套用、明確原生載入、
Sync UI 與 folder／clipboard／斷線回歸仍在 Progress.md；不代表真機或付費 API 驗收。
