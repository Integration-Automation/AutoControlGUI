受管 DAG 批次與明確續接
================================

初次執行前註冊
--------------------------------

``manage_agent_dag("register", {"definition": graph, "max_parallel": 4})`` 保存 owner 範圍內的
完整受管圖，不提交任務、不取得目標。圖須有 1..100 個封閉 task 節點、每主機不同 request key 及
有效拓樸；拒絕普通 action／action_file、未知欄位、循環、重複相依及自填批次標記。本機規格綁定
目前 profile／origin 上限，遠端路徑不在本機 canonicalize；私下固定主機設定，不在批次保存原憑證。

取得 ``batch_id`` 後，明確 ``run_dag(graph, max_parallel=4, batch_id=batch["batch_id"])``。
圖、並行數及主機設定須一致，不能提供自訂 runner。目的端 ``options.dag_batch`` 包含批次／圖摘要／
節點 ID；key 由批次、節點、主機及原 key 衍生，不會採認剛好使用原 key 的其他任務。原圖保持不變。

派送見證與獨立完成
--------------------------------

``begin`` 只能由 registered 進入 running 一次，回傳私有 attempt；``claim`` 在可能派送前提交，
且相依節點須已確認。``record`` 只收有限協調身分，向目的端重新核對精確規格／key／任務、
spec-match 契約 1、成功狀態、完整獨立完成條件及輸入釋放；缺一不能確認節點，也不揭露遠端診斷。
``finish`` 依持久節點階段計算 succeeded／waiting_review。

中斷或提交回覆遺失保留 claimed／unknown，重啟、第二次 begin 或稍後查無紀錄都不能重設。
runtime 重啟先使舊 attempt 失效，批次改為 waiting_review；單一任務成功不批准新批次 attempt。原 owner 與 caller 權限持續更新；遠端不接收本機 principal／
origin witness，目的端連線只使用相符的已審閱主機設定。不重建登入／視窗，也不解除原生輸入隔離。

共用介面與尚缺步驟
--------------------------------

介面為 ``manage_agent_dag``、``AC_agent_dag``、MCP ``ac_agent_dag``、``POST /agent/dag``、
Builder 與 ``agent-task dag register|get|list|begin|claim|record|finish|inspect request.json``。
register 可帶 1..64 的 max_parallel；執行請求帶 batch_id／attempt，節點操作加 node_id，record
另帶 ``receipt={outcome, task_id}``。一般 caller 使用 run_dag 驅動這些階段。get 回傳原圖及節點
階段／收據，list 最多 200 個可見批次；inspect 只查看已綁定圖，``resume_permitted=false``。

``run_dag``、``AC_run_dag``、MCP ``ac_run_dag`` 新增選填 batch_id，未填時保留既有行為。
DAG Actions 新增「註冊受管批次（不執行）」與「讀取受管批次紀錄」及批次 ID 欄位；註冊不自動
執行，仍須另用 Run。圖／批次選取變更時丟棄晚到回覆；停止／關閉現有 DAG worker 保留耐久紀錄，
目的端任務仍依既有服務生命週期及暫停／審閱契約處理。

整圖明確續接
--------------------------------

中斷後用原圖與批次 ID 取得唯讀審閱，再明確核准／啟動::

    review = manage_agent_dag("review_continuation", {"batch_id": identifier, "definition": graph})
    request = {"batch_id": identifier, "definition": graph, "snapshot": review["snapshot"],
               "decisions": review["decisions"], "note": "已核對所有節點證據與權限"}
    result = run_dag(graph, max_parallel=4, batch_id=identifier, recovery=request)

review 只接受 waiting_review。要先使執行中／已批准的協調 attempt 失效，可明確呼叫
``pause_batch``，提供 batch_id；這只停止新的協調派送，不會暫停已接受任務，也不證明輸入清理。
目的端任務仍須依各自 pause／cancel／review 生命週期處理，不能以此作為原生輸入移交訊號。

每個節點都須恰有一個封閉決策。``adopt`` 帶 node_id／action／task_id，只採認綁定原任務的獨立
完成證據；``successor`` 欄位相同，須沿真實 TaskRecovery 來源鏈連回原任務，先另行建立、審閱並
獨立完成該新任務。不相關的成功任務或自填 options 不能建立來源鏈。``dispatch`` 帶
node_id／action／spec，只准從未 claim 且目的端未接受請求的 pending 節點；``wait`` 只帶
node_id／action，阻止整圖批准。協調 claim 前出現在目的端的任務不構成批次來源證據；查無紀錄
不能清除既有 claim 或授權重播。

修改決策後，帶完整 decisions 再做 review_continuation，只有 can_approve=true 才用其新 snapshot
與 decisions 批准。本機派送可替換過期 origin 並保持／縮小原根目錄；完整動作、目標、設定與完成
條件保持固定。遠端規格不變，由目的端決定權限。submission_contract=1 的歷史摘要證明已接受
規格身分，不授予現在的輸入權限。舊任務沒有見證時仍須通過目前 spec-match 契約 1；request-key
重試不會補造見證。缺原始輸入見證的舊批次須明確使用 get.input_definition。

