任務恢復與重新授權
================================================

經審閱的新任務
----------------

桌面／瀏覽器 context 退休後，不能以歷史欄位收據直接續跑。
``manage_agent_recovery("preview", {"task_id": source_id})`` 只讀停止的有限 skill，
不觀察或操作目標；回傳來源收據摘要、逐筆結果、已嘗試／已驗證步數、剩餘動作及綁定精確來源
任務／收據／人工見證的 ``snapshot``。未知副作用、讀回失敗、舊座標或缺少新 capture 來源時
不提供可提交草稿，未知步數不會標示已完成。

操作人須審閱目前應用狀態，以來源範圍內的語義動作／新 capture 重建必要準備，再明確呼叫
``manage_agent_recovery("create", request)``，提供 ``task_id``、``snapshot``、``spec`` 與
非空 ``note``。只可修改目標說明與動作；target、工具、根目錄、app、inputs、預算、options
與完成條件固定，移除私有 skill 發布 pin。不接受舊 capture、觀察索引及座標動作；未知副作用
須先經既有收據核對流程處理。來源變更須重新預覽／核准，尚未釋放的輸入租約阻止建立替代任務。

新任務與唯一來源關聯在同一 SQLite 交易內提交；相同核准重試、重啟或建立回覆遺失，都回傳同一
新任務，不同核准則衝突。來源保留狀態、原收據、見證與逐筆結果；新任務從零收據開始並重新驗證
完成，不會使來源成功；已移交的來源不能再恢復執行。任務／列表 metadata 的 ``recovery`` 顯示來源關聯。新任務仍存在時保留
來源證據；新任務移除後仍保留關聯直到來源到期清理，重送舊核准不能復活已移除的任務。

共用介面為 ``AC_agent_task_recovery``、MCP ``ac_agent_task_recovery``、
``POST /agent/recovery``（``{operation, request}``）、Builder 與
``agent-task recovery preview|create request.json``；兩種操作均需 ``drive_input``。
Agent 任務的 Actions 提供「審閱剩餘工作／重新規劃」及「建立經審閱的新任務」。有效預覽只填入獨立的
Recovery JSON 編輯器及空白註記，不填入或提交一般任務表單；審閱計畫／註記後再明確建立。
切換任務會清除草稿，遲到回覆會忽略。建立後走既有耐久背景派送，關閉視圖只解除請求訂閱。
登入／視窗恢復、任意指標的新定位及實際應用／原生驗收仍待接合；不新增瀏覽器引擎或付費依賴。

外部 agent 與本機模型重新規劃
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

恢復流程也支援停止的 ``external`` 與 ``ollama`` 任務。這兩種模式沒有可執行的有限前綴，
預覽因此回傳 ``completed_steps=null``、空剩餘動作／逐筆結果、``draft=null`` 及
``new_plan_required``。獨立 ``review_template`` 保留來源範圍、模式、模型／端點、預算與完成
條件，但目標／動作留空；即使舊規格有未使用的動作陣列，也不推測它曾執行或代表剩餘工作。

操作人須明確填寫非空目標及審閱註記；審閱後可沿用原目標文字，但不因此繼承完成進度。
新任務不可夾帶未使用的動作或切換模式／模型設定。未知副作用仍須先核對
並重新取得來源快照；不複製已完成收據、舊觀察或模型歷史，模型停止但缺新完成證據時仍為未知。

既有 API／AC／MCP／REST／CLI／Builder 共用此流程。GUI Actions「審閱剩餘工作／重新規劃」
只準備獨立 Recovery 編輯器，目標／註記留空，不自動提交。外部任務由 caller 重新 observe／act；
明確核准的 Ollama 新任務走既有背景派送，以原模型／loopback 端點建立新 backend、取得新觀察，
首輪歷史為空。預覽不呼叫模型 HTTP。自有假 Ollama loopback 服務核對 show／chat 順序、模型、
新目標與空歷史；這不代表已安裝模型驗收，實際模型／原生證據仍列於 Progress.md；來源重新授權見下節。

明確核准新任務的來源授權
--------------------------------

客戶端 session 退休可能使 origin witness 失效。一般 ``preview``／``create`` 仍要求原來源授權有效；
重新授權使用相同 API 的兩個明確操作：

