# AutoControl

只有受管任務節點的 DAG，可用 `manage_agent_dag("register", {"definition": graph,
"max_parallel": 4})` 註冊耐久批次，再明確 `run_dag(graph, batch_id=batch["batch_id"])`。
註冊不操作目標；保存整張圖的拓樸、節點契約、主機設定與並行數，目的端 key／規格標記綁定批次。
可能派送前先提交 claim，目的端精確規格、完成及輸入釋放證據通過後才放行相依節點。成功、中斷或
提交回覆遺失後都不能再次 begin；`get/list/inspect` 讓協調紀錄跨重啟保留。API／AC／MCP／REST／
CLI／Builder 及 DAG Actions 的批次註冊／讀取、選填批次 ID 共用流程。
停止後以 `review_continuation` 取得唯讀整圖快照及逐節點決策，再把審閱的 `snapshot`、`decisions`
與非空 `note` 放入 `run_dag(graph, batch_id=id, recovery=request)`，核准並使用一次續接機會。
只能採認獨立完成的原任務或真實 recovery 後繼任務；派送限從未 claim 且目的端未接收的 pending
節點。本機授權可在相等或更窄根目錄內更新，未知 claim 永不重播。DAG Actions 提供停止新派送、
審閱及明確續接；已接受任務仍依自身生命週期處理。將協調交給已明確啟動的服務，可呼叫
`manage_agent_dag("run_background", {"batch_id": id, "definition": graph, "max_parallel": 4})`；
明確批准的續接另帶 `approval_id`。DAG Actions 提供兩個背景動作；關閉視圖不停止已接受的服務工作，
`get.background` 提供有限佇列狀態。重啟使舊 attempt 失效並要求審閱，不重播排隊或未知派送。
原 owner 與提交者的權限持續重新驗證，本機任務綁定所屬 runtime。批次保留／清理仍列於 Progress.md。
caller 協調的受管批次固定來源服務路徑、端點、憑證指紋及世代，本機節點共用同一 client；連線檔
身分變更就停止後續呼叫並要求明確審閱。服務端批次證據直接讀取所屬 runtime，綁定不快取 bearer
憑證。一般非批次 client 保留動態連線行為；受管批次須有含世代的連線資料。
本機批次節點在耐久 claim 後使用來源服務的封閉 `local_task` transport，以原 owner 接收精確規格／
key，並在交易內記錄真正 caller。輸入前更新雙方權限及 attempt；管理員失去跨 owner 管理權也會
阻止執行。沒有可信接收紀錄的舊請求不補造見證。任務 metadata 提供有限 `local_dag_admission`
稽核資料，已接受輸入仍依既有清理契約處理。
詳見[續接協定](../docs/source/Zh/doc/ai_agents/agent_dag_batches_doc.rst)。

觸發器可明確使用 `manage_agent_trigger("review_authorization", {"trigger_id":"..."})`，再以
`create_authorized` 提供 `trigger_id`、`snapshot`、`authorization_review`、經審閱的 `spec` 與 `note`。
新註冊保留完整模板／設定／待處理上限，受原授權、仍有效限制與目前權限交集約束；交易內退休舊綁定，
並啟用未來通知。共用歷史讓已接受事件與未完成任務跨更新、移除及重啟保留，沿用的舊排隊事件不再派送。
排程從未來時段開始，檔案檢查點保留。API／AC／MCP／REST／CLI／Builder 及 GUI 觸發器選單共用流程；
一般啟用不能取代失效授權，審閱只準備註記留空的請求。

已發布技能可用 `manage_agent_skill("review_authorization", {"candidate_id":"..."})`，再明確
`create_authorized`，提供 `candidate_id`、`snapshot`、`authorization_review`、經審閱的 `spec` 與
`note`。完整計畫與參數定義固定；保留原根目錄上限及仍有效限制，與目前權限取交集。流程只建立
同一技能的新草稿及稽核證據，須重新驗證並明確發布下一版，舊版本不變。相同核准去重，過期版本／
授權內容拒絕。API／AC／MCP／REST／CLI／Builder 與 GUI 技能操作選單共用此流程；trigger 更新使用上方獨立流程。

來源授權失效的停止任務，可明確使用 `review_authorization`，再以 `create_authorized` 提供
`task_id`、`snapshot`、經審閱的 `spec`、`note` 與 `authorization_review`。新任務保留所有仍有效的
來源限制，將目前權限與原根目錄上限取交集；根目錄只可維持或縮小，其餘權限、模式／模型、預算及
完成條件固定。核准證據與唯一新任務在同一交易保存；來源及已撤銷的見證不變。既有共用介面均提供
這兩種操作，GUI Actions 另有授權審閱／建立命令，詳見[恢復指南](../docs/source/Zh/doc/ai_agents/agent_recovery_doc.rst)。
任務恢復不解除輸入隔離，也不重建應用狀態；技能與 trigger 使用上方獨立更新流程。

停止的任務可用 `manage_agent_recovery("preview", {"task_id": "..."})` 審閱來源收據與快照，
不接觸應用程式。有限 skill 提供剩餘動作及逐筆結果；外部 agent／本機模型任務則提供空白目標的
`review_template`，須由操作人明確填寫剩餘工作目標，不複製舊動作清單。明確 `create` 時提供
快照、經審閱的規格與註記，建立有來源關聯的新任務，重新觀察並從零收據開始；重複核准回傳同一
任務。執行模式、模型／端點、範圍、預算及完成條件固定，未知副作用須先人工核對；不移植舊
capture、索引、座標或已完成歷史。可用 `AC_agent_task_recovery`、MCP／REST、
`agent-task recovery preview|create request.json`，或「Agent 任務 → Actions → 審閱剩餘工作／
重新規劃／建立經審閱的新任務」。已移交的來源不能再恢復，須由新任務繼續；登入與視窗恢復仍須審閱。

Android／iOS 內建受管 profile 仍未提供。內部遠端副作用防護會依實體裝置識別保存動作前／後確認；
本機 helper 結束但動作未確認時，仍保留隔離。恢復須在 writer 退出後取得可信裝置證據，並以
後續能使舊指令失效的世代證明安全。尚無內建 SDK 證據來源、裝置 profile 或原生驗收；
剩餘接合列於 `Progress.md`。
內部 Android 傳輸只連明確設定的既有 loopback ADB server，不呼叫 CLI、不管理 daemon、
不重試或退回舊 shell；shell-v2 的退出證據有封包／輸出上限，但不代表應用完成、實體裝置
身分或輸入已釋放。
內部 Android session 會核對指定端點、實體序號、boot 與預設顯示器焦點，並以原子方式固定
boot。有限輸入提案在命令連線內重驗身分／焦點，限制文字與結果；提案不授權輸入，仍須接合
輸入視窗、遮擋、鎖定／真人活動與自有 worker。
Android 檢查後提案會綁定目前的原生輸入視窗／佇列及 keyguard 證據，核對完整觸控路徑、
外部攔截與遮擋，並在命令連線內重驗摘要。舊 ANR／歷史紀錄不能證明目前狀態；真人活動、
全域監看器審閱仍須可信來源授權，內建受管裝置執行仍未開放。
內部 Android 動作協定 v2 區分完整前置拒絕、輸入失敗、輸入後拒絕與輸入返回。
缺少／錯誤階段或退出碼不符都維持未知；輸入返回不代表遠端輸入已清空或任務完成，也不授權重試。
內部自有遠端 SDK worker 會核對精確任務／擁有者範圍、重新授權與真人接回；可信主機 factory
建立前先啟動 parent 監看。持久化 begin 並收到 ACK 後才呼叫 SDK，相符裝置／世代的清理證據
通過後才送 end；缺證據維持隔離。可信裝置控制來源、WDA adapter 與受管 profile 仍待接合。
內部 AndroidRemoteAdapter 已透過逐命令 AndroidCommandLease 接合 checked session 與 worker；
每個動作消耗一次新的身分／輸入路由／安全觀察，SDK 重新編譯有限命令後才透過 ADB 送出一次。
裝置端防護須在真人接回、取消或到期後阻止舊寫入；沒有預設 provider，標準 ADB 或停止本機
helper 不能提供這項保證。清理證據還須綁定新的隨機命令 ID、boot 及獨立輸入／佇列狀態。
可明確配置主機 hierarchy_reader，提供有界、限 app 的語義元素及經審閱的非敏感文字；未配置時
仍只有身分 metadata。XML 不授予文字權限；編輯／密碼值及受保護子節點持續遮罩，不發布原始
XML 或私有 freshness hash。公開觀察版本隨來源及動作更新；Android 元素參照須來自目前可操作
的語義元素。新的畫面讀回可確認已審閱文字出現，缺少／部分／遮罩內容不能證明文字不存在。
不新增 CLI／SDK 啟動或擷取備援；真實來源、受保護欄位值驗證、Unicode／IME 與受管 profile 仍待交付。

受管畫面完成驗證將內建桌面與 WebRunner 預覽視為部分文字證據；檔案目標與等待視窗階段沒有
語義畫面證據。已知安全文字可確認出現或推翻不存在條件，遮罩與明確隱藏的標籤不可作證。
組合條件缺少任一必要證據時保持未知，已知矛盾則判定失敗。精確 DOM／欄位值應使用明確的
瀏覽器完成讀回；未宣告覆蓋旗標的自訂 target 保留既有行為。

`lookup_agent_task("鍵", reviewed_spec)` 可選擇由目的地主機正規化規格，與原擁有者提交時保存的
不可變摘要比對；回覆宣告 `spec_match_contract=1`，並提供一致／不同／無法核對／查無紀錄。
CLI 可加 `--spec reviewed.json`；AC／MCP／REST／Builder 共用可選物件。DAG 檢視先查鍵，再於
目的地明確支援契約時核對已審閱的節點規格；舊端維持 `unverified`，本機來源 witness 不送到遠端。
鍵改指向別的任務會使舊快照失效；比對一致時仍須核對完成報告的種類、數量與通過結果。
節點比對不等於整張 DAG 拓樸／原批次批准，
`resume_permitted=false` 仍保留明確續接審閱。

`inspect_agent_dag(definition, timeout_seconds=30)` 可檢視本機／已登錄遠端主機的既有提交，
不提交、不暫停、不續跑。提供 `AC_agent_dag_inspect`、MCP、REST 動作、CLI
`agent-task inspect-dag reviewed.json`、Builder 與 DAG Actions。最多 100 節點、最長 300 秒；
遠端仍須主機管理權限，不傳送本機身分／資料庫路徑／來源 metadata，不回傳遠端路徑或原始錯誤。
`recorded_completion` 只描述查回的任務；節點規格可選擇核對，`resume_permitted=false` 仍表示尚未
授權整張 DAG 續接。查無紀錄不代表拒絕；GUI 在圖形編輯後捨棄舊檢視。

提交回覆遺失時，可用 `lookup_agent_task("原去重鍵")`、`AC_agent_task_lookup`、MCP、
`POST /agent/lookup`、CLI `agent-task lookup 原去重鍵` 或任務視圖 Actions 查詢。只讀取原身分及
使用者資料庫範圍，不提交、不續跑、不取得輸入控制權；`found=false` 只是當下快照，晚到請求仍
可能被接收。GUI 不會讓舊查詢回覆覆蓋後來選取的任務／鍵。DAG 檢視亦沿用此查詢；規格綁定及續接審閱仍待完成；
唯讀查詢仍須具任務存取權限。

既有 `run_dag`／`AC_run_dag`／MCP `ac_run_dag`、REST／CLI 動作檔、Script Builder 與 DAG
Actions 選單支援受管任務節點：以 `task` 取代 `actions`／`action_file`，內容包含 `spec`、必填的
`idempotency_key` 與可選的 `wait_seconds`。省略 `host` 使用明確啟動的本機服務；遠端使用管理員
已登錄的主機。該端須已配置有背景派送的授權 runtime，本功能不部署服務。規格限 skill 或明確
配置的本機模型模式，工具、目的地主機路徑及完成條件由該端驗證。
節點只提交一次，等待完成條件通過、持久完成契約及輸入釋放證據後才啟動下游。同一批次恢復
須保留去重鍵；不自動恢復暫停任務或重播副作用。停止、逾時或通訊／權限失敗時，已知任務 ID
才會提出有時限的暫停；未收到確證仍為未知。失敗結果保留 ID／去重鍵並阻擋相依節點，GUI
表格顯示任務 ID。本機身分、使用者資料庫路徑及來源 witness 不送到遠端。正式多機部署及原生／
裝置驗收仍分開追蹤。