``approve_continuation`` 帶 batch_id／definition／snapshot／decisions／非空有限 note，選填
timeout_seconds 預設 30、最多 300；重新核對證據並在交易內保存真正審閱者、決策、採認與縮限綁定，
不派送。相同重試回傳同一批准，包含 used／cancelled 狀態。``start_continuation`` 帶
batch_id／definition／approval_id／不變的 max_parallel，重新驗證後只消耗一次批准。圖、審閱者、
權限、主機設定或證據變更須重新審閱。run_dag／AC_run_dag／ac_run_dag 選填 recovery 驅動此流程，
仍拒絕自訂 runner。``validate_node`` 帶 batch_id／attempt／node_id；執行時在採認節點及放行
其相依節點前重驗完成證據，證據消失就轉回 unknown。

所有操作共用 manage_agent_dag／AC_agent_dag／ac_agent_dag／POST /agent/dag／Builder 與
``agent-task dag OPERATION request.json``。get 提供有限續接稽核，包含使用者、note、決策與批准
狀態，不揭露私有 owner 路徑或憑證。DAG Actions 新增停止新派送、審閱與明確續接，以及可編輯請求
JSON；核對後填 note，圖／批次選取變更會使舊審閱失效。唯讀 inspect／review 維持
resume_permitted=false，只有明確 approve／start 授權新 attempt。

服務背景協調
--------------------------------

明確啟動 AgentRuntimeService 後，可將協調交給服務，讓 caller／視圖關閉後仍繼續::

    accepted = manage_agent_dag("run_background", {
        "batch_id": identifier, "definition": graph, "max_parallel": 4})
    record = manage_agent_dag("get", {"batch_id": identifier})

停止的批次先整圖審閱並明確批准，再將這一次已批准 attempt 交給服務::

    approved = manage_agent_dag("approve_continuation", request)
    accepted = manage_agent_dag("run_background", {
        "batch_id": identifier, "definition": graph, "max_parallel": 4,
        "approval_id": approved["approval_id"]})

共用 AC／MCP／REST／CLI／Builder。未帶 approval_id 使用初次 begin；帶值則消耗 start_continuation。
選填 timeout_seconds 只用於續接證據檢查。圖、並行數、真正提交者、原 owner、主機綁定規則不變；
重複初次啟動或已消耗批准均拒絕，接受回覆遺失須讀取紀錄，不得重播。匯入、註冊或讀取不會啟動
服務。服務未就緒／已滿時不消耗 attempt；取得 attempt 後若佇列接受失敗，則使其失效。

服務沿用 WorkQueue，以四個協調 worker、最多 64 個待處理／執行中派送限制工作量。每個節點仍須
先 claim，再取得目的端獨立完成證據。派送及輪詢持續更新原 owner 與真正提交者權限。本機目的端
直接綁定所屬 runtime、保留原任務 owner，不讀取可能指向其他服務的全域連線檔；遠端沿用固定端點，
不接收本機 principal／origin witness。本機實際執行及原生輸入釋放仍由服務的任務 worker 負責。

get／list 新增 background：caller 協調時為 null，背景則只提供 new／in_progress／success／failed
等有限狀態，失敗須審閱；不能替代持久批次／節點證據或證明原生清理，不揭露私有派送權限與 attempt。
DAG Actions 新增「交由服務背景執行批次」及「核准並交由服務背景續接」，明確提交後即回傳批次紀錄。
關閉視圖不停止服務已接受的工作，之後重新讀取批次紀錄查看進度。

任務停止請求與後續狀態轉換使用資料庫條件更新，保留同時完成的終態與完成證據。
服務關閉先使協調 attempt 失效，再回收協調與本機任務 worker；stop_all 也先停止可見 running／
approved 批次的後續派送，再取消可見本機任務，operator 不能停止其他 owner 批次。此處只停止未來
claim；目的端已接受／傳輸中的操作仍依 pause、清理及未知副作用契約處理，不推論遠端已清理。
真實程序退出仍保留耐久 claim；重啟將 live 批次轉為 waiting_review、舊排隊／執行中派送轉失敗，
不重新 claim 或重播。即使舊派送尚無節點 claim，也須明確審閱；查無目的端任務仍不能重設未知 claim。

caller 來源服務綁定
--------------------------------

``run_dag(..., batch_id=...)`` 在 begin 或續接批准前固定來源。AgentRuntimeClient.bound() 保存
連線檔絕對路徑及 URL／token／服務世代摘要，每次請求仍重新讀取憑證，不快取 bearer。受管批次
必須有有效世代；一般 client 保留動態連線行為，仍可使用沒有世代的舊資料。本機節點的 submit／
get／pause 經執行 context 共用來源 client，全域預設探索變更不會把後續本機節點送往另一服務。
來源 URL、token 或世代被替換時，在傳輸前停止後續呼叫，不會靜默替執行中 attempt 重新綁定。