1. ``manage_agent_recovery("review_authorization", {"task_id": source_id})`` 回傳來源 ``snapshot``、
   ``authorization_review`` 摘要、範圍裁切後的授權內容，以及草稿或可編輯 ``review_template``。
   審閱不啟動目標、不呼叫模型。
2. 審閱剩餘工作後，向 ``manage_agent_recovery("create_authorized", request)`` 提供 ``task_id``、
   ``snapshot``、``spec``、非空 ``note`` 與 ``authorization_review``。

原本正規化的根目錄是上限；所有仍有效的舊限制必須保留，再加入目前 caller 的限制並取交集。
只可為新任務取代失效的舊見證，不修改見證檔、不恢復來源任務；目前 caller 的授權失效則拒絕。
沒有 session policy 的可信主機呼叫仍須明確核准，並受原目錄與主機 profile 限制。公開審閱內容不
揭露原範圍外的其他根目錄。操作人只可維持或縮小建議根目錄；工具、app、inputs、模式／模型／
端點、預算、完成條件及其他 options 固定，不能刪除仍有效的限制。

摘要綁定來源快照與有效授權內容；目錄或 session 變更須重新審閱，來源收據變更須重取快照。
完成條件超出新範圍時不提供可執行模板；剩餘動作不相容時須修改並完整驗證，不會默默移除完成
條件。動態任務仍須明確填寫目標。未知副作用須先核對，未釋放輸入所有權仍阻止建立；重新授權
不解除隔離，也不代表登入／視窗／原生就緒。

新任務、唯一來源關聯及授權證據在同一交易提交；``recovery.reauthorization`` 保存審閱摘要、
受限內容、核准根目錄及操作人。新任務到期後仍保留稽核，直到來源清理；``existing_successor``
可查已退休的新任務，重送核准不能建立第二個或改用其他核准模式。

四種操作均需來源 owner／operator 的 ``drive_input``；API／AC／MCP／REST／Builder 共用契約。
CLI 為 ``agent-task recovery review_authorization|create_authorized request.json``；GUI Actions
新增「審閱新任務授權」及「建立重新授權的新任務」。審閱只填獨立 Recovery 編輯器，註記留空，
須另行明確建立。證據使用確定性假目標、已驗證身分的 loopback HTTP 及 offscreen Qt；
技能更新見下節；trigger 更新、應用狀態重建與實際模型／原生驗收仍列待辦。

已發布技能的授權更新
--------------------------------

技能使用獨立於停止任務恢復的流程。對目前已發布版本呼叫
``manage_agent_skill("review_authorization", {"candidate_id": published_id})``，取得 ``snapshot``、
``authorization_review``、裁切後的 ``authorization`` 與 ``spec``。審閱不觀察、不執行、不發布；
固定動作／完成條件超出縮小範圍時回傳 ``spec=null`` 與 ``authorization_scope_unavailable``。

明確 ``manage_agent_skill("create_authorized", request)`` 須提供 ``candidate_id``、``snapshot``、
``authorization_review``、經審閱的 ``spec`` 與非空 ``note``。保留仍有效的舊限制，只為新候選
取代失效來源；根目錄只能維持或縮小，受原上限與目前權限交集限制。目標、完整動作、工具、app、
inputs、模式／設定、預算、完成條件及參數定義固定；語義內容變更須另走後續修復候選流程。

結果是同一技能系譜的新草稿，版本為零，保存父版本、操作人／授權內容／核准目錄證據，不繼承發布
或驗證 trial。須重新 ``validate``、獨立驗證成功，再明確 ``accept``，提供父 ``expected_version``
及註記；舊 trial 不能發布新候選。舊版本及執行中 pin 不變，``run`` 須明確選擇新版本，來源失效的
舊版本仍拒絕執行。候選及唯一核准關聯在同一交易提交，相同內容重試、重啟或並行呼叫均去重；
父版本／目前授權變更須重新審閱，寫入交易內也核對發布競爭。

共用介面為 ``AC_agent_skill``、MCP ``ac_agent_skill``、``POST /agent/skill``、Builder 與
``agent-task skill review_authorization|create_authorized request.json``；GUI 技能操作選單提供兩種
操作，須明確執行 Actions 的技能操作，不會自動建立任務或發布版本。直接審閱也須 owner／operator
的 ``drive_input``。證據限假應用、已驗證身分的 loopback 與 offscreen GUI；原生驗收及 trigger
明確重新註冊仍列於 Progress.md。