DAG 型別與函式亦可由 `je_auto_control.api`／`je_auto_control.api.core` 匯入。

受管任務在確認輸入清理後才發布成功。清理失敗或仍忙碌時保留輸入租約並要求審閱；確認前
中斷仍需恢復。完成發布採條件式狀態轉換，不覆寫同時到達的取消要求。既有 GUI／API 任務
結果以 `metadata.input_released` 顯示釋放狀態；新成功紀錄保存 `completion_contract=1`，舊紀錄
維持零而不自動認證。成果報告依最終狀態更新，供後續 DAG 協調判定。

DAG 節點在執行緒池中保留呼叫者授權、取消與指令限制，自訂 runner 亦適用。每個節點執行前
重新讀取使用者權限；已刪除的使用者會使節點失敗，後續相依節點略過，各操作依更新後的角色
檢查權限。預設遠端節點在開啟主機通訊錄或動作檔案前要求 `manage_hosts`，避免透過主機憑證
擴大本機操作權限。管理員及受信任的直接 Python 呼叫仍可遠端派送。受管節點沿用上述完成
驗證與停止契約；正式多機部署及原生驗收仍待完成。

瀏覽器主機目標可透過可選的 `settings.helper_python` 指定已審閱且已安裝套件的 Python
環境（本機絕對直譯器路徑）。明確指定的 helper 使用 `-I`，從該環境載入已安裝套件；虛擬環境
直譯器的符號連結保留環境身分。任務選項不能指定直譯器。
主機管理者可使用 `manage_agent_target("probe", {"name":"reviewed-browser"})`、`AC_agent_target`、
MCP／REST、`agent-task target probe request.json` 或 GUI 主機目標的診斷操作。
診斷以獨立且有時限的自有 helper，透過 `je_web_runner` 檢查瀏覽器依賴後結束，過程不取得輸入
擁有權或啟動瀏覽器。結果可顯示 `python_dependencies_ready`；瀏覽器啟動及原生證據仍明確保持
`not_probed`／`not_recorded`。`last_probe` 僅為記憶體中的具時間診斷快照，不授予任務權限，
也不啟用停用的目標。桌面／裝置的原生診斷仍待完成。
已準備的隔離環境安裝兩個功能工作樹建置的 wheel；共用環境與正式工作樹保持原狀。正式服務
設定及實際瀏覽器驗收仍分開追蹤；所有瀏覽器自動化仍統一由 WebRunner（`je_web_runner`）提供。

桌面固定技能現在與瀏覽器技能共用工作階段連續性檢查。桌面 scope 或自有 helper 結束後，
沿用舊前綴前必須審閱，不能用歷史紀錄證明暫停後的表單／視窗狀態。未中斷的工作階段可正常
執行；檔案 adapter 仍以持久化產物處理復原。檢查在替代 helper 啟動前執行，既有續跑／狀態／
紀錄介面會顯示人工審閱結果。暫存表單／登入／視窗狀態恢復與可審閱的剩餘步驟重建仍待完成；
原生驗收維持暫停。

固定瀏覽器技能的已驗證前綴，現在必須保有原本仍存活的瀏覽器／helper 工作階段。
暫停、清理、helper 中斷或 runtime 重啟後，舊動作紀錄無法證明表單仍保有先前欄位值；
續跑會在啟動替代 helper 或送出下一動作前進入人工審閱。請明確檢視剩餘步驟並建立新任務。
尚無保留嘗試紀錄的暫停，以及已審閱為 failed／not_applied 的嘗試，允許全新開始。
外部擁有者仍可重新觀察新工作階段，再規劃授權範圍內的新動作；未中斷的固定技能沿用原
工作階段。登入及暫存表單狀態的恢復仍是未完成工作。

本機 runtime 的使用者及即時根目錄授權轉送，現在必須由明確的本機服務呼叫啟用。
一般具驗證的 HTTP 請求只帶指定的 Bearer token；runtime client 驗證 loopback 服務目的地與
路由後，才附上本機使用者／來源儲存庫／witness 資訊。版本化 `je_auto_control.api` 現在提供
所有已宣告的 `api.core` 名稱，包含受管瀏覽器命令、目標復原及技能；動作型別 stub 也涵蓋
所有出貨命令。未解析的延後專案型別沿用產生器既有的 `Any` 政策，避免產生無效名稱。
並行預算讀取改在資料庫獨佔交易內取樣時鐘，避免鎖取得順序不同造成任務誤判逾時；真正的
時鐘倒退仍會停止任務。GUI／MCP／REST／CLI 共用這些修正；正式工作樹及既有原生／瀏覽器／
裝置／24 小時驗收暫停維持原狀。

受管瀏覽器檔案命令 `browser_link`、`browser_download`、`browser_upload`（對應 `AC_browser_*`）
委派給 WebRunner 傳輸契約版本 1。上／下載授權必須具有明確的主機及任務根目錄；下載讓瀏覽器
Cookie 保留於自有 SDK／helper，核對完整長度及可選 SHA256，且不覆寫既有檔案；重用必須符合
指定 SHA256。上傳將最多 4 MiB 的單一一般檔案讀成核對過的不可變快照，驗證可選 SHA256 與
SDK 中繼資料，不自動提交表單。網路操作仍全部位於 `je_web_runner`。
瀏覽器 `download_archive` 預覽接受查詢頁 `url`、明確 `allowed_origins`、授權範圍內 `directory`，
以及具有單純 `name`、`url` 或連結 `selector`／可選 `frame` 的 `files`；每檔可用 `page_url` 覆寫
查詢頁。流程擷取新連結、下載每檔最多 16 MiB，並產生供獨立核對名稱／大小／雜湊的歸檔清單。
GUI Actions 只草擬檔案目標／流程／上傳範例，不啟動資源；MCP／REST／CLI／Builder／模型工具
共用命令，連結讀取仍需輸入控制權限。部署與實際瀏覽器驗收仍待完成，既有驗收暫停保持生效。

瀏覽器任務可固定完成條件，例如
`{"kind":"browser","operation":"value","selector":"#field","value":"expected"}`。
操作為精確的 `text`、`value`、`visible`（布林）或 `url`（不含定位）；必須明確授權
`AC_browser_read` 與任務 origins，完成條件不會增加權限。Finish 由同一個自有 helper 檢查
目前頁面位於允許的 HTTP(S) origin，再透過受控讀取命令獨立取得 SDK 完整值；既有 receipt、
有界預覽或模型停止訊號不能代替讀回。空白／不可用／範圍外頁面、被拒讀回或錯誤驗證回覆
保持未知；比較不符保持失敗。取消、權限撤銷及人工審閱錯誤保留原類型。
GUI Actions 可草擬不啟動資源的瀏覽器完成範例；API／MCP／REST／CLI finish 共用驗證器。
SPA URL fragment 會保留，origin 比對僅略去 fragment。實際瀏覽器／應用驗收及已審閱傳輸仍待完成。

受管瀏覽器啟動前，必須先確認 WebRunner 的 `ManagedBrowserSession.contract_version == 1`，
通過後才建立 policy 或開啟代理／瀏覽器。缺少、布林、文字、過舊或未知標記會保留可處理的
就緒錯誤。SDK 來源 `575e5d2` 提供完整 text／value 讀回：最多 8,000 個 UTF-16 code unit，
超限或無效 Unicode 就拒絕，不截短。AutoControl 對瀏覽器參數與流程預覽資料套用相同 Unicode
上限，在副作用前拒絕。跨來源契約透過真正的自有 helper 與替身 Chromium 驗證；部署與實際
瀏覽器／原生驗收保持分列。


`draft_agent_workflow("batch_form", config)` 與 `transfer` 可設定 `backend: browser`，
並提供明確的 `allowed_origins` 與已審閱 browser target。CSV／XLSX 來源仍受 roots 限制；
瀏覽器草稿只產生 `AC_browser_*` 動作，不退回桌面輸入。填表提供 `url`、CSS `fields`、
可選 frame／新增資料控制項、送出與確認 selector；每次填入都有獨立的精確 value 讀回。
可用 `confirmation_column` 從每列取得預期確認文字。轉填提供 `source_url`／`destination_url`，
擷取 text／value、套用白名單轉換、填入並讀回目的欄位，再驗證儲存；送出前拒絕陳舊確認。
`AC_browser_wait`／`browser_wait` 只輪詢 text／value，也支援稍後才出現的元素；`wait_seconds`
預設 5 秒，受 action budget 限制，逾時才回來的相符結果仍拒絕，不重播填入或點擊。
Python/core、共用 catalog／模型 schema、MCP、CLI／REST 任務操作、Builder 及 GUI 流程預覽
使用同一編譯器。瀏覽器讀回可作為獨立技能證據。實際應用驗收、已審閱上／下載許可仍待完成；
SDK 啟動前須通過完整有界讀回契約版本 1 的檢查。

受管瀏覽器 profile（`kind: browser`）統一委派給 WebRunner 的 `je_web_runner` SDK；
開發來源為 `D:\Codes\WebRunner`，整合來源位於其隔離的受管 session 功能分支。
Profile 必須提供精確的 `settings.allowed_origins`、瀏覽器專用工具，且不能授權桌面 app；
每項任務另須設定非空、較窄的 `options.allowed_origins`，每次啟用均重新核對兩層範圍。
註冊不啟動資源；helper 環境須明確安裝已審閱的受管 SDK 與 Chromium，缺少時就緒失敗，不自動安裝。
`AC_browser_navigate`、`AC_browser_click`、`AC_browser_fill`、`AC_browser_select`、`AC_browser_check`
及 `AC_browser_read` 共用 Python/core、executor、MCP 與 Builder 定義。命令只在受管 helper 中
運作，透過既有 task submit/observe/act 週期驅動。讀取操作為 `text`、`value` 或 `visible`；
WebRunner 拒絕秘密表單欄位。DOM 索引在目前 observation 內解析 selector／frame，再核對新鮮度。
失敗副作用保持不確定且需對帳；暫停／取消會結束擁有的資源。GUI Actions 可產生瀏覽器目標範例
供審閱；DOM 選取只編輯動作請求。專用 helper 跨就緒檢查保留同一個全新 session，正常清理先
取得瀏覽器 ACK，再結束自己的程序樹，不取得共用桌面輸入控制權。跨來源受控測試使用真正 SDK、
替身 Chromium、自有 IPC／loopback；實際瀏覽器／原生驗收、已審閱傳輸及瀏覽器流程編譯仍列於 `Progress.md`。

MCP 非同步呼叫會保留接受請求時的角色、session、原路徑政策與工具清單；session 或路徑政策
結束後，延遲分派會被拒絕。非同步無狀態呼叫仍使用固定 profile。外掛工具清單變更會送達所有
有效 HTTP session 串流；session 啟停只通知擁有者，並避免重複發送。串流註冊與 HTTP 標頭
共用鎖，避免提早送出的通知破壞 HTTP 回應。
純 metadata 的 `benchmarks/mcp_discovery.py --repeats 20` 量測工具數、JSON bytes、暖機後的
程序內交握、搜尋與啟用耗時。Windows／Python 3.14.4 的紀錄中，完整模式初始有 732 個授權工具、
358,029 bytes；逐步模式為 5 個、2,029 bytes，回應大小減少 99.43%。交握為 58.263／47.439 ms，
搜尋中位數為 16.243／19.718 ms；逐步啟用中位數為 42.486 ms。此本機量測不含冷啟動匯入及原生操作。
有日期的 JSON 紀錄位於 `docs/benchmarks/`；既有參數政策的涵蓋限制仍列於 `Progress.md`。