服務端批次檢視與完成驗證直接讀取所屬 runtime；保留目前原 owner 的 request-key 範圍，同時在查詢
前後更新真正 caller 的權限。因此管理員檢視仍使用原 owner 的 key。遠端維持目的端憑證，不接收
本機 principal／origin。Python／AC／MCP／Builder 及 GUI Run 共用此行為，不需另填憑證或新增命令。

偵測替換不代表先前已接受工作完成清理，原 claim 持續保留，亦不把 pause／控制請求轉送替代服務。
須透過另行確認的原服務連線檢視，並使用明確批次／任務審閱；還原檔案不重設 begin、未知 claim
或已消耗批准。

原 owner 本機接收
--------------------------------

caller 與服務協調都在耐久 node claim 後使用 ``local_task``，請求只含
``{batch_id, attempt, node_id, operation, body}``，一般使用者仍由 run_dag 驅動生命週期。
operation 限 submit／get／lookup／pause，節點須為 local；submit／get／lookup 要有有效 attempt
與未決 claimed 節點。submit 只收 ``{spec, idempotency_key}``，須與已綁定完整契約相符，以原
owner 建立任務／key，另記真正 caller。自填 actor、變更規格／key、其他節點或任意方法均在輸入前拒絕。

任務、request key、submission witness 及可信本機接收在同一交易提交，固定 task／batch／node／
attempt／actor／提交摘要。相同重試回傳同一任務；舊 key 沒有相同可信綁定就拒絕，不補造見證，
options 或自填快照不構成證明。提交失敗不啟動 worker。get／pause 只接受已接收的 task ID；lookup
限綁定 key 與選填精確規格。attempt 被封鎖或原 owner 失去輸入權限後，仍可精確清理已接收任務，
不授權新派送或其他任務控制，caller 權限仍須通過。遠端沿用目的端身份，不接收本機 actor。

runtime 在 scope 進入、checkpoint、實際派送前、巢狀命令 guard 與維護重新核對雙方權限；actor
仍須能管理原 owner 的工作，管理員降為 operator 後不能繼續其他人的任務。attempt 失效或 claim
未知時阻止後續輸入，排隊任務也在啟動前重驗。原生清理失敗沿用隔離，接收／pause 回覆不取代
輸入釋放證明。任務 metadata 新增有限 local_dag_admission（contract／batch／node／actor UID），
不揭露 attempt capability 或私有使用者資料庫路徑，既有任務 JSON 檢視可直接顯示。

保留與清理
--------------------------------

沿用 ``prune_agent_tasks(keep_days=30)`` 與服務每小時維護，API／AC／MCP／REST／CLI／Builder／GUI
共用政策。回覆保留 deleted／keep_days，新增 deleted_batches／deleted_dag_deliveries；每次最多
考慮 1,000 個過期 registered／succeeded 批次、回收 1,000 筆過期且已結束的孤立 DAG 派送，
逐任務維持原本 1,000 筆上限。只回收 owner／admin 可管理的批次；沒有原批次的派送限主機管理者清理。

未使用註冊須所有節點 pending 且沒有關聯接收任務；成功批次須所有節點 confirmed、關聯任務及復原
後繼任務已終止，沒有執行中的派送、記憶體／耐久輸入 owner 或 prepared／dispatched／uncertain 動作。
尚未結束的協調派送及未到保留期限的派送均阻止回收。與 begin／claim／續接／接收共用批次鎖，
並在同一寫入交易內重驗年齡與狀態。只串聯刪除已安全結束的本機批次資料及派送；任務產物仍依
既有所有權／已知檔名規則清理，不影響其他 WorkQueue 或使用者成果。

running／waiting_review／approved 批次不自動到期；所有仍保留的本機批次持續保護標記任務、
可信接收、收據／採認來源及復原後繼，個別任務超過保留天數也不移除 actor gate 或待審閱證據。
這不會延長遠端目的端保留期；遠端證據到期／缺失仍不可採認，須另有明確跨主機保留／移交契約。

尚缺步驟
--------------------------------

管理員替其他 owner 復原本機任務時，可在 preview／review_authorization 加入
``owner_policy="source_owner"``，明確 create／create_authorized 另帶 ``ownership.review`` 為
``ownership_review``。子任務保留來源 owner，另記真正審閱者，輸入前持續驗證雙方權限；整圖
沿用原 owner 讀取與真實 recovery chain，即可採認獨立完成的子任務。GUI 提供擁有者選擇，須有
相符預覽。省略政策仍由真正建立者持有；已存在的 caller-owned 子任務不自動移轉或補造接收紀錄，
其明確唯讀成果移交仍列於 Progress.md。不會為採認自動放寬其他任務可見性。

舊圖不能事後自動當作已綁定批次；採認只證明
歷史邏輯階段，不重建登入／視窗或宣稱目前應用狀態。假目標、自有本機／雙主機 HTTP 與 offscreen
證據不代表正式部署、實際模型或原生驗收。瀏覽器維持 je_web_runner。
