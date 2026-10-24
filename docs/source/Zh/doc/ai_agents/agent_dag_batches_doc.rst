受管 DAG 批次身分
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

這批提供初次執行證據；整圖明確續接核准、審閱後替代任務採認、相依重新驗證、服務背景批次協調及
保留／清理仍列於 Progress.md。舊圖不能事後自動當作已綁定批次；假目標、自有本機／雙主機 HTTP
與 offscreen 證據不代表正式部署、實際模型或原生驗收。瀏覽器維持 je_web_runner。