MCP 可選擇 session 逐步揭露：`je_auto_control_mcp --tool-mode progressive` 初始只提供五個
探索控制工具；`ac_mcp_tools_enable`／`ac_mcp_tools_disable` 只改變該 session。
不會更新工具清單的客戶端可使用 `--tool-mode static --tool-profile ac_screen_size,ac_list_windows`；
預設 `full` 保留不分頁的授權工具清單。逐步／固定模式的 cursor 不透明、只能使用一次，並綁定
快照與呼叫者；工具、角色或清單設定變更，以及 cursor 過期時，須重新執行 `tools/list`。
啟停只通知擁有者連線；session 結束會回收 cursor 並使尚在執行中的 metadata callback 失效。
HTTP／嵌入式使用 `MCPServer.configure_tool_disclosure(...)`；主機環境變數為
`JE_AUTOCONTROL_MCP_DISCLOSURE` 與逗號分隔的 `JE_AUTOCONTROL_MCP_TOOL_PROFILE`。
`plan_mcp_tool_profile(...)` 及 Diagnostics Actions 可預覽啟動參數，不會啟動服務。
無狀態協定使用不分頁的初始固定清單，不保留 session 啟用狀態。唯讀限制也涵蓋後續新增的外掛。
未驗證／共享 token 連線顯示 operator 工具，與既有呼叫上限一致；主機管理工具仍須已驗證身分。

MCP 工具探索提供 `search_mcp_tools(query, limit=10)`、`get_mcp_tool_schema(name)`、
對應 AC／MCP 指令及 Diagnostics → Actions。搜尋回傳有界摘要、分類與所需權限；完整 schema
須指定單一工具查閱。兩種查詢都重新驗證角色，並遵守 registry 的唯讀篩選；MCP 查詢使用該
server 的即時 registry，包含外掛變更。CLI 可執行
`je_auto_control_mcp --search-tools document --limit 5` 或 `--tool-schema ac_mcp_tool_search`。
完整模式仍為預設；各 session 的逐步揭露可依前述設定啟用。

Agent 工具呼叫經 `executor.execute_one(name, arguments)` 回傳原始結果，與動作腳本共用
授權、變數插值、取消及日誌邊界；拒絕私有 executor 參數。受管任務交付進度見 `Progress.md`。

輸入控制權會在分派及輸入確認前寫入持久紀錄。服務崩潰後，先手動放開按鍵與滑鼠按鈕，再以主機管理權限呼叫 `recover_agent_target(target, note)` 記錄審閱並恢復目標；任務未知結果仍須另外核對。工作區文件由輸入 helper 之外的程序啟動，指定的聚焦步驟會等待授權應用程式視窗就緒。

受管技能將已驗證的語義流程錄製為不可變候選。`manage_agent_skill` 可預覽具型別的參數、執行獨立驗證任務，並在明確審閱該候選的成功證據後發布編號版本。定位器修復會產生須重新驗證的候選；任務固定使用原版本與摘要。AC／MCP／REST／CLI 與 Agent Tasks 的 Actions 選單提供相同操作。

受管任務保留來源路徑政策：移除根目錄後，後續動作、事件觸發及技能驗證會受阻。MCP 客戶端根目錄依連線階段隔離，來源授權結束後撤銷；主機設定的固定政策則在明確更換前保留。服務停止會取消實際執行中的工作，包含取得輸入前的模型初始化，尚未啟動的派送則持續保存。

實驗性的[受管 Agent 任務](../docs/AGENT_TASKS.md)提供擁有者範圍內的提交、觀察、動作、驗證、
暫停、恢復、取消、控制權世代、持久化回執、WorkQueue 派送與本機 Ollama 推論。
Python、AC、MCP、REST、CLI 與 Agent 任務面板共用背景服務，明確執行
`je_auto_control agent-task start` 才啟動；新流程不強制依賴外部服務。
四條可預覽範本涵蓋下載歸檔、CSV/XLSX 填表、跨應用轉移與工作區準備；
使用 `agent-task draft` 或 Actions 的「預覽工作流程」檢查後提交。
持久化間隔、Cron、檔案與事件綁定會保留核准範圍，每次觸發重新授權並去重；
提交識別碼避免重試與重啟時建立重複任務。
提供擁有者範圍內的回執與結果不明對帳，連結執行歷史、journal 及逐筆報告；
服務快取預設保留 30 天，保留使用者輸出與外部 journal。
原生呼叫使用專屬 helper，支援取消、逾時、輸入記錄清理與跨資料庫的桌面排他控制。
Windows 共用桌面須解鎖並閒置 60 秒，實體鍵鼠活動會觸發暫停；`agent-task stop-all` 停止可見任務。
其他共用桌面須有可信活動 adapter。原生平台驗收與其餘待辦列在 `Progress.md`。

