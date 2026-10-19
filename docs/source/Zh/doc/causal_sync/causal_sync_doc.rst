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
設定／資產 adapter 仍列於 C3。

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
C3 的設定／資產 adapter 與同步 UI 仍待實作。

``queue.request_control(...)`` 只持久化意圖，不發 HTTP；``control_status`` 檢視狀態；
``control_receipt(endpoint, user_id, operation_id)`` 回傳已確認的原始 revision 或 None。
``client.flush`` 先投遞未完成控制，再傳增量編輯，其報告包含兩者；原始 queue status／
pending 計數只包含編輯。自有 outbox SQLite schema 1 驗證舊表格後原子遷移至 2；
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
這是明確選擇、不解讀內容的原始檔案複製，保留原始位元組。將本機秘密與機器路徑換成
參照的設定 adapters，以及因果設定同步整合仍屬 C3；這裡不自動蒐集工作區檔案或上傳。

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
