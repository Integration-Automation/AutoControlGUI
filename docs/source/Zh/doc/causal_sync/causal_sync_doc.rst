因果審閱與持久化本機 outbox
================================================================

實驗性基礎元件提供因果 entry 判斷、可序列化 peer ledger 與持久化本機重送佇列。
目前 HTTP client 仍使用既有時間戳合併；HTTP client／outbox 自動整合與本機
完整重同步協調仍保留在 C2。以下因果設定庫與獨立 HTTP 協定已驗證裝置確認及
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
sink 須處理至少一次投遞；本機元件不自動提供 HTTP／CAS 重建。
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
命令只保存資料，不執行腳本或啟用觸發器；outbox 自動投遞、有界 HTTP 重合併
與本機完整重同步套用仍是 C2 待辦。