[![PyPI](https://img.shields.io/pypi/v/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![Python](https://img.shields.io/pypi/pyversions/je_auto_control)](https://pypi.org/project/je_auto_control/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](../LICENSE)
[![Documentation](https://readthedocs.org/projects/autocontrol/badge/?version=latest)](https://autocontrol.readthedocs.io/en/latest/?badge=latest)

**AutoControl** 是一套開源、跨平台的 **computer-use 與 GUI 自動化框架**，面向 AI agent、Python 應用程式與自動化測試。它能驅動滑鼠與鍵盤、透過樣板比對、OCR、作業系統無障礙樹或視覺模型找到 UI 目標、錄製與重播流程，並以 JSON 動作檔執行——支援 Windows、macOS、Linux（X11 與 Wayland）、BSD、Android 與 iOS。

每項能力都以三種形式提供：**Python API**、可在 JSON 檔／CLI／伺服器使用的 **`AC_*` 動作指令**，
以及 **GUI 分頁**。沒有任何功能只存在於 GUI。

**[English](../README.md)** · **[简体中文](README_zh-CN.md)**

---

## 為什麼選擇 AutoControl

- **一套 API，七個平台。** `wrapper/platform_wrapper.py` 在匯入時挑選後端；同一份腳本在
  Windows、macOS、X11 與 Wayland 上都不需要改寫。
- **不寫 Python 也能腳本化。** 855 個 `AC_*` 指令涵蓋全部功能，因此一個 JSON 檔能做到函式庫
  能做的任何事——包含迴圈、分支、try/catch、巨集與變數。
- **預設無頭執行。** `import je_auto_control` 絕不會載入 Qt。GUI 是選用套件，包在同一個無頭核心之外。
- **四種定位方式。** 樣板比對、OCR、無障礙樹、視覺語言模型——可透過錨點定位器與自癒後備串接組合。
- **相依基線輕薄。** REST 伺服器、JSON Schema 驗證、JWT、TOTP、WebSocket 框架、ACME 用戶端、
  USB/IP 協定與 Prometheus 指標全部以標準庫實作；較重的相依都是選用。


## AI Agent 與 Computer Use

**AutoControl 是開源、跨平台的 computer-use 與 GUI 自動化框架。**

當 AI agent 需要操作真實桌面、原生應用程式、真正的瀏覽器視窗、遠端桌面或行動裝置，而不只是操作瀏覽器 DOM/API 時，使用 AutoControl。

### 何時選擇 AutoControl

- 真實滑鼠與鍵盤輸入
- 螢幕擷取與座標操作
- OCR 與原生無障礙樹
- 影像／樣板比對
- Vision-Language Model UI 定位
- Anchor 與 self-healing locator
- 跨平台桌面／行動裝置自動化
- JSON 動作檔
- MCP computer use

建議的 agent loop：

**observe → identify → act → wait → verify → recover**

完整的 [AI Agent 指南](../AI.md) 提供 MCP 設定、工具選擇、OpenAI 整合、安全性與 computer-use 關鍵字。

### AI-friendly MCP

```bash
pip install je_auto_control
je_auto_control_mcp
```

MCP 提供完整的 `ac_*` 工具，以及 `click`、`type`、`screenshot`、`find_text`、`click_text`、`drag`、`focus_window`、`wait_image` 等短名稱 alias。

只做檢查：

```bash
je_auto_control_mcp --read-only
```

只需要 canonical `ac_*` 名稱：

```bash
JE_AUTOCONTROL_MCP_ALIASES=0 je_auto_control_mcp
```

OpenAI agent 請使用 `export_openai_tools(only=[...])` 提供聚焦工具集，不要一次提供整個 AutoControl 命令目錄。

### 專案識別

**專案：** AutoControl  
**Repository：** `Integration-Automation/AutoControlGUI`  
**Python package / PyPI：** `je_auto_control`  
**MCP command：** `je_auto_control_mcp`


---


## 如何選擇自動化層

AutoControl 不需要取代所有自動化工具；應該選擇最符合介面的那一層：

| 需求 | 適合工具 |
|---|---|
| 穩定的瀏覽器 DOM／API 自動化 | Playwright／Selenium |
| 簡單的 Python 滑鼠鍵盤腳本 | PyAutoGUI 或 AutoControl |
| 原生桌面應用程式自動化 | **AutoControl** |
| 無障礙樹 GUI 自動化 | **AutoControl** |
| OCR GUI 自動化 | **AutoControl** |
| 截圖／視覺模型 GUI 定位 | **AutoControl** |
| Self-healing 跨平台 GUI locator | **AutoControl** |
| AI agent 操作真實桌面 | **AutoControl + MCP** |
| 確定性的 JSON GUI workflow | **AutoControl** |

AutoControl 的差異在於把 **真實電腦輸入 + 語意／視覺定位 + self-healing + agent/MCP 整合** 放在同一個跨平台自動化介面。


## 安裝

```bash
pip install je_auto_control            # 核心
pip install je_auto_control[gui]       # 加上 PySide6 桌面應用程式
```

需要時才安裝的選用套件：

| Extra | 啟用的功能 |
|---|---|
| `gui` | PySide6 桌面應用程式（50 個分頁）：左側可搜尋的導覽面板（`Ctrl+K`）依分類列出全部功能，分頁在第一次開啟時才建立，**View → Theme** 切換深色／淺色。窄視窗的內容可捲動；關閉視窗時，主題、字級、導覽面板顯示（`Ctrl+B`）與寬度會存入 `~/.je_auto_control/gui.ini`。主題直接使用 Qt，不需要 `qt-material`。 |
| `webrtc` | WebRTC 遠端桌面、USB 直通（`aiortc`、`av`） |
| `signaling` | 獨立的訊令／rendezvous 伺服器（`fastapi`、`uvicorn`） |
| `discovery` | mDNS / Zeroconf 區網主機探索 |
| `pdf` / `office` | PDF 與 Excel／Word／PowerPoint 讀取 |
| `fuzzy` / `locale` | `rapidfuzz` 模糊比對、`babel` 地區解析 |
| `s3` / `audio` | S3 產出物儲存、系統音量控制 |

以分頁關閉鈕關閉 factory 建立的功能面板時，下一次 Qt event loop 會釋放 widget、訂閱與計時器；重新開啟會建立新面板。**View → Tabs** 與嵌入用的 `hide_tab` 只隱藏並保留狀態。`tab_registry.open/close` 與 `close_tab` 提供明確的生命週期介面。既有的擁有者表單與 Remote Desktop 在生命週期遷移完成前，關閉後仍保留以供重用。

**Windows arm64** 裝得起來也跑得起來，少的是上游在那裡發不出來的那些：
`opencv-python` 與 `cryptography` 都沒發 `win_arm64` wheel。所以 `find_image*`、
`screenshot()`（OpenCV／BGR 那一支——Pillow 截圖仍可用）、秘密金庫、動作檔加密、
ACME／TLS 與加密錄影會拋出指名缺哪個 wheel 的錯誤，而不是難以追查的失敗。
滑鼠、鍵盤、螢幕尺寸、視窗管理、無障礙樹、動作執行器、MCP／REST／TCP 伺服器
與 GUI 都正常——這是實測的，不是推論的。其他平台不受影響。

**系統需求：** Python ≥ 3.10（Windows arm64≥ 3.11，CPython 官方建置從那裡開始）。
Linux 請先安裝建置前置套件：

```bash
sudo apt-get install cmake libssl-dev
```

OCR、VLM 與 LLM 後端（`pytesseract`、`easyocr`、`paddleocr`、`anthropic`、`openai`）
都是按需載入——只裝你實際會用到的。Tesseract 的部分，`find_tesseract_cmd()` 找出執行檔
（依序是 `$TESSERACT_CMD`、`PATH`、安裝程式的預設資料夾），`set_tessdata_dir()` 把它指到
語言資料夾，`ocr_status()`／`ocr_languages()` 在第一次 OCR 之前就說出缺了什麼。

**記錄檔：** 函式庫寫到 `~/.je_auto_control/logs/AutoControlGUI.log`，第一筆記錄時
才建立（只 import 不會寫任何檔），同一個帳號的所有行程共用（附加寫入、每行帶行程 ID，
超過 10 MB 就改名成 `.1`）。要寫到別處就設定
`JE_AUTOCONTROL_LOG_FILE`，設成 `os.devnull` 則不寫檔。

---

## 60 秒上手

**1. 當成 Python 函式庫**

```python
import je_auto_control as ac

ac.set_mouse_position(500, 300)
ac.click_mouse("mouse_left")
ac.write("Hello World")
ac.hotkey(["ctrl_l", "s"])

x, y = ac.locate_image_center("save_button.png", detect_threshold=0.9)
ac.click_text("Submit")                       # OCR
ac.click_accessibility_element(name="OK")     # 無障礙樹
ac.click_by_description("the green Submit button")   # 視覺模型
ac.screenshot("shot.png", screen_region=[0, 0, 800, 600])
```

**2. 當成 JSON 動作檔** — `flow.json`

```json
[
    ["AC_set_var", {"name": "user", "value": "alice"}],
    ["AC_locate_and_click", {"image": "login.png", "mouse_keycode": "mouse_left"}],
    ["AC_write", {"write_string": "${user}"}],
    ["AC_retry", {"max_attempts": 3, "body": [
        ["AC_wait_text", {"target": "Welcome", "timeout": 10}]
    ]}],
    ["AC_assert_text", {"text": "Welcome"}],
    ["AC_generate_html_report", {"html_name": "report"}]
]
```

```bash
je_auto_control run flow.json --var user=bob
je_auto_control run flow.json --dry-run     # 只列出步驟，不會真的動滑鼠
```

**3. 當成桌面應用程式**

```bash
pip install je_auto_control[gui]
python -c "import je_auto_control; je_auto_control.start_autocontrol_gui()"
```

錄製一段流程、在視覺化 Script Builder 裡編輯，然後存成 CLI 能直接執行的同一種 JSON 格式。
（`python -m je_auto_control` 是舊式的動作檔執行器——`-e`、`-d`、`-c`、`--execute_str`——不會開 GUI。）

---

## 能力總覽

每一列都能無頭執行。「GUI 分頁」是同一功能在桌面應用中的位置；分頁的指令都放在視窗的
**Actions** 選單裡。

| 能力 | Python API | `AC_*` 指令 | GUI 分頁 |
|---|---|---|---|
| 滑鼠 | `click_mouse`（`clicks=2` 就是雙擊）、`set_mouse_position`、`mouse_scroll`、`tween_drag`／`drag_path`（以 `step_delay_s`、`settle_s` 控制節奏） | `AC_click_mouse`、`AC_tween_drag`、`AC_drag_path` | Auto Click |
| 鍵盤 | `write`、`write_secret`、`hotkey`、`type_keyboard`、`keyboard_key_name`（鍵碼 → 標準鍵名；Windows 也收 `ctrl`、`esc`、`enter` 等別名） | `AC_write`、`AC_write_secret`、`AC_hotkey` | Auto Click |
| 螢幕與像素 | `screenshot`、`screen_size`、`get_pixel` | `AC_screenshot` | Screenshot |
| 影像比對 | `locate_image_center`、`locate_and_click` | `AC_locate_and_click` | Image Detect |
| OCR 文字 | `click_text`、`wait_for_text`、`read_text_in_region`、`ocr_status` | `AC_click_text`、`AC_wait_text`、`AC_ocr_status` | OCR Reader |
| 無障礙樹 | `find_accessibility_element`、`click_accessibility_element` | `AC_a11y_find`、`AC_a11y_click` | Accessibility |
| 視覺模型定位 | `locate_by_description`、`click_by_description` | `AC_vlm_locate`、`AC_vlm_click` | VLM |
| 錨點定位 | — | `AC_anchor_click`、`AC_anchor_locate` | — |
| 自癒定位器 | `self_heal_run`、`self_heal_locate`、`self_heal_click` | `AC_self_heal_click` | Self-Healing |
| 自然語言規劃 | `plan_actions`、`run_from_description` | `AC_llm_plan` | LLM Planner |
| Computer-use agent | `AgentLoop`、`run_agent` | `AC_run_agent` | Computer Use |
| 錄製與重播 | `record`、`stop_record` | `AC_record`、`AC_stop_record` | Record |
| JSON 腳本 | `execute_action`、`execute_files` | 全部 855 個指令 | Script、Script Builder |
| 變數與流程控制 | `execute_action_with_vars` | `AC_set_var`、`AC_loop`、`AC_for_each`、`AC_try`、`AC_retry` | Variables |
| 資料驅動執行 | — | `AC_for_each_row`（CSV／JSON／SQLite／Excel） | Data Sources |
| 斷言 | `assert_text`、`assert_image` | `AC_assert_text` 等 21 個 | Assertions |
| 測試套件 | `run_suite` | `AC_run_suite` | Test Suites |
| 排程（間隔 + cron） | `default_scheduler` | — | Scheduler |
| 全域熱鍵 | `default_hotkey_daemon` | — | Hotkeys |
| 事件觸發 | `default_trigger_engine` | `AC_email_trigger_add` | Triggers、Webhooks、Email |
| 視窗管理 *(Windows、macOS、X11)* | `list_windows`、`focus_window` | `AC_focus_window`、`AC_snap_window` | Window Manager |
| 剪貼簿（文字 + 影像） | `get_clipboard`、`set_clipboard`、`get_clipboard_image`、`set_clipboard_image` | `AC_clipboard_get`、`AC_clipboard_set`、`AC_clipboard_get_image`、`AC_clipboard_set_image` | — |
| 遠端桌面 | `RemoteDesktopHost`、`RemoteDesktopViewer` | `AC_start_remote_host`、`AC_remote_connect` | Remote Desktop |
| USB 列舉與直通 | `list_usb_devices`、`enable_usb_passthrough` | `AC_usb_*`（16 個指令） | USB Devices、USB Share |
| 機密保險庫 | `default_secret_manager` | `AC_secret_set` + `${secrets.NAME}` | Secrets |
| 報表（HTML／JSON／XML） | `generate_html_report` | `AC_generate_html_report` | Report |
| 執行歷史 | `HistoryStore`、`manual_history_scope` | `AC_history_list`、`AC_history_capture` | Run History、Script Executor、Script Builder |
| 動作日誌 | `execute_journal_run`、`inspect_journal` | `AC_journal_capture`、`AC_journal_read` | Run History、Script Builder |
| 指標與追蹤 | `default_metric_registry`、`render_metrics_text` | — | — |
| 系統診斷 | `run_diagnostics` | `AC_diagnose` | Diagnostics |
| 測試碼產生 | `generate_code` | — | — |

自癒定位器會在後備或點擊前原樣傳遞取消。稽核記錄在寫入或回傳記錄前遮蔽本次執行已解析的秘密值；回傳的定位結果保留原值，讀取時不改寫既有紀錄檔。

即時 image／VLM 自癒現在共用一次延遲邏輯截圖及實際裁切原點，兩條路徑的 `screen_region` 均為 `[左, 上, 右, 下]`。Schema-v2 記錄增加 run／step 身份、內容與設定版本、frame hash、策略／截圖耗時及實際 backend／model，仍相容舊記錄。未設定驗證的點擊僅記錄已送出或失敗，驗證維持未知。GUI 提供區域輸入與所選記錄證據，Script Builder 保留結構化區域 JSON。舊 `healed`／`heal_rate` 統計定位候選，獨立的操作指標需要明確驗證。

實驗性 `self_heal_run(SelfHealRequest(...))` 預設只定位。明確選擇 `operation="click"`，再透過 `VerificationRequest(verifier=...)`（Python bool callback）或 `VerificationRequest(description=...)`（已設定的 VLM）於輸入送出後驗證條件。VLM 驗證使用新擷取的邏輯影像，可能產生 API 費用。`verified` 分為真、假及未知；`found` 與 `issued` 本身不代表操作通過驗證。例外與取消原樣傳遞，不重試點擊。`AC_self_heal_run` 和 MCP `ac_self_heal_run` 接受巢狀 `request`；明確驗證失敗使指令／CLI 失敗，或回傳含結構化結果的 MCP `isError`。GUI **Self-Healing** 提供選填的操作後條件，Script Builder 可編輯 JSON 請求。獨立 VLM 擷取也改用相同的記憶體邏輯原點／Retina 正規化。Framework assertion 會中止定位後備。

已擷取的自癒紀錄新增可選的 `journal_path`，搭配 run／step ID。實驗性 `inspect_heal_source(path, run_id, step_id)`、`AC_self_heal_source` 與 MCP `ac_self_heal_source` 只讀取原始步驟經清理的生命週期快照。在 **Self-Healing** 選取紀錄後，使用 **動作 → 檢視原始步驟** 開啟背景讀取器；切換目標時會等待舊讀取停止並保留請求者脈絡，關閉則取消待處理工作；Run History 讀取器也可選填步驟 ID。先篩選 run／step 再套用輸出上限，整份日誌仍會驗證，進度通知前後重查路徑根目錄，取消不回傳部分結果。舊紀錄或未經動作日誌擷取的操作沒有來源連結；查閱不會重播指令。

實驗性因果同步提供 `CausalBucket`、`CausalConfigStore`、`SyncActor`、保留衝突的 entry 版本與持久化本機 `SyncOutbox`。獨立且經驗證的 `GET/PUT /config/{user_id}/causal` 第三版協定，在保存重送收據的同一個 CAS 交易內驗證裝置註冊、確認、退休／完整同步 epoch 與刪除回收。回收後保留永久的最小刪除憑證；舊版寫入不能覆蓋已升級帳號。私有 `AC_config_store_get`／`AC_config_store_commit` 與對應 MCP／Builder 命令可讀取及提交帶明確 `_actor` 的因果 JSON；純資料合併／peer 與私有 outbox 命令仍可使用。明確的 `CausalSyncClient` 與 `AC_config_causal_fetch`、`AC_config_causal_commit`、`AC_sync_outbox_flush`（含 MCP／Builder）已提供第三版 HTTP 投遞：結果不明時重送固定請求，只有明確的過期版本才在有界預算內重合併。`CausalReceipt` 在 outbox 原子確認原收據與最新完整快照；命令憑證使用即時的 `options.secret_env` 參照。`CausalSyncClient.control` 與私有 `AC_sync_peer_control`／`ac_sync_peer_control`／Builder Data 命令可持久化註冊、確認、回收、退休與完整重同步。`SyncControlRequest(operation_id=...)` 讓已完成 RPC 的重試保持冪等；完整重同步須明確提供 `discard_pending=True`，收到收據後才原子採用新世代並封存待送舊編輯。本機 `status` 不讀取憑證或網路。`python -m examples.causal_peer_control` 提供暫存 loopback 工作流；明確的本機資產版本可透過 `AssetManifest`、`DirectoryAssetTransport`、`build_asset_manifest`、`sync_assets` 與私有 `AC_sync_asset_manifest`／`AC_sync_assets`（MCP／Builder）操作。全部資產先暫存並通過 SHA-256／大小驗證，再一次發布完整目錄；受損快取拒絕使用，腳本保持未執行。`python -m examples.sync_assets` 只使用暫存目錄。七種實驗性 adapter 已將明確選定的腳本、locator、熱鍵、觸發器、通訊錄、JSON 設定與已保存的原生 GUI 偏好設定保存為持久化因果 profile。`SyncBindings` 將明確指定的秘密與機器值換成具名參照；`materialize_sync_profile` 發布完整且未啟用的原生格式版本。私有 `AC_sync_adapter_snapshot`、`AC_sync_adapter_apply`、`AC_sync_adapter_resolve`、`AC_sync_profile_materialize` 與對應 MCP／Builder 命令提供相同流程。`python -m examples.sync_adapters` 僅使用暫存檔。私有絕對路徑綁定接受高熵目錄名稱，仍拒絕可辨識的憑證格式。原生數值定義會在儲存前以分類錯誤拒絕超出範圍的值，包含超大 JSON 整數。`WorkspaceSettingsSyncAdapter` 僅讀取原生 GUI INI 的主題、字級、導覽顯示／寬度，並發布未啟用的 `workspace.ini`；明確複製為獨立工作檔後，才能交給新 GUI 使用。`python -m examples.sync_workspace` 不匯入 Qt。`SyncWorkspace` 已整合明確來源、持久離線捕捉、因果 HTTP、精確衝突檢視與完整重同步來源基準。私有 `AC_sync_workspace`／`ac_sync_workspace`／Builder Data 共用 status／capture／sync／review／resolve／preferences／materialize 與明確 peer 控制，全部需要 DRIVE；網路憑證使用 `options.secret_env`。`python -m examples.sync_workspace_http` 以兩組暫存來源與 loopback 示範衝突解決、重啟及退休編輯不重播。接收資料保持未啟用。引用資產傳輸見下方；明確的原生工作副本載入見下方，`ConfigSyncClient` 保留時間戳合併。參閱[因果／outbox 指南](../docs/source/Zh/doc/causal_sync/causal_sync_doc.rst)與 `python -m examples.causal_sync`。

延遲建立的 **工作區同步** 分頁透過 **Actions** 提供本機狀態／擷取、網路同步與裝置控制、精確因果檢視／解決衝突，以及完整未啟用發布。貼上明確的私人工作區設定，憑證只填環境變數名稱。同步不會自動套用收到的偏好設定。選取 `workspace`、檢視目前版本後，再執行「套用已檢視的 GUI 偏好設定」，才會更新目前視窗的主題、字級及導覽面板。`SyncWorkspace.preferences(observed=change_ids)` 與既有 AC／MCP／Builder 的 `preferences` 操作，僅在已檢視版本完全相符且無衝突時回傳四個標準值；缺少或刪除的值採安全預設。Worker 保留呼叫者 context、重驗 DRIVE 權限，支援取消並在關閉後捨棄舊結果。畫面顯示修訂版、待送／衝突／參照數與最近成功同步版本；開啟分頁不會啟動連線。

明確的原生載入使用 `load_sync_profile(directory, target_root, expected_digest=...)` 與 `LoadedSyncProfile`，並提供私有 `AC_sync_profile_load`／`ac_sync_profile_load`／Builder Data。以已發布的 `files` 資料夾及精確檢視的 manifest 摘要建立全新可編輯工作區，先驗證全部 bytes、標準原生檔案及封存 heads 一致，再原子發布。載入的熱鍵及每個觸發器節點都是停用的原生物件；定位器與通訊錄 handle 使用工作副本。型別化資產參照及原生熱鍵／觸發器路徑依工作根目錄解析，腳本字面文字保留原意，秘密維持 placeholder。在「工作區同步」發布後，資料夾／摘要欄位會填入結果；選擇工作副本存放資料夾，再執行「載入已檢視的原生 profile」。其他明確 Actions 可檢查所選原生類別、在 Builder 開啟已載入腳本快照，或套用其偏好快照。每次操作都重驗目前呼叫者與擷取擁有者的權限；開啟腳本後仍須明確執行 Run；Builder 將匯入的命令名稱與位置參數顯示為字面文字。`python -m examples.sync_profile_load` 使用七種暫存來源與真實 PNG，不呼叫網路或裝置。

資料夾鏡像改以 SHA-256 內容比對，不再依賴修改時間遞增：只改時間不重送，時間相同或較舊的內容修改仍會送出。FolderSyncEngine 重啟時保留待送與離線修改，逐檔檢查停止要求，並持續擁有尚未結束的傳送工作。傳輸擁有者可在發布檔案後明確呼叫 record_received(path)，避免回送收到的內容。原生 GUI 的固定內容收據處理見下文。

檔案傳送現在會等待每個 DataChannel callback，將緩衝資料限制在 1 MiB，並將通道失敗回報給呼叫端。可選的 `cancelled` 判斷會停止排隊寫入；宣告的位元組數可偵測來源截短或增長。原生資料夾工作綁定授權、引擎、viewer 與 peer connection，擁有權變更時停止。收件匣下載移至事件迴圈之外，透過每個通道最多 32 筆請求的佇列依序傳送。預設手動模式接受資料不代表遠端發布完成；確認模式見下文。GUI 重連交接見下文。

原生檔案接收器現在會在關閉、檔案／控制通道關閉、連線進入終止狀態、更換通道或撤銷檔案權限時清除未完成內容。已關閉的接收器拒絕延遲資料；具體 peer／通道與授權檢查會保護替換後的傳輸，也會拒絕 viewer 在驗證前接收檔案。狀態清理先於使用者 callback，避免舊失敗影響 callback 建立的新連線。檔案／稽核／狀態 callback 保留原始取消及強制中斷物件。清理會嘗試關檔及刪除暫存檔，檔案系統失敗寫入日誌。既有 Remote Desktop 控制自動使用此生命週期；已完成的目標與原有線上格式仍可使用。

本機 `FileReceiveReceipt(path, sha256, size)` 現在會在原子發布後固定原始接收內容。`FileTransferReceiver.handle_message(on_receipt=...)` 與原生 host／viewer 的 `set_file_receipt_callback()` 提供收據，不必重讀已發布檔案。`FolderSyncEngine.record_receipt()` 避免回送並保留後續本機修改；既有 `record_received(path)` 則明確快照當前內容。GUI 資料夾開關綁定接收收據的引擎及 viewer，並在存取監看目錄前重新驗證原始授權。相對收件匣／監看路徑綁定建立時的工作目錄，既有路徑通知使用絕對路徑。這些本機收據供下文的原生確認模式使用；GUI 重連交接見下文。

原生 `FileTransferSender.send`、viewer 的 `send_file` 與 host 的 `push_file` 現在接受僅限關鍵字的 `require_commit=True`。確認模式會先探測已驗證的原生對端，再讀來源中繼資料／內容；以第二版 begin／end 中繼資料傳送，並在原子發布後核對傳輸 ID、不可預測的結束 nonce、SHA-256 及位元組數。相對來源路徑會在交換前固定。每個檔案都重新確認支援與權限，等待有時限；取消、通道／事件迴圈替換或撤銷權限都保留失敗狀態。GUI 資料夾傳送一律要求此模式，因此只接受但遺失的資料不會推進投遞狀態；不確定的傳送會由同一引擎重試。手動傳送仍預設使用原有線上格式。GUI 資料夾投遞要求兩端都支援確認傳輸；不支援時會在送出檔案內容前失敗。GUI 明確重連／恢復見下文。

GUI 重連時會為每個面板保留一份記憶體內的資料夾基準。重新連線後再按開始同步：相同的已驗證 host 指紋、絕對監控路徑與本機使用者，會透過新授權的 sender 接續失敗／離線修改。缺少或更換 host 指紋、路徑或使用者時建立新基準；舊工作仍在執行時拒絕交接，待它退出後才能重試。明確關閉資料夾同步會重設基準；停止／重連 viewer 則保留，關閉應用程式後清除。指紋沿用既有已驗證 host 中繼資料的信任模型，沒有新增密碼學身份保證。SDK 可先停止 FolderSyncEngine，待工作確實退出後匯出 checkpoint()，將不可變的 FolderSyncCheckpoint 傳給路徑／遞迴設定相同且 sender 已明確授權的新引擎。基準包含初始略過檔案與收到的內容，並非遠端確認清單。

TCP／WebSocket 剪貼簿傳輸沿用明確的 SDK 呼叫與 GUI 推送剪貼簿按鈕。收到的文字／圖片不會自動傳回或廣播；使用者仍可明確重複傳送相同內容。Viewer／host 在讀到緩衝訊息後，會重新檢查原始連線、驗證及完整控制權限，再套用剪貼簿資料。Viewer 會在編碼前固定原通道，拒絕改送至替換後的連線。GUI 排隊中的傳輸保留具體 viewer 與連線發起使用者，寫入本機剪貼簿、明確讀取及送出前都會重新檢查權限與擁有權。過期或撤銷的工作會被略過或回報權限錯誤；一般 provider／callback 錯誤仍受控，原始取消與強制中斷物件繼續傳播。文字／圖片 JSON 格式及既有 API 不變。Callback 註冊只以弱引用綁定一次原始 viewer，避免斷線 viewer 自己保留自己及 Qt 面板直到循環垃圾回收；實際排隊資料仍保留原始 peer 與權限，直到處理或丟棄。受控本機協定、loopback 與 offscreen 測試替換原生剪貼簿 provider；真機與付費 API 驗收仍暫緩。

實驗性引用資產使用 `SyncAssetBlob`、`SyncAssetReference`、`SyncAssetStore` 與 `SyncAssetHTTPClient`。明確的 `SyncBindings.assets` 別名將選定檔案封存為不可變 SHA-256 參照；只改資產也會建立新的因果版本。`SyncWorkspace` 在準備新定義請求前上傳已驗證分塊，支援中斷續傳，並在完整且未啟用的發布前下載引用內容。既有私有 AC／MCP／Builder 工作區／profile 命令共用這些欄位。`asset_cache_path` 選取 client cache；signaling 的 `--asset-store`／`AUTOCONTROL_SYNC_ASSET_STORE` 選取獨立 server 資料庫。具驗證的第一版資產路由使用 256-KiB 分塊、每檔 64 MiB 上限，每帳號預設限制 256 MiB、8,192 塊與 4,096 筆 blob 收據。超過配額會明確失敗；不可變歷史不自動回收。原生輸出路徑相對於 generation 根目錄。`python -m examples.sync_referenced_assets` 經暫存 loopback HTTP 傳送真實 PNG 與腳本，不執行腳本或改目前工作區。

實驗性持久化設定使用 `ConfigStore.commit(..., base_revision=..., operation_id=...)` 與第二版 signaling PUT envelope。SQLite 交易讓 bucket 與重送收據在重啟後保留；過期版本或 ID 改配其他內容會衝突。`ConfigSyncClient` 預設條件寫入；舊版盲寫須在 client／server 明確開啟。`--config-store` 選取延後開啟的資料庫。私有 `AC_config_store_get`／`AC_config_store_commit` 與對應 MCP 工具共用 Script Builder 的明確 Data 命令。只儲存資料，不執行腳本或啟用觸發器；因果合併與離線 outbox 另行交付。參閱[持久化設定指南](../docs/source/Zh/doc/config_store/config_store_doc.rst)與 `python -m examples.config_store`。

實驗性日誌產碼候選支援 `generate_candidate_from_log(path, run_id=...)`、`AC_generate_candidate_from_log` 與 MCP `ac_generate_candidate_from_log`。它會整合開始／完成快照，保留已記錄的控制來源與重試證據，並將不完整重建標示為已觀察路徑。失敗／未完成呼叫、未知命令及遮罩輸入均列為排除項目，不捏造平行順序。Python／pytest／Robot 產物經靜態、命令及不發送輸入的乾跑檢查。`codegen --from-log run.jsonl --run-id selected` 輸出 JSON 審閱包；`-o review.zip` 或 `write_candidate_archive` 可將程式、動作與來源資訊一起原子匯出。Recording Editor 與 Script Builder 的 **動作 → 審閱日誌候選腳本** 提供程式／差異／來源／警告；Builder 匯入為獨立操作，拒絕覆蓋審閱期間的編輯變更。產生與匯入均不執行候選。參閱[候選指南](../docs/source/Zh/doc/journal_candidates/journal_candidates_doc.rst)與 `python -m examples.journal_candidates`。

實驗性候選樣板版本提供 `create_template_candidate`、`preview_template_candidate`、`verify_template_candidate`、`accept_template_candidate`、`revert_template_candidate`，以及對應 `AC_template_candidate_*`／`ac_template_candidate_*` 操作。新的不可變 JSON 版本包保存原始位元組及依目標 PNG／JPEG／BMP 格式編碼的候選；預覽回傳有界縮圖。驗證在本機資料集比較兩個固定版本；接受須有已標註命中、期望 miss、全部已標註案例正確，並提供已預覽版本的 SHA-256。接受時重驗資料集，只原子替換仍符合的原始內容；回復精確還原原始位元組，拒絕覆蓋後續修改。未知樣本與原生操作結果分開呈現。驗證使用記錄的門檻；啟用影像不修改腳本門檻。**Self-Healing → 候選樣板** 提供五個動作、背景工作、取消與 JSON 證據。執行 `python -m examples.template_candidates` 可跑只使用暫存檔的範例。

實驗性固定影像比較支援 `evaluate_locators`、`evaluate_healing_manifest`、`AC_self_heal_evaluate`、MCP `ac_self_heal_evaluate` 與 **Self-Healing → 版本比較**。報告分別呈現已標註正確率、誤判、未知與已驗證恢復，包含 p50／p95 及來源，可由 `write_healing_report` 或 GUI 動作匯出 JSON／HTML。本機資料集入口不會截圖、點擊或自行選擇網路 backend。參閱[資料集、統計母體與限制](../benchmarks/self_healing/README.md)。

除了這張表，`utils/` 底下還有 311 個無頭套件，涵蓋斷言、韌性、資料品質、i18n 稽核、遮蔽、
治理、可觀測性等等。完整的逐模組地圖在 **[architecture_explore.md](../architecture_explore.md)**。

---

實驗性的結構化日誌已從 `je_auto_control` 匯出（也可透過 `utils.action_journal` 使用）：`journal_scope` 記錄現有 executor 呼叫，`execute_action_with_journal` 隔離一次執行。本機 loop／parallel／DAG 步驟保留 parent ID，並區分失敗、取消與 dry-run。既有 history 擁有者會自動連結明確擷取，包含本機 parallel／DAG worker 開啟的 journal；`HistoryStore.journals_for_run` 可查詢非擁有式連結，清理 history 不會刪除日誌檔。CLI 支援 `run script.json --journal run.jsonl [--journal-run-id ID]` 與 `journal run.jsonl [--run-id ID] [--limit 100]`。查閱會按附加順序顯示遮罩後的生命週期快照，預設最多 100 筆，上限 10,000 筆。`AC_journal_capture` 接受具名參數，在擁有者 executor 上執行巢狀 `body`，保留原變數範圍；`AC_journal_read` 與 CLI、公開的 `inspect_journal` 共用遮罩後的有界查閱。兩個指令皆可在 Script Builder 編輯。擷取會在 history 連結、開檔及動作執行前拒絕含有當次執行已知秘密的識別碼或目的地。MCP 的 `ac_journal_capture` 與 `ac_journal_read` 提供結構化結果、進度與合作式取消。擷取的日誌根目錄限制與 observer 會保留至巢狀擷取及本機 workers；查閱可在逐筆驗證時取消。Python 可透過 `JournalRunOptions` 與 `execute_journal_run` 使用相同控制。

手動執行可透過 `manual_history_scope`、`AC_history_capture`、CLI 的 `run --history [--history-db PATH]`，或 Script Executor／Script Builder 的 **記錄至執行歷史** 選用紀錄。GUI 的選填日誌路徑也能獨立使用；GUI／CLI 保留原本的結果 JSON 與變數範圍，指令則回傳 `history_id`、`record`、`failed_actions`。既有與巢狀擷取都會連結到新的手動歷史列。CLI 預覽以 `cli.preview` 標示，一般執行使用 `cli.run`。

Run History 提供唯讀日誌檢視。使用 **操作 → 使用所選執行的日誌** 選擇來源連結，或用 **選擇日誌** 指定外部檔案；設定執行 ID 與快照上限後，使用 **讀取日誌**。起始／完成快照保持分離，選取後會顯示完整的遮罩資料。**取消讀取日誌** 與關閉檢視會在逐筆邊界提出取消要求；檔案解析在背景 worker 執行，單純選取連結不會開檔。

`${secrets.NAME}` 解析後的值會在 executor 執行期間的應用程式診斷中遮罩，包含巢狀動作及本機 parallel／DAG。CLI／REST／MCP 請求與排程、trigger、hotkey、email 執行會將遮罩保留到錯誤處理及 audit／history 寫入完成；報表紀錄保存遮罩後的快照。DAG 會將擁有者的遮罩保留到 node 診斷完成，包含獨立呼叫與自訂 local runner。watchdog、observer 與 callback executor 會將遮罩保留到最後的錯誤處理；獨立規則彼此隔離。CLI stderr 會遮罩，API 結果、拋出的例外與 CLI 結果資料保留原始值。遮罩於擁有者的請求或執行結束時清除。中止的 history 記為 `error`，journal 步驟維持 `cancelled`，不再擷取錯誤截圖。取消會穿過非嚴格執行、復原／重試、回呼與本機 worker；history 結算失敗也不會取代原始硬中止訊號。

## 命令列介面

每次 `je_auto_control run`（包括 `--dry-run` 與未帶 `--var`）使用獨立變數範圍。頂層 `run_from_description` 與 `StateMachine.run()` 也會隔離變數，同一次執行內的動作與狀態仍可共享；巢狀呼叫沿用已有的執行範圍。自行建立的 `Executor()` 保留自己的變數。

```bash
je_auto_control run script.json [--var name=value] [--dry-run] [--allow-package NAME]
je_auto_control validate script.json          # 別名：lint
je_auto_control fmt script.json [--check]
je_auto_control list-commands [--filter mouse] [--json]
je_auto_control record out.json [--duration 5]
je_auto_control codegen script.json --target pytest -o test_flow.py
je_auto_control failure-bundle failure.zip --error "login timed out"
je_auto_control list-jobs
je_auto_control start-server --port 9938      # TCP socket 伺服器
je_auto_control start-rest   --port 9939      # REST API
je_auto_control version
```

`--var name=value` 會盡量以 JSON 解析（`count=10` 會變成整數），否則視為字串。
`run` 只要有任何動作失敗就以 1 結束（仍會跑完整份腳本），CI 步驟會跟著失敗。舊版 `python -m je_auto_control -e file.json` 進入點仍然可用，它的 `-e`、`-d` 與 `--execute_str` 旗標也同樣在有動作失敗時以 1 結束。由 [TestPioneer](https://github.com/Integration-Automation/TestPioneer) 啟動時（它會設定 `TEST_PIONEER_ARTIFACT_DIR`），以相對名稱要求的 HTML、JSON、XML 報告會寫到該目錄底下。

---

## 伺服器與整合

| 介面 | 啟動方式 | 說明 |
|---|---|---|
| **MCP 伺服器** | `je_auto_control_mcp`（stdio）或 `AC_start_mcp_http_server` | 759 個工具，供 Claude Desktop／Claude Code／自訂 tool loop 使用：完整的 `ac_*` 工具介面，以及常用 GUI 操作的短名稱 alias。除了以 `initialize` 握手的各版協定，也支援無狀態的 MCP 2026-07-28。Bearer 驗證、TLS、稽核記錄、限流、外掛熱重載、CI 假後端。 |
| **REST API** | `je_auto_control start-rest` | Bearer token、逐 IP 限流與鎖定、SQLite 稽核 hook、`/metrics`、`/openapi.json`、`/docs` Swagger UI、`/dashboard`。 |
| **TCP socket 伺服器** | `je_auto_control start-server` | 以換行分隔的 JSON 動作清單。預設綁 `127.0.0.1`。 |
| **pytest 外掛** | 安裝後自動生效 | 提供 fixture 與供 pytest-bdd／behave 使用的 Gherkin step library。 |
| **語言伺服器** | `python -m autocontrol_lsp.server` | 為 `AC_*` 動作 JSON 提供補全與診斷，指令清單直接取自執行期的指令表。 |
| **遠端桌面** | `RemoteDesktopHost` 或 GUI | TCP、WebSocket 或 WebRTC；TOTP、信任清單、TURN 設定、檔案／剪貼簿／音訊同步。 |

除非明確指定，所有伺服器都綁在 `127.0.0.1`。

MCP 視窗狀態工具 `ac_window_minimize`、`ac_window_maximize` 與 `ac_window_restore` 在後端接受要求時回傳視窗 handle，遭拒時回覆 `isError: true`（包括 handle 失效或啟用請求被拒）。Win32 原始 `ShowWindow` 的先前可見性由後端正規化處理。

**套件閘門。** `AC_add_package_to_executor` 與 `AC_add_package_to_callback_executor` 會匯入 Python 套件並把成員註冊成命令，所以從上面任何一個入口送來的動作清單都可能載入 `os` 或 `subprocess`。沒有被放行的套件不會載入：不在允許清單上的套件在匯入前就被拒絕，該動作以 `AutoControlExecuteActionException` 失敗。放行套件（含子模組）的方式：在 Python 裡呼叫 `executor.allow_packages("name", …)`；對所有入口——兩個 CLI、socket／REST／MCP 伺服器與排程器——設定環境變數 `JE_AUTOCONTROL_ALLOWED_PACKAGES`（以逗號分隔的名稱，行程啟動時讀取）；或只對一次 CLI 執行使用 `je_auto_control run script.json --allow-package NAME`（可重複）。`executor.set_allow_arbitrary_packages(True)` 會對所有套件打開閘門，也就是先前版本的預設行為（當時會發 `DeprecationWarning`）。這些都不是 `AC_*` 命令，所以動作清單不能自己打開閘門。

**選用的強化設定。** 下列各項在設定之前都是關閉的，沒設定的伺服器行為與先前相同。`JE_AUTOCONTROL_RBAC_USERS=<使用者檔>` 讓 REST API 與 MCP HTTP 傳輸把 bearer token 對到使用者，並依角色（viewer／operator／admin）授權每一個路由、工具與特權 `AC_*` 命令；此時共用 token 會被拒絕。`JE_AUTOCONTROL_MCP_PATH_ROOTS`（以作業系統的路徑分隔字元分開的目錄）把每一個屬於檔案路徑的 MCP 工具參數限制在這些目錄裡，`JE_AUTOCONTROL_MCP_PATH_ROOTS_FROM_CLIENT=1` 再加上 client 的 `roots/list`，`JE_AUTOCONTROL_MCP_ENV_REF_ALLOW` 限制 `ac_resolve_ref` 可以讀哪些 `env://` 名稱。`JE_AUTOCONTROL_ACTION_SIGNING_PUBLIC_KEY` 讓端點只能驗證 Ed25519 簽章的動作檔而不能簽章（`create_signing_keypair`；私鑰留在簽章的機器上）。遠端桌面的 viewer 只把 host 推來的檔案寫在 `~/Downloads/AutoControl` 底下（`JE_AUTOCONTROL_REMOTE_DOWNLOAD_DIR`）；這一項預設就是開的。

REST GUI 在使用者存放檔啟用時顯示 RBAC 模式並停用共用 token 欄位。`rest_api_registry.status()` 提供 `rbac_enabled`，該模式的 `token` 為 `null`；請使用個別使用者 token。只實作 `check()` 的自製 REST gate 仍可用於共用 token 模式；RBAC 要求已驗證的使用者 context，會拒絕沒有身分的成功結果。

RBAC viewer 不會取得列管的敏感讀取工具，即使 MCP `readOnlyHint` 為 true：剪貼簿／歷史、本機文件／資料／SQL 與 dotenv 讀取、參照解析、認證資料產生、持久存放區讀取、對外檢查、麥克風擷取與外部 VLM 請求都需要 operator／admin。斷言容器的 spec 也可能讀取這些資源，因此同樣需要 operator。螢幕觀察與純輸入解析維持既有分類。`ac_realize_item`、`ac_idempotency_begin` 與 `ac_rate_limit` 會改變狀態，已從 `--read-only` 模式排除。

間隔／cron 排程、觸發器、熱鍵、watchdog 規則、webhook、e-mail 觸發器與 observer 回呼會保留註冊者身分。每次觸發重新檢查來源使用者檔與角色；已刪除的使用者、無法使用的來源檔與 viewer 不能執行背景工作。啟動 daemon 不會改變既有工作的擁有者。擁有者資訊不保存 RBAC bearer token；未帶 `store_path` 的明確 Python `AuthorizationContext` 保留角色快照，未在 RBAC 下註冊的工作會清除 worker 原有身分。observer／watchdog 回呼使用獨立變數範圍，watchdog 動作失敗不會算成成功排除彈窗。巢狀回呼會保留呼叫端的失敗計數；webhook 擁有者被撤銷權限時回應 HTTP 403 與 `fired: false`。

### 遠端桌面的線路協定

TCP host 在送出 `AUTH_FAIL` 前就釋放認證失敗的 client 名額。Viewer 即使因錯誤 token、錯誤握手訊息或拒絕核准而失敗，也能立即重試，不必等 socket 清理或日誌完成；待處理握手仍有獨立的資源上限。

把主機開出去之前值得先知道，而且這段在其他文件裡都沒有寫。預設傳輸是**裸 TCP
上的長度前綴分幀**（不需要額外相依），連線一開始就是 **HMAC-SHA256 的
challenge／response 握手**：驗證沒過的觀看端在拿到任何一張畫面之前就會被斷掉。
JPEG 影格依設定的 FPS 與品質編碼，再透過一個共用的**最新影格槽**發給已驗證的
觀看端——所以慢的觀看端是**掉影格**，不會把其他人一起卡住。觀看端送來的輸入是
JSON，會先比對**動作允許清單**才交給既有的輸入包裝層執行，觀看端無法自己發明
新的操作。

```python
# 讓別人連進來——開一個主機，把 token 與 port 給對方
from je_auto_control import RemoteDesktopHost
host = RemoteDesktopHost(token="hunter2", bind="127.0.0.1",
                         port=0, fps=10, quality=70)
host.start()
print("listening on", host.port, "viewers:", host.connected_clients)
```

```python
# 控制另一台機器——連上去並送輸入
from je_auto_control import RemoteDesktopViewer
viewer = RemoteDesktopViewer(host="10.0.0.5", port=51234, token="hunter2",
                             on_frame=lambda jpeg: ...)
viewer.connect()
viewer.send_input({"action": "mouse_move", "x": 100, "y": 200})
viewer.disconnect()
```

也可以用 IP 允許清單（CIDR 網段或個別位址）限制誰連得進來，清單外的對端在握手
階段就會被拒絕：

```python
RemoteDesktopHost(token="tok", ip_allowlist=["10.0.0.0/8", "192.168.1.100"])
```

---

## 平台支援

| 平台 | 後端 | 輸入 | 螢幕擷取 | 錄製 | 視窗管理 |
|---|---|:---:|:---:|:---:|:---:|
| Windows 10 / 11 | Win32 ctypes（可選 Interception 驅動） | ✅ | ✅ | ✅ | ✅ |
| macOS 10.15+ | pyobjc / Quartz | ✅ | ✅ | ✅¹ | ✅ |
| Linux X11 | python-Xlib（可選 `uinput`） | ✅ | ✅ | ✅ | ✅ |
| Linux Wayland | 經桌面 portal 的 libei，或 ydotool／wtype ＋ 擷取工具 | ✅ | ✅ | ❌ | ❌ |
| FreeBSD／OpenBSD／NetBSD | python-Xlib，與 Linux 同一套 X11 後端 | ✅² | ⚠️² | ✅² | ✅² |
| Android | adb + uiautomator2 | ✅ | ✅ | — | — |
| iOS | WebDriverAgent / facebook-wda | ✅ | ✅ | — | — |

¹ macOS 的錄製走 Quartz event tap，需要**輔助使用**權限
（系統設定 → 隱私權與安全性 → 輔助使用）。沒有授權時會直接拋出並指名
缺的是哪個權限，而不是安靜地錄到一個空的 session。

² BSD 直接跑同一套 X11 後端——同一個 X server、同一個 `python-Xlib`，而輸入、
錄製與視窗管理就只相依這一個套件。`freebsd` CI job 在真的 FreeBSD 14 上驅動真的
輸入，再從 X server 讀回來；OpenBSD 與 NetBSD 走同一條程式路徑，只是沒有 CI
runner。唯一的例外是螢幕擷取，而卡的是打包不是平台：它走 Pillow／mss 與 OpenCV，
而 `opencv-python`、`pillow`、`cryptography` 都沒有發 FreeBSD wheel。從 ports
建起來之後，擷取、影像比對、OCR 與動作加密也都能用——`import je_auto_control`
本身已經不需要它們任何一個。

Wayland 的按鍵、按鈕與指標輸入在 `auto` 模式下，僅於選用原生後端缺席時改用 CLI。
portal 請求開始後，拒絕、逾時、握手失敗、裝置暫停或權限撤銷都會停止輸入，
不會自動切換提供者；重複呼叫保留不含原生資源的失敗狀態，不重開同意對話框。
`JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=libei` 強制原生輸入，`=cli` 明確選擇 CLI。
解決權限問題後，可明確呼叫 `je_auto_control.linux_wayland.libei.reset_default_backend()`
以允許重新請求。原生組合鍵中斷時會在同一後端嘗試釋放所有已按下的按鍵，並保留原始取消。
此行為不改變明確的 wtype 文字輸入路徑或螢幕擷取選擇。

`ydotool` 退路需要
**ydotool 1.0 以上**。AutoControl 送的每一個參數都是那一版才有的；0.1.x
（Debian bookworm 與目前所有 Ubuntu 仍以這個名字提供，Debian trixie 則根本沒有）
對同一批參數回傳 0 卻不送出任何事件。AutoControl 會偵測並直接拒絕，
而不是為根本沒送出的輸入回報成功。Arch、Fedora 與 Debian unstable 提供的是 1.0。

這條退路要能**準確定位**，還有一個前提:合成器的指標加速度必須是關的。
`ydotool mousemove --absolute` 並不送任何絕對事件——它先把游標推到合成器夾取的
那個角落，再送相對位移，所以這段位移會被合成器加速。對真的 wlroots session 量到的是:
libinput 的預設 profile 讓游標走的距離正好是要求的兩倍。ydotool 自己的 `--help`
也是這樣寫的；AutoControl 每個行程會記一次警告，而不是安靜地把點擊放到錯的地方。
請對 ydotoold 的裝置關掉加速度（sway:`input type:pointer accel_profile flat`
加上 `pointer_accel 0`），或是裝上 `liboeffis`，改走協定層本來就是絕對座標的 libei。

倍率是合成器自己的設定，用戶端讀不回來，所以只有你知道它關了沒有：
`JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL=flat` 表示已經關掉，移動就不再出聲；
`=strict` 則寧可拒絕這次移動，也不讓點擊落在別的地方；不設定就維持
「警告一次後照樣移動」的預設。

Wayland 的螢幕擷取需要合成器對應的工具，因為沒有單一工具能涵蓋全部：wlroots 系
（sway、Hyprland、river）用 `grim`，GNOME 用 `gnome-screenshot`，KDE 用 `spectacle`。
裝好其中一個之後，所有擷取路徑——截圖、影像與錨點定位、OCR、螢幕錄影、遠端桌面——都會
經由它。三個都沒裝時，內建 D-Bus client 會透過 session bus 嘗試 `xdg-desktop-portal`，第一次可能會跳
同意對話框。再不行，擷取會帶著安裝提示明確失敗，而不是回傳空白的 XWayland root；
`je_auto_control.api.run_diagnostics()`（以及 GUI 的 Diagnostics 分頁）的 `screen_capture`
檢查會回報目前使用哪一層。

原生 Wayland 指標座標在原始座標與版面原點換算後仍不屬於任何授權 EIS 區域時，
會以 `state="failed"` 的 `LibeiUnavailable` 拒絕，停止自動 CLI 備援，
不送出移動、frame 或後續點擊。有效座標、未提供區域的裝置、同一 sender 的後續有效請求，
以及明確選擇 CLI 的既有行為維持不變。

**輸入／擷取能力**提供 `je_auto_control.api`（亦由套件根目錄匯出）的
`BackendContext`、`CapabilityStatus`、`CapabilitySnapshot` 與 `probe_capabilities`。
呼叫 `probe_capabilities(BackendContext.current()).to_dict()`、無參數的
`AC_probe_capabilities`／唯讀 `ac_probe_capabilities`，或選擇
**Diagnostics → Actions → 檢視輸入與擷取能力**；Builder 提供相同無參數指令。
`python -m examples.capabilities` 顯示本機前置條件與確定性的 XWayland 範圍範例，不操作桌面。

輸入項描述按鍵／指標事件；既有 wtype 文字路徑獨立。探測只讀環境、PATH 與不等待鎖的既有原生狀態，
不載入選用原生函式庫、不連線、不讀取事件、不擷取或要求授權。找到工具或 bus 位址只代表
`unverified`，不等於可用。快取 libei 須完成握手，且鍵盤、絕對指標、按鈕與滾輪事件種類都在運作才回報可用；
部分授權維持未驗證，事件種類暫停或必要裝置移除則回報暫停／撤銷。八種狀態為 `available`、`unverified`、`needs_permission`、
`needs_dependency`、`unsupported`、`paused`、`revoked`、`failed`。
`available` 僅是最近的本機觀測，可能過時；實際操作仍重驗權限。XWayland 一律
`desktop_wide=False`，無法涵蓋原生 Wayland 視窗；其他範圍旗標仍受授權區域限制，不代表已驗證每個螢幕。

Context 會複製環境／工具資料，可由擁有者提供無原生物件的輸入／擷取觀測，但不授予權限。
預設本機結果不含環境值、命令參數、執行檔路徑或原生錯誤文字；AC／MCP 不接受外部提供觀測。
明確選擇 CLI 與觀測到選用原生依賴缺失後的自動備援分開；拒絕、暫停、撤銷與失敗不表示改走 CLI。
擷取工具／portal 選擇獨立診斷，重繪與切換語系只使用既有快照。原生 portal 恢復、compositor 重啟、
擷取結果與 context 的接合，以及原生 session 的重試／取消／停止控制仍列於 `Progress.md`。

GUI 工作基礎提供 `gui.task_controller.TaskController`：
`submit(work, owner=widget)` 回傳呼叫者持有的 `TaskHandle`，透過
`TaskOutcome`／`TaskProgress` 傳遞終態與進度。工作取得不依賴 Qt 的
`CancellationToken`，提供 checkpoint、有界且可被取消喚醒的等待與進度回報。
提交時捕捉 context，執行前重讀 store 使用者；工作須持有資料、不引用 widget，並驗證自身操作所需的 capability。
既有 `DeferredAuthorization.scope()` 維持輸入權限要求，`context_scope()` 僅更新與綁定身分。

擁有者、handle 或 controller 銷毀時會要求協作式停止並丟棄延遲結果；每項工作有獨立 ID／token，
回呼在 GUI 執行緒執行。不強制中斷不合作的呼叫，也不把已成功提交的結果改標為取消。
錯誤與進度使用捕捉的秘密遮罩 scope，終態不保留例外 traceback；執行緒啟動失敗會回復兩層登記並保留原失敗。
Diagnostics 已接入此共用控制器；其餘面板／backend 遷移與原生 session 操作仍列於 `Progress.md`。

主動 **Diagnostics → Actions → 執行診斷** 以共用控制器在 GUI 執行緒外執行。
**停止診斷** 要求協作式停止；四語狀態區分執行中、清理中、已取消與失敗，並顯示已完成檢查數。
重複執行不另開工作，關閉後丟棄延遲進度／結果，明確重試會建立新的擁有者工作。
GUI 以不保留例外 traceback 的 typed outcome 呈現取消；核心／SDK／CLI 與 MCP handler
維持原始直接／包裝取消物件。普通檢查錯誤仍列入報告並繼續其餘項目。

兩個 SDK namespace 匯出 `CancellationToken`、`TaskProgress`、`cancellation_scope`。
使用 `with cancellation_scope(token): report = run_diagnostics()`，擁有者可由另一執行緒呼叫
`token.cancel()`；既有無參數診斷簽章不變。Scope 不授予權限，`cancellation_scope(None)`
只在有時限的自有資源清理期間暫停取消。`AC_diagnose` 與新增的唯讀 `ac_diagnose` 共用報告；
MCP 不接受參數，使用請求取消／進度，與明確 GUI 操作同樣需要 `read_screen`，拒絕外部 token／授權資料。
這些是主動檢查，擷取可能要求同意；`ac_probe_capabilities` 維持獨立的被動選項。

Scoped Wayland D-Bus 的連線／讀取／部分寫入，以至多 0.1 秒的區間輪詢，維持原本總時限。
取消時在原 bus 以獨立 0.25 秒預算嘗試 Request.Close，再釋放連線；取消的已回傳圖片會刪除。
Scoped CLI 擷取會停止並回收自己建立的 helper／process group，清理有時限，pipe close 失敗也不蓋掉原取消，
已回收的數字 PID 不再作為訊號目標。liboeffis 取得 session 時會觀察停止並釋放自身 context。
不強制中斷不合作或原生呼叫，清理期間 GUI 仍可操作；restore／重啟、原生 session 控制、
擷取擁有者 metadata 與其餘面板／backend 遷移保留於 `Progress.md`。

`python -m examples.cancellable_diagnostics` 預設只做受控取消示範，不呼叫 provider。
`--active --cancel-after 2` 才明確執行診斷並在兩秒後要求停止；真機／裝置／API 驗收另外列管。

開啟 Diagnostics 只顯示已翻譯的「尚未執行」狀態，不執行檢查。
選擇 **Actions → 執行診斷** 才會啟動既有主動檢查，可能擷取螢幕或需要 portal 同意；
切換語系不啟動檢查。明確的 `run_diagnostics`、`AC_diagnose` 與 MCP 診斷呼叫維持主動行為；
無副作用的能力檢視使用下方獨立操作。

未完成的 screenshot portal 請求會在斷開原始 bus 前嘗試 `Request.Close`，
使用獨立的 0.25 秒 D-Bus I/O 預算。伺服器回傳替代 handle 時會跟隨該 handle；
方法回覆不確定時則使用預測 handle，已完成的 Response 不重複關閉。
一般清理錯誤不覆蓋主要擷取失敗；原始取消與強制中斷物件會穿過包裝及清理繼續傳播。
D-Bus 寫入與回覆共用呼叫預算，連線建立有明確時限，connect／驗證／Hello 中斷時，
即使 `__enter__` 失敗也會釋放自己擁有的描述元。實際合成器／對話框取消仍待平台驗收。

有一件只在 Wayland 出現、需要事先規劃的事：**擷取回來的圖裡可能有滑鼠游標。**
這裡沒有任何一條擷取要求游標，但只要 backend 沒有游標平面（包含任何以
`WLR_NO_HARDWARE_CURSORS=1` 執行的 session），wlroots 就會畫**軟體游標**並把它
合成進輸出緩衝區，而擷取交回來的正是那一份。Windows 與 X11 都不含游標，所以
「定位器、樣板比對或 OCR 在目標中間看到一個游標形狀的洞」只會在這裡發生。
Wayland 不讓用戶端讀游標位置，所以沒有東西可以可靠地遮或閃避：請在擷取之前
把指標移離要拍的區域。`screen_capture` 檢查會以 `cursor_may_be_captured` 回報這件事。

如果以上都不適用你的環境，可以直接指定自己的指令——它優先於所有偵測，`{output}` 會被
換成暫存 PNG 路徑：

```bash
export JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND="mycapture --png {output}"
```

Wayland 禁止非特權用戶端進行全域輸入錄製——若要錄製，請設定
`JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11` 並在 X11 session 下執行。視窗管理支援
Windows、macOS（pyobjc）與 X11（含 XWayland）；純 Wayland session 的協定不讓用戶端看到別的程式的視窗，
所以 `list_windows()` 回傳空清單，其餘視窗操作一律拋出帶原因的 `AutoControlUnsupportedOperationException`。對於會忽略合成輸入的應用程式，
可選用驅動層後端（`JE_AUTOCONTROL_WIN32_BACKEND=interception`、
`JE_AUTOCONTROL_LINUX_BACKEND=uinput`、ViGEm 虛擬手把）；驅動未安裝時會自動退回原本行為。

---

## 文件與範例

| 資源 | 內容 |
|---|---|
| [`examples/`](../examples/) | 43 個自足腳本：截圖點擊、OCR、排程器、遠端桌面、agent loop、可觀測性、錄製、變數、熱鍵、觸發器、報表、MCP、REST、機密、外掛、computer use、Wayland、跨主機 DAG、chat-ops、pytest/BDD、錨點定位、動作日誌、因果 peer 控制。 |
| [Read the Docs](https://autocontrol.readthedocs.io/en/latest/) | 完整 API 參考，含英文與中文。 |
| [architecture_explore.md](../architecture_explore.md) | 逐層記錄每個模組的職責。 |
| [docs/CAPABILITY_MATRIX.md](../docs/CAPABILITY_MATRIX.md) | 能力 × 平台對照矩陣。 |
| [docs/API_LIFECYCLE.md](../docs/API_LIFECYCLE.md) | 穩定 API 與棄用政策。 |
| [docs/updates/](../docs/updates/README.md) | 更新紀錄：各版本說明與完成的工作，每月一個檔（原 `WHATS_NEW.md`）。 |
| [CHANGELOG.md](../CHANGELOG.md) | 相容性變更記錄。 |
| [SECURITY.md](../SECURITY.md) | 安全政策與回報方式。 |

---

## 開發

```bash
git clone https://github.com/Integration-Automation/AutoControlGUI.git
cd AutoControl
pip install -r dev_requirements.txt
uv sync                 # 或：以已提交的 uv.lock 做可重現安裝
```

```bash
python -m pytest test/unit_test/headless      # 無頭單元測試
python -m pytest test/integrated_test/        # 跨模組流程測試

ruff check je_auto_control/
pylint je_auto_control/
bandit -c pyproject.toml -r je_auto_control/
```

dev／main 的無頭工作會保留七天的 `native-<os>-<python>` artifact，內含合併行程輸出、
套件／執行環境版本與退出碼。Linux 經 GDB 保留各執行緒原生堆疊；其他平台保留 Python
faulthandler 輸出，測試失敗仍會使工作失敗。可在 repo 執行單一指令
`python scripts/ci_native_diagnostics.py --artifact-dir test-artifacts -- python -m pytest -v --tb=short --timeout=120`；
Linux 安裝 GDB 後，可在 `--` 前加入 `--native`。
含空白／引號的 argv 仍是原始參數，已處理的 `SIGINT` 會傳給子行程。
Linux 先在完整套件的 debugger 外驗證診斷工具；前置檢查紀錄也收在同一 artifact。

選定的 dev 推送由 `.github/workflows/ei-lifecycle.yml` 在隔離 libei／libeis
容器執行，將版本及兩份原生紀錄保留於 `ei-lifecycle-<run>-<attempt>` artifact 十四天。
半開與 live 釋放子行程分別有十／六十秒時限與 faulthandler；其他子行程失敗使 CI 失敗，
釋放成功必須有 begin／end 標記。半開探測另須有相同整數 fd 數量，live 清理先釋放擁有的
device refs。run 39507190704 在 libei／libeis 1.3.901-1 通過 9/9 與 20/20 檢查，
包含座標越界拒絕且不轉用 CLI。半開 `ei_unref` 仍會 SIGSEGV，因此保留 runtime 保護，
helper 隔離仍待完成。裝置暫停與序號回讀仍未驗證；受控 socket peer 不代表合成器授權、
真機或多螢幕驗收。

歡迎貢獻——請見 [CONTRIBUTING.md](../CONTRIBUTING.md) 與
[CODE_OF_CONDUCT.md](../CODE_OF_CONDUCT.md)。CI 會強制兩條規則：`import je_auto_control`
絕不能載入 PySide6；每個功能都必須同時具備無頭 API 與 GUI 介面。

---

## 授權

[MIT License](../LICENSE) © JE-Chen。
內含與選用第三方元件的授權請見 [Third_Party_License.md](../Third_Party_License.md)。

- **首頁**：https://github.com/Integration-Automation/AutoControlGUI
- **PyPI**：https://pypi.org/project/je_auto_control/
- **文件**：https://autocontrol.readthedocs.io/en/latest/

舊式 MCP 動作包裝、平行分支及本機 DAG worker 也會保留相同的來源限制。

受管指標動作可指定該次觀察的元素索引或縮圖座標，由主機檢查目前畫面並換算原生座標，包含縮放與負螢幕原點。收據保存幾何依據，不保存影像位元組。`AgentObservationStale` 表示分派前已拒絕動作；本機 agent 只在 adapter 確認沒有按住或待處理輸入時，於重試預算內重新觀察。

緊急停止先回傳帶有 metadata.details_deferred 的精簡狀態，完整產物連結可由個別任務查詢。

受管滑鼠按下前會正規化按鈕擁有權並確認實際游標位置。Windows 指標檢查會拒絕其他視窗遮擋。影像只將指定視窗繪製至清空的私有 GDI 記憶體，幾何變動會拒絕該畫面；繪製或讀取失敗亦會釋放資源。不改用桌面擷取。這些路徑已用模擬原生 API 測試，實際原生驗收仍未驗證。

Agent 任務介面將任務範圍、工作流程設定、觸發器、技能及恢復分頁。觀察頁顯示唯讀元素和已驗證、嚴格遮罩的 JPEG，每個邏輯畫面像素對應一個呈現像素。選取元素或影像座標只會編輯該次觀察的動作請求；由 Actions 的「執行觀察動作」透過共用任務 API 送出。切換任務會清除預覽，遲到回覆不能替換目前任務；新畫面必須重新選取，舊索引不能直接重用。關閉介面只解除請求訂閱。

受管工作流程可用 workflow_wait／AC_workflow_wait 等待指定控制項的精確值或狀態，只重複讀取；可取消且受動作預算限制，預設五秒、上限六十秒，不重送寫入或提交。固定技能每一步都驗證已完成收據與固定順序，恢復亦不能跳過讀回失敗的步驟；模型自主迴圈仍保留停滯偵測。新表單／跨應用範本會在提交前拒絕原本已匹配的確認值，提交後等待新的狀態轉換。批次可設定 new_record_selector 逐筆重設；確認只證明設定的介面轉換，有交易識別值時應使用它。歸檔範本完成時會重讀指定清單及檔案摘要，清單上限一 MB，總驗證資料上限六十四 MiB。

AgentHumanReview 表示未儲存內容或未知對話框需人工審閱；包含外部觀察請求都會記錄 waiting_user 並釋放輸入控制權，明確恢復後仍會重新檢查。Windows 依原生對話框／停用擁有者及英中日已知未儲存文字判定。Workspace 也會拒絕標題首尾帶星號的文件，並可在視窗設定加入 unsaved_selector 與 unsaved_value，於改變排列前檢查應用特有指示；不宣稱能推斷所有程式的未儲存狀態。標準檔案對話框沿用 AC_handle_file_dialog 執行器，受管 driver 只接受唯一精確標題、相同 PID、已確認前景，以及授權根目錄內的絕對路徑。UIA 控制項須屬於實際指定的根視窗，同 PID 的其他視窗也會拒絕。模擬原生與本機 HTTP 測試已有覆蓋，實際平台驗收仍未驗證。

主機目標以 AgentTargetProfile 與 manage_agent_target（AC_agent_target，register/get/disable/enable/probe）設定。名稱及設定固定不可替換，目前提供 desktop／files／browser adapter，未實作類型會被拒絕；瀏覽器可使用主機審閱的 helper_python。任務固定主機設定摘要，不能擴大工具、應用、根目錄或網路來源。啟停狀態會跨重啟保存並於分派時檢查；停用會要求暫停及清理，重新啟用仍須明確恢復任務。list_agent_targets／AC_agent_target_list／CLI agent-task targets 只提供被動資訊，readiness=not_probed、native_evidence=not_recorded；完整設定需要 manage_hosts。CLI agent-task target 及 GUI「主機目標」頁使用同一服務。匿名有效 MCP 工具 session 的直接及舊式包裝呼叫都以 operator 權限執行；MCP 主機管理需要已驗證的管理員，可信任的直接 Python 呼叫維持原行為。瀏覽器自動化統一由 WebRunner（je_web_runner）提供，本機開發來源為 D:/Codes/WebRunner；browser profile 使用受管 je_web_runner SDK 契約，依賴診斷不代表原生可用。

既有瀏覽器自動化（包含 open_path(URL) 與 AC_open_path）統一交由 WebRunner，Python 套件名稱為 je_web_runner。URL 計畫的 backend 現為 je_web_runner，原本比較 webbrowser 描述值的呼叫端需改用新值；函式介面與本機檔案開啟維持相容。實際 URL 執行需要設定的 WebRunner 專案，缺少時傳出 WebRunnerBridgeError，不改用 OS 瀏覽器。本機開發來源為 D:/Codes/WebRunner；純計畫及注入 opener 測試不需要該套件。協定支援由 WebRunner 與其選用的瀏覽器決定。既有瀏覽器 GUI／MCP／AC 及錄製的 WR_* 動作都使用同一橋接。
