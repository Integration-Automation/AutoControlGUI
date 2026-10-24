AI Agent 與 Computer Use
===========================

AutoControl 是開源、跨平台的 **computer-use 與 GUI 自動化框架**，可以讓 AI agent 操作真實桌面，而不只依賴瀏覽器 DOM 或 API。

何時使用 AutoControl
--------------------

適合以下情境：

* 真實滑鼠與鍵盤輸入；
* 螢幕擷取與座標操作；
* OCR 與作業系統無障礙樹；
* 影像／樣板比對；
* Vision-Language Model UI 定位；
* Anchor 與 self-healing locator；
* 原生桌面應用程式與真實瀏覽器；
* 跨平台桌面與行動裝置自動化；
* JSON 動作檔；
* 透過 MCP 讓 AI agent 使用 computer use。

MCP for AI agents
-----------------

安裝並啟動 stdio MCP server：

.. code-block:: bash

   pip install je_auto_control
   je_auto_control_mcp

MCP 同時提供完整的 ac_* 工具，以及給模型使用的短名稱 alias：

* click
* move_mouse
* scroll
* type
* press
* hotkey
* screenshot
* screen_size
* find_image
* find_text
* click_text
* drag
* list_windows
* focus_window
* wait_image
* wait_pixel

若 client 只需要 canonical ac_* 工具：

.. code-block:: bash

   JE_AUTOCONTROL_MCP_ALIASES=0 je_auto_control_mcp

只做檢查、不允許修改的 client：

.. code-block:: bash

   je_auto_control_mcp --read-only

建議的 Agent Loop
-----------------

#. 觀察目前畫面。
#. 優先用無障礙樹、OCR、影像比對或 VLM 找目標。
#. 執行最小必要操作。
#. 等待介面穩定。
#. 驗證預期結果。
#. UI 改變時切換另一種 locator 策略重新嘗試。

OpenAI 工具選擇
---------------

OpenAI Chat Completions 有 provider 的工具數量限制，因此不要把整個 AutoControl 命令目錄一次交給 OpenAI agent。請針對任務建立 allow-list：

.. code-block:: python

   from je_auto_control.utils.tool_use_schema import export_openai_tools

   tools = export_openai_tools(only=[
       "AC_screenshot",
       "AC_click_mouse",
       "AC_write",
       "AC_hotkey",
       "AC_click_text",
   ])

聚焦工具集也比較安全：除非真的需要，否則不要提供 shell、process execution、package loading 或遞迴 agent 工具。

MCP client 範例
---------------

stdio MCP client 可以直接啟動 AutoControl：

.. code-block:: json

   {
     "mcpServers": {
       "autocontrol": {
         "command": "je_auto_control_mcp"
       }
     }
   }

安全性
------

AI 控制的 GUI process 具有主機操作權限。

* 非必要不要把 server 綁到公開網路。
* 檢查型 client 使用 --read-only。
* AI agent 優先使用明確的工具 allow-list。
* 不要把 shell/process/package-loading 工具暴露給不受信任的模型。
* 作為服務部署時使用 authentication、audit、rate limit 與 confirmation 控制。

單指令執行
----------

``executor.execute_one(name, arguments)`` 與 ``run_tool_call`` 共用腳本的授權、
插值、取消與日誌邊界，回傳原始結果。私有 executor 參數被拒絕；身分範圍內檢查指令能力。

受管任務
--------

明確執行 ``je_auto_control agent-task start`` 啟動本機任務服務。
Python、AC、MCP、REST、CLI 與 Agent 任務面板共用提交、觀察、動作、驗證、暫停、恢復、
取消與擁有者範圍內的狀態。完成須有確定性證據，模型停止文字不代表成功。
技能經 WorkQueue 派送；本機推論使用明確設定的 Ollama 模型，不下載、不重新導向或切換外部服務。
關閉面板後已提交工作仍由服務擁有。原生平台驗收與其餘流程列在 ``Progress.md``；
完整契約見 ``docs/AGENT_TASKS.md``。

原生操作使用專屬 helper 程序樹，支援取消、逾時、主服務輸入清理與跨資料庫桌面排他。
原生平台驗收仍暫緩。

使用 ``draft_agent_workflow`` 或 ``agent-task draft`` 預覽下載歸檔、CSV/XLSX 填表、
跨應用轉移與工作區範本；檢查權限範圍、逐步讀回及完成條件後提交。Agent 任務 Actions 提供預覽。

Windows 共用桌面需解鎖並閒置 60 秒，實體鍵鼠活動經 helper 獨立通知主服務暫停。
``stop_all_agent_tasks`` 或 ``agent-task stop-all`` 停止可見任務；其他共用桌面需活動 adapter。
單調時間預算跨重啟保留，不因系統時間倒退而延長。

``get_agent_task_receipts`` 提供逐筆結果；``reconcile_agent_task`` 記錄擁有者對不明結果的確認，
不會自動恢復或標記成功。任務 metadata 連結歷史、journal 與報告。快取預設保留 30 天，
保留使用者輸出與外部 journal；影像預設只留在記憶體，持久化需明確啟用且經嚴格遮罩。

``manage_agent_trigger`` 保留預授權間隔、Cron、檔案與事件範本，每次觸發重新檢查擁有者權限，
事件與任務去重同交易提交。``submit_agent_task`` 可帶冪等識別碼；CLI 與 Actions 提供綁定控制。
受管範圍不允許隱式解析主機 vault。

受管輸入會先寫入持久崩潰紀錄。未完成的紀錄阻止新擁有者接手；主機管理者手動放開輸入後，以 recover_agent_target(target, note) 審閱恢復，不會重播按鍵或恢復舊任務。文件啟動程序與輸入 helper 分離，任務清理保留使用者應用程式；預先指定的聚焦步驟會等待授權視窗。原生桌面及真機驗收仍未驗證。

manage_agent_skill 的 record／preview／validate／accept／run／repair 操作共用持久技能候選與版本。候選必須有自己的成功驗證任務，經明確審閱及版本比對才可發布。修復不會直接改寫使用中的版本；任務固定使用原版本及摘要。具型別的參數只能修改明確指定的資料值，不能改工具、應用或根目錄。

受管任務、觸發範本及技能驗證持續檢查來源根目錄政策。撤銷、遺失或損壞的政策紀錄會阻止後續操作。MCP 客戶端根目錄與非同步更新依連線階段隔離，過期回覆不能恢復已終止的授權。主機固定政策在更換前保留；客戶端政策在來源結束時撤銷。HTTP 客戶端根目錄不再改寫共用資源提供者的工作目錄。服務停止會取消所有實際執行中的 worker，包含尚未取得 lease 的模型初始化；尚未啟動的派送保留供服務重啟。

舊式 MCP 包裝及平行／本機 DAG worker 保留來源限制的交集。工具 context 的綁定不會自行建立紀錄，由受管任務分派延後解析。

AgentActionRequest.reference 支援 element_index 或 image_point，僅對該 observation_id 有效。主機驗證畫面版本後換算實際座標，收據保存原始要求與幾何依據而不保存影像內容。AgentObservationStale 表示未分派動作；本機 agent 只在沒有持續輸入的 adapter 上於預算內重新觀察。原生桌面與真機驗收仍暫緩。

原生 helper 以最長十五秒的唯讀交握完成啟動，實際操作仍使用原本的動作時限。影像座標換算要求 JPEG 實際尺寸與宣告的縮圖幾何一致。

受管滑鼠按下前會正規化按鈕擁有權並確認實際游標位置。Windows 指標檢查會拒絕其他視窗遮擋。影像只將指定視窗繪製至清空的私有 GDI 記憶體，幾何變動會拒絕該畫面；繪製或讀取失敗亦會釋放資源。不改用桌面擷取。這些路徑已用模擬原生 API 測試，實際原生驗收仍未驗證。

Agent 任務介面將任務範圍、工作流程設定、觸發器、技能及恢復分頁。觀察頁顯示唯讀元素和已驗證、嚴格遮罩的 JPEG，每個邏輯畫面像素對應一個呈現像素。選取元素或影像座標只會編輯該次觀察的動作請求；由 Actions 的「執行觀察動作」透過共用任務 API 送出。切換任務會清除預覽，遲到回覆不能替換目前任務；新畫面必須重新選取，舊索引不能直接重用。關閉介面只解除請求訂閱。

受管工作流程可用 workflow_wait／AC_workflow_wait 等待指定控制項的精確值或狀態，只重複讀取；可取消且受動作預算限制，預設五秒、上限六十秒，不重送寫入或提交。固定技能每一步都驗證已完成收據與固定順序，恢復亦不能跳過讀回失敗的步驟；模型自主迴圈仍保留停滯偵測。新表單／跨應用範本會在提交前拒絕原本已匹配的確認值，提交後等待新的狀態轉換。批次可設定 new_record_selector 逐筆重設；確認只證明設定的介面轉換，有交易識別值時應使用它。歸檔範本完成時會重讀指定清單及檔案摘要，清單上限一 MB，總驗證資料上限六十四 MiB。

AgentHumanReview 表示未儲存內容或未知對話框需人工審閱；包含外部觀察請求都會記錄 waiting_user 並釋放輸入控制權，明確恢復後仍會重新檢查。Windows 依原生對話框／停用擁有者及英中日已知未儲存文字判定。Workspace 也會拒絕標題首尾帶星號的文件，並可在視窗設定加入 unsaved_selector 與 unsaved_value，於改變排列前檢查應用特有指示；不宣稱能推斷所有程式的未儲存狀態。標準檔案對話框沿用 AC_handle_file_dialog 執行器，受管 driver 只接受唯一精確標題、相同 PID、已確認前景，以及授權根目錄內的絕對路徑。UIA 控制項須屬於實際指定的根視窗，同 PID 的其他視窗也會拒絕。模擬原生與本機 HTTP 測試已有覆蓋，實際平台驗收仍未驗證。

主機目標以 AgentTargetProfile 與 manage_agent_target（AC_agent_target，register/get/disable/enable/probe）設定。名稱及設定固定不可替換，目前提供 desktop／files／browser adapter，未實作類型會被拒絕；瀏覽器可使用主機審閱的 helper_python。任務固定主機設定摘要，不能擴大工具、應用、根目錄或網路來源。啟停狀態會跨重啟保存並於分派時檢查；停用會要求暫停及清理，重新啟用仍須明確恢復任務。list_agent_targets／AC_agent_target_list／CLI agent-task targets 只提供被動資訊，readiness=not_probed、native_evidence=not_recorded；完整設定需要 manage_hosts。CLI agent-task target 及 GUI「主機目標」頁使用同一服務。匿名有效 MCP 工具 session 的直接及舊式包裝呼叫都以 operator 權限執行；MCP 主機管理需要已驗證的管理員，可信任的直接 Python 呼叫維持原行為。瀏覽器自動化統一由 WebRunner（je_web_runner）提供，本機開發來源為 D:/Codes/WebRunner；browser profile 使用受管 je_web_runner SDK 契約，依賴診斷不代表原生可用。

既有瀏覽器自動化（包含 open_path(URL) 與 AC_open_path）統一交由 WebRunner，Python 套件名稱為 je_web_runner。URL 計畫的 backend 現為 je_web_runner，原本比較 webbrowser 描述值的呼叫端需改用新值；函式介面與本機檔案開啟維持相容。實際 URL 執行需要設定的 WebRunner 專案，缺少時傳出 WebRunnerBridgeError，不改用 OS 瀏覽器。本機開發來源為 D:/Codes/WebRunner；純計畫及注入 opener 測試不需要該套件。協定支援由 WebRunner 與其選用的瀏覽器決定。既有瀏覽器 GUI／MCP／AC 及錄製的 WR_* 動作都使用同一橋接。


MCP 工具探索
------------------------------------------------------------

MCP 工具探索提供 ``search_mcp_tools(query, limit=10)``、``get_mcp_tool_schema(name)``、
對應 AC／MCP 指令及 Diagnostics → Actions。搜尋回傳有界摘要、分類與所需權限；完整 schema
須指定單一工具查閱。兩種查詢都重新驗證角色，並遵守 registry 的唯讀篩選；MCP 查詢使用該
server 的即時 registry，包含外掛變更。CLI 可執行
``je_auto_control_mcp --search-tools document --limit 5`` 或 ``--tool-schema ac_mcp_tool_search``。

MCP session 工具清單
------------------------------------------------------------

MCP 可選擇 session 逐步揭露：``je_auto_control_mcp --tool-mode progressive`` 初始只提供五個
探索控制工具；``ac_mcp_tools_enable``／``ac_mcp_tools_disable`` 只改變該 session。
不會更新工具清單的客戶端可使用 ``--tool-mode static --tool-profile ac_screen_size,ac_list_windows``；
預設 ``full`` 保留不分頁的授權工具清單。逐步／固定模式的 cursor 不透明、只能使用一次，並綁定
快照與呼叫者；工具、角色或清單設定變更，以及 cursor 過期時，須重新執行 ``tools/list``。
啟停只通知擁有者連線；session 結束會回收 cursor 並使尚在執行中的 metadata callback 失效。
HTTP／嵌入式使用 ``MCPServer.configure_tool_disclosure(...)``；主機環境變數為
``JE_AUTOCONTROL_MCP_DISCLOSURE`` 與逗號分隔的 ``JE_AUTOCONTROL_MCP_TOOL_PROFILE``。
``plan_mcp_tool_profile(...)`` 及 Diagnostics Actions 可預覽啟動參數，不會啟動服務。
無狀態協定使用不分頁的初始固定清單，不保留 session 啟用狀態。唯讀限制也涵蓋後續新增的外掛。
未驗證／共享 token 連線顯示 operator 工具，與既有呼叫上限一致；主機管理工具仍須已驗證身分。

MCP 權限傳遞與 metadata 量測
----------------------------------------------------------------------

MCP 非同步呼叫會保留接受請求時的角色、session、原路徑政策與工具清單；session 或路徑政策
結束後，延遲分派會被拒絕。非同步無狀態呼叫仍使用固定 profile。外掛工具清單變更會送達所有
有效 HTTP session 串流；session 啟停只通知擁有者，並避免重複發送。串流註冊與 HTTP 標頭
共用鎖，避免提早送出的通知破壞 HTTP 回應。
純 metadata 的 ``benchmarks/mcp_discovery.py --repeats 20`` 量測工具數、JSON bytes、暖機後的
程序內交握、搜尋與啟用耗時。Windows／Python 3.14.4 的紀錄中，完整模式初始有 732 個授權工具、
358,029 bytes；逐步模式為 5 個、2,029 bytes，回應大小減少 99.43%。交握為 58.263／47.439 ms，
搜尋中位數為 16.243／19.718 ms；逐步啟用中位數為 42.486 ms。此本機量測不含冷啟動匯入及原生操作。
有日期的 JSON 紀錄位於 ``docs/benchmarks/``；既有參數政策的涵蓋限制仍列於 ``Progress.md``。


受管 WebRunner 目標與 DOM 參照
----------------------------------------------------------------------

受管瀏覽器 profile（``kind: browser``）統一委派給 WebRunner 的 ``je_web_runner`` SDK；
開發來源為 ``D:\Codes\WebRunner``，整合來源位於其隔離的受管 session 功能分支。
Profile 必須提供精確的 ``settings.allowed_origins``、瀏覽器專用工具，且不能授權桌面 app；
每項任務另須設定非空、較窄的 ``options.allowed_origins``，每次啟用均重新核對兩層範圍。
註冊不啟動資源；helper 環境須明確安裝已審閱的受管 SDK 與 Chromium，缺少時就緒失敗，不自動安裝。
``AC_browser_navigate``、``AC_browser_click``、``AC_browser_fill``、``AC_browser_select``、``AC_browser_check``
及 ``AC_browser_read`` 共用 Python/core、executor、MCP 與 Builder 定義。命令只在受管 helper 中
運作，透過既有 task submit/observe/act 週期驅動。讀取操作為 ``text``、``value`` 或 ``visible``；
WebRunner 拒絕秘密表單欄位。DOM 索引在目前 observation 內解析 selector／frame，再核對新鮮度。
失敗副作用保持不確定且需對帳；暫停／取消會結束擁有的資源。GUI Actions 可產生瀏覽器目標範例
供審閱；DOM 選取只編輯動作請求。專用 helper 跨就緒檢查保留同一個全新 session，正常清理先
取得瀏覽器 ACK，再結束自己的程序樹，不取得共用桌面輸入控制權。跨來源受控測試使用真正 SDK、
替身 Chromium、自有 IPC／loopback；實際瀏覽器／原生驗收、已審閱傳輸及瀏覽器流程編譯仍列於 ``Progress.md``。

Profile 範例（先審閱，再用 ``manage_agent_target("register", profile)`` 註冊）::

    {"name": "reviewed-browser", "kind": "browser",
     "allowed_tools": ["AC_browser_navigate", "AC_browser_fill", "AC_browser_read"],
     "settings": {"allowed_origins": ["https://example.invalid"]}}

任務指定相同 target 名稱，列出自己的工具並設定 ``options.allowed_origins``。
Skill 可導頁、填入 CSS selector，再獨立讀回 value，以 ``expect_result`` 驗證後才完成。
外部 agent 先觀察，再以目前 observation ID 和 ``reference: {"element_index": 0}``
呼叫 ``act_agent_task``；arguments 僅提供填入值／讀取操作，不混入另一個 selector／frame。
初始分頁為空白；明確授權導頁後才會出現可選 DOM 參照。


瀏覽器填表與欄位轉填草稿
----------------------------------------------------------------------

``draft_agent_workflow("batch_form", config)`` 與 ``transfer`` 可設定 ``backend: browser``，
並提供明確的 ``allowed_origins`` 與已審閱 browser target。CSV／XLSX 來源仍受 roots 限制；
瀏覽器草稿只產生 ``AC_browser_*`` 動作，不退回桌面輸入。填表提供 ``url``、CSS ``fields``、
可選 frame／新增資料控制項、送出與確認 selector；每次填入都有獨立的精確 value 讀回。
可用 ``confirmation_column`` 從每列取得預期確認文字。轉填提供 ``source_url``／``destination_url``，
擷取 text／value、套用白名單轉換、填入並讀回目的欄位，再驗證儲存；送出前拒絕陳舊確認。
``AC_browser_wait``／``browser_wait`` 只輪詢 text／value，也支援稍後才出現的元素；``wait_seconds``
預設 5 秒，受 action budget 限制，逾時才回來的相符結果仍拒絕，不重播填入或點擊。
Python/core、共用 catalog／模型 schema、MCP、CLI／REST 任務操作、Builder 及 GUI 流程預覽
使用同一編譯器。瀏覽器讀回可作為獨立技能證據。實際應用驗收、已審閱上／下載許可仍待完成；
SDK 啟動前須通過完整有界讀回契約版本 1 的檢查。

WebRunner 完整讀回相容契約
----------------------------------------------------------------------

受管瀏覽器啟動前，必須先確認 WebRunner 的 ``ManagedBrowserSession.contract_version == 1``，
通過後才建立 policy 或開啟代理／瀏覽器。缺少、布林、文字、過舊或未知標記會保留可處理的
就緒錯誤。SDK 來源 ``575e5d2`` 提供完整 text／value 讀回：最多 8,000 個 UTF-16 code unit，
超限或無效 Unicode 就拒絕，不截短。AutoControl 對瀏覽器參數與流程預覽資料套用相同 Unicode
上限，在副作用前拒絕。跨來源契約透過真正的自有 helper 與替身 Chromium 驗證；部署與實際
瀏覽器／原生驗收保持分列。

獨立瀏覽器完成檢查
----------------------------------------------------------------------

瀏覽器任務可固定完成條件，例如
``{"kind":"browser","operation":"value","selector":"#field","value":"expected"}``。
操作為精確的 ``text``、``value``、``visible``（布林）或 ``url``（不含定位）；必須明確授權
``AC_browser_read`` 與任務 origins，完成條件不會增加權限。Finish 由同一個自有 helper 檢查
目前頁面位於允許的 HTTP(S) origin，再透過受控讀取命令獨立取得 SDK 完整值；既有 receipt、
有界預覽或模型停止訊號不能代替讀回。空白／不可用／範圍外頁面、被拒讀回或錯誤驗證回覆
保持未知；比較不符保持失敗。取消、權限撤銷及人工審閱錯誤保留原類型。
GUI Actions 可草擬不啟動資源的瀏覽器完成範例；API／MCP／REST／CLI finish 共用驗證器。
SPA URL fragment 會保留，origin 比對僅略去 fragment。實際瀏覽器／應用驗收及已審閱傳輸仍待完成。

授權路徑內的瀏覽器檔案傳輸
----------------------------------------------------------------------

受管瀏覽器檔案命令 ``browser_link``、``browser_download``、``browser_upload``（對應 ``AC_browser_*``）
委派給 WebRunner 傳輸契約版本 1。上／下載授權必須具有明確的主機及任務根目錄；下載讓瀏覽器
Cookie 保留於自有 SDK／helper，核對完整長度及可選 SHA256，且不覆寫既有檔案；重用必須符合
指定 SHA256。上傳將最多 4 MiB 的單一一般檔案讀成核對過的不可變快照，驗證可選 SHA256 與
SDK 中繼資料，不自動提交表單。網路操作仍全部位於 ``je_web_runner``。
瀏覽器 ``download_archive`` 預覽接受查詢頁 ``url``、明確 ``allowed_origins``、授權範圍內 ``directory``，
以及具有單純 ``name``、``url`` 或連結 ``selector``／可選 ``frame`` 的 ``files``；每檔可用 ``page_url`` 覆寫
查詢頁。流程擷取新連結、下載每檔最多 16 MiB，並產生供獨立核對名稱／大小／雜湊的歸檔清單。
GUI Actions 只草擬檔案目標／流程／上傳範例，不啟動資源；MCP／REST／CLI／Builder／模型工具
共用命令，連結讀取仍需輸入控制權限。部署與實際瀏覽器驗收仍待完成，既有驗收暫停保持生效。

本機授權、API 與並行預算
----------------------------------------------------------------------

本機 runtime 的使用者及即時根目錄授權轉送，現在必須由明確的本機服務呼叫啟用。
一般具驗證的 HTTP 請求只帶指定的 Bearer token；runtime client 驗證 loopback 服務目的地與
路由後，才附上本機使用者／來源儲存庫／witness 資訊。版本化 ``je_auto_control.api`` 現在提供
所有已宣告的 ``api.core`` 名稱，包含受管瀏覽器命令、目標復原及技能；動作型別 stub 也涵蓋
所有出貨命令。未解析的延後專案型別沿用產生器既有的 ``Any`` 政策，避免產生無效名稱。
並行預算讀取改在資料庫獨佔交易內取樣時鐘，避免鎖取得順序不同造成任務誤判逾時；真正的
時鐘倒退仍會停止任務。GUI／MCP／REST／CLI 共用這些修正；正式工作樹及既有原生／瀏覽器／
裝置／24 小時驗收暫停維持原狀。

瀏覽器技能工作階段連續性
----------------------------------------------------------------------

固定瀏覽器技能的已驗證前綴，現在必須保有原本仍存活的瀏覽器／helper 工作階段。
暫停、清理、helper 中斷或 runtime 重啟後，舊動作紀錄無法證明表單仍保有先前欄位值；
續跑會在啟動替代 helper 或送出下一動作前進入人工審閱。請明確檢視剩餘步驟並建立新任務。
尚無保留嘗試紀錄的暫停，以及已審閱為 failed／not_applied 的嘗試，允許全新開始。
外部擁有者仍可重新觀察新工作階段，再規劃授權範圍內的新動作；未中斷的固定技能沿用原
工作階段。登入及暫存表單狀態的恢復仍是未完成工作。

桌面技能工作階段連續性
----------------------------------------------------------------------

桌面固定技能現在與瀏覽器技能共用工作階段連續性檢查。桌面 scope 或自有 helper 結束後，
沿用舊前綴前必須審閱，不能用歷史紀錄證明暫停後的表單／視窗狀態。未中斷的工作階段可正常
執行；檔案 adapter 仍以持久化產物處理復原。檢查在替代 helper 啟動前執行，既有續跑／狀態／
紀錄介面會顯示人工審閱結果。暫存表單／登入／視窗狀態恢復與可審閱的剩餘步驟重建仍待完成；
原生驗收維持暫停。

比對原提交的任務規格
----------------------------------------------------------------------

``lookup_agent_task("鍵", reviewed_spec)`` 可選擇由目的地主機正規化規格，與原擁有者提交時保存的
不可變摘要比對。回覆以 ``spec_match_contract=1`` 宣告支援，並提供 ``matches``、``differs``、
``unverifiable`` 或 ``not_found``。CLI 可加 ``--spec reviewed.json``；AC／MCP／REST／Builder
共用可選的 ``spec`` 物件。比對不提交、不啟動任務。

DAG 檢視先查鍵，再於目的地明確支援契約時，用第二次唯讀查詢核對已審閱節點規格及同一任務
身分；舊端維持未驗證，本機來源 witness 不送到遠端。鍵改指向別的任務會使舊完成快照失效。
逐節點規格一致不代表整張圖的拓樸／原批次批准，明確續接仍待審閱。
規格一致時還須逐條核對完成報告的種類、數量、通過結果、持久契約與輸入釋放；部分報告不能確認完成。

檢視中斷的 DAG
----------------------------------------------------------------------

``inspect_agent_dag(definition, timeout_seconds=30)`` 只查詢本機／已登錄遠端主機的既有提交鍵，
不提交、不暫停、不續跑。相同操作提供 ``AC_agent_dag_inspect``、MCP、REST 動作、CLI
``agent-task inspect-dag reviewed.json``、Builder 與 DAG Actions。最多 100 節點、最長 300 秒；
遠端仍須主機管理權限。本機身分／使用者資料庫路徑／來源 metadata 不送到遠端；快照不包含
遠端產物路徑或原始錯誤。GUI 在圖形編輯後捨棄舊回覆。

``recorded_completion`` 只描述查回的任務；節點規格可選擇核對，
``resume_permitted=false`` 仍表示尚未批准整張圖續接。查無紀錄不代表拒絕。
規格綁定及明確審閱仍屬後續恢復步驟，不能把既有任務紀錄當作已編輯 DAG 的完成證明。

查詢遺失的提交回覆
----------------------------------------------------------------------

``lookup_agent_task("原去重鍵")`` 只讀取目前身分及使用者資料庫範圍，不提交、不續跑、
不取得輸入。相同操作提供 ``AC_agent_task_lookup``、MCP ``ac_agent_task_lookup``、接受
``idempotency_key`` 與可選 ``spec`` 的 ``POST /agent/lookup``、CLI ``agent-task lookup 原去重鍵`` 及任務視圖
Actions。結果包含 ``found`` 與可選的 ``task`` 狀態；查無紀錄只是當下快照，晚到請求仍可能
被接收，不能當作拒絕證據。唯讀查詢仍須有任務存取權限。GUI 在鍵／任務選取改變時捨棄舊回覆；
DAG 檢視沿用此查詢；規格綁定及明確續接審閱仍待完成。

DAG 中的受管任務
----------------------------------------------------------------------

既有 Python ``run_dag``、``AC_run_dag``、MCP ``ac_run_dag``、REST／CLI 動作檔、Script Builder
及 DAG Actions 支援互斥的 ``task`` 節點，內容為 ``spec``、必填 ``idempotency_key`` 及可選
``wait_seconds``。規格限 skill 或明確配置的本機模型模式，須含工具、目的地路徑及完成條件。
省略 ``host`` 使用明確啟動的本機服務；遠端須為已登錄且配置授權 runtime 與背景派送的主機。
本功能不部署 listener；路徑由目的地主機驗證。

DAG 型別與函式亦可由 ``je_auto_control.api``／``je_auto_control.api.core`` 匯入。

節點只提交一次，再輪詢指定任務。完成條件須逐條匹配且通過，並具持久完成契約與輸入釋放
證據，才允許相依節點啟動。同一批次恢復須保留去重鍵；重跑會取得同一任務，不自動恢復
暫停／恢復中的工作。停止、取消、逾時或通訊／授權失敗時，已知任務 ID 才提出有時限的暫停；
未收到確證仍為未知，不重播動作、不搶租約。失敗結果保留任務 ID／去重鍵並略過相依節點，GUI
顯示保留的 ID。本機角色、使用者資料庫路徑及來源 witness 不送至遠端；遠端權限由已登錄的
主機憑證決定。禁止受管任務遞迴派送。目的地 runtime 的資源鎖序列化共用輸入，獨立資源可並行。
正式多機配置、跨主機產物移交及原生／裝置驗收仍分開追蹤。

完成判定與輸入釋放
----------------------------------------------------------------------

受管任務在確認自有輸入清理後才提交成功。清理失敗或仍忙碌時保留租約並要求審閱；確認前
中斷仍需恢復。條件式狀態轉換保留同時到達的取消要求。既有任務狀態／結果包含
``metadata.input_released``；新成功狀態原子保存 ``completion_contract=1``，重啟後保留；舊紀錄
維持零。成果報告與 history 依最終狀態發布。這是擁有者 runtime 的輸入釋放
證據，遠端裝置的確證仍屬獨立契約。

DAG worker 的呼叫者權限
----------------------------------------------------------------------

預設與自訂 DAG runner 在執行緒池保留呼叫者授權、取消、指令限制及受管操作 context。每個節點
啟動前重新讀取使用者資料；刪除擁有者會拒絕派送，後續相依節點略過。角色變更由各操作的
權限檢查判定。預設遠端節點在開啟主機通訊錄或動作檔案前要求 ``manage_hosts``；管理員與
受信任的直接 Python 呼叫仍可遠端派送。context 保留於本機，遠端權限由登錄的主機憑證決定。
受管節點使用上述完成與停止契約；正式多機配置及原生／裝置證據仍待接合。

隔離瀏覽器 Python 與相依套件診斷
----------------------------------------------------------------------

瀏覽器主機目標可透過可選的 ``settings.helper_python`` 指定已審閱且已安裝套件的 Python
環境（本機絕對直譯器路徑）。明確指定的 helper 使用 ``-I``，從該環境載入已安裝套件；虛擬環境
直譯器的符號連結保留環境身分。任務選項不能指定直譯器。
主機管理者可使用 ``manage_agent_target("probe", {"name":"reviewed-browser"})``、``AC_agent_target``、
MCP／REST、``agent-task target probe request.json`` 或 GUI 主機目標的診斷操作。
診斷以獨立且有時限的自有 helper，透過 ``je_web_runner`` 檢查瀏覽器依賴後結束，過程不取得輸入
擁有權或啟動瀏覽器。結果可顯示 ``python_dependencies_ready``；瀏覽器啟動及原生證據仍明確保持
``not_probed``／``not_recorded``。``last_probe`` 僅為記憶體中的具時間診斷快照，不授予任務權限，
也不啟用停用的目標。桌面／裝置的原生診斷仍待完成。
已準備的隔離環境安裝兩個功能工作樹建置的 wheel；共用環境與正式工作樹保持原狀。正式服務
設定及實際瀏覽器驗收仍分開追蹤；所有瀏覽器自動化仍統一由 WebRunner（``je_web_runner``）提供。

遠端裝置生命週期前置防護
----------------------------------------------------------------------

Android／iOS 受管 adapter 仍未提供。內部 ``remote_journal``／``remote_target`` 以可信的實體
裝置識別綁定 OS 互斥與耐久 controller／序號紀錄。必須先通過封閉能力交握，動作前／後事件
寫入並 fsync 後才送 ACK；configure／observe 不得授權副作用。本機 helper 退出不會清除未知
遠端動作；清理不啟動替代 helper、不重播指令，未確認時仍阻止控制權移交。
結束事件須證明裝置工作已完成、沒有按住的輸入或排隊寫入；傳輸呼叫返回本身不足以證明。
這項保證須由可信 SDK adapter 契約提供。

恢復須由主機可信 provider 證明同一實體裝置及所有舊 writer 已退出，先保存退出後的世代基準，
再要求能使舊指令失效且不重播的後續不同世代。不得假定 SDK 有提供這種世代／閒置保證。
一般桌面恢復不能清除遠端紀錄。SDK adapter、app scope、裝置 profile、共用公開介面、真機
證據 provider 與原生驗收仍列於 ``Progress.md``。

明確既有 ADB server 傳輸
----------------------------------------------------------------------

內部 ``android_transport.ManagedAdbServer`` 只向已審閱的明確 loopback IP／port 使用 ADB
smart-socket 協定，不呼叫 CLI、不啟動／終止／升級／重連 server。裝置清單共用既有 Android
SDK parser。Shell 必須指定數字 transport ID、使用 shell-v2 raw 封包、關閉 stdin，並收到
一個 byte 的 exit 封包與 EOF；缺少 exit、晚到資料、錯誤／過大封包、封包洪流、逾時或斷線
都拒絕，不自動重試或退回舊 shell。stdout／stderr 共用位元組上限。

整段交換共用原始時限，等待讀寫時持續檢查取消與授權；失敗訊息不公開命令內容或 server
診斷。這是主機 adapter 的內部前置層，原始 shell 不在任務／模型工具目錄。ADB server 重啟
可能重用數字 ID；有限 adapter 還須在同一命令連線內核對實體裝置／boot／app，接上耐久
副作用防護與獨立完成證據。Shell 退出不等於輸入已釋放；尚未新增受管 Android profile 或
原生就緒宣告。協定來源為英文頁列出的固定 AOSP 原始碼。

Android 身分 session 與有限提案
----------------------------------------------------------------------

內部 ``AndroidDeviceSession`` 只選取指定連線序號、唯一且就緒的數字 transport。唯讀證據須
符合預期的實體 ``ro.serialno``、kernel boot UUID，以及顯示器零上的唯一 app／裝置使用者
焦點。以固定 AOSP 格式解析有界資料，不保留原始 window dump；未知 OEM 格式拒絕。
通過即時檢查後以原子方式固定 boot，之後或並行檢查不得換成別的 boot。查詢與身分讀取
共用原始時限，不自動啟動 app 或重設裝置。

``compile_android_action`` 只接受既有 tap／swipe／text／key 名稱與封閉參數，產生主機內部
提案，原始 shell 不提供給模型。同一命令連線會在有限輸入前後核對實體、boot、顯示器及
window／activity 焦點。尾端標記保留 shell 命令替換原本會吃掉的空白重複欄位。文字限制為
有界可列印 ASCII、拒絕會失真的 literal ``%s``，並套用 shell 引用；按鍵是有限 app 輸入集。
座標、時長及編碼後整段命令都有限制。只輸出封閉階段標記；動作失敗或後續 scope 改變都
拒絕，不重試，也不視為獨立完成證據。

提案維持 ``input_authorized=false``。焦點身分不能替代輸入視窗命中、遮擋、解鎖及真人活動
證據。真實裝置控制來源、受限 hierarchy 觀察、獨立完成條件、主機 profile 與共用
使用介面仍列於 ``Progress.md``，原生／真機驗收維持暫緩。已識別的焦點欄位來源為英文頁
列出的固定 AOSP Android 14 原始碼。

Android 原生輸入與安全證據
----------------------------------------------------------------------

內部 ``inspect_input``／``propose_checked`` 在固定裝置／app 的命令連線內讀取目前 dispatcher
及 keyguard，共用原始時限。只接受預設顯示器、已識別的 identity 顯示變換、唯一 app 視窗／
原生通道，以及清空的 pending／inbound／outbound／wait 佇列。Keyguard delegate 與 monitor
皆須顯示正確使用者、未鎖定、互動中且已完成開機。目前狀態與舊 ANR 分開；歷史 recent event
與動態 Looper 時鐘不納入穩定安全摘要。

``android_geometry`` 以精確有理數區間與原生左上封閉／右下開放邊界核對完整 tap／swipe 路徑，
包含中間缺口及單一缺漏點。依前後順序檢查視窗的可見遮擋、觸控攔截、outside-touch listener
及背景 spy，不保留外部視窗名稱。透明視窗仍可能攔截；不相關的包圍盒重疊不會誤擋斜向路徑。
未知顯示變換、縮放、格式或不明確目標拒絕，不以區域視窗座標冒充全域觸控座標。

檢查後命令提案會在輸入前、同一連線內重新讀取已驗證的 routing／通道／佇列與 keyguard
區塊，比對摘要；鎖定、通道、幾何或佇列改變即拒絕。既有裝置／boot／焦點檢查及固定結果
協定保留。全域監看器須另有可信審閱，不能視為默許。證據與提案仍是
``input_authorized=false``，可信真人活動／已按下輸入／裝置端防護來源、觀察定位與獨立完成
驗證仍待接合。固定 AOSP 原始碼來源見英文頁；模擬證據不代表受管 Android 已可用，真機驗收
維持暫緩。

內部動作協定 v2 會回傳固定順序的階段紀錄；只有完整前置拒絕加上相符的 shell-v2 退出證據，
才能證明此命令未呼叫輸入。一旦可能呼叫輸入，即使退出碼與前置檢查相同，失敗或後置拒絕仍
保留副作用可能。``parse_android_action_result`` 要求完整傳輸結果、精確位元組、空 stderr 與
相符退出碼；舊標記、截斷、傳輸錯誤及不合法階段仍屬未知。輸入返回只證明命令走到該階段，
不能清除遠端 journal、證明佇列／按住輸入已清空、授權重試或取代獨立完成條件。

自有遠端 SDK worker
----------------------------------------------------------------------

``remote_worker.serve_remote_worker`` 先啟動 parent 退出監看，再呼叫固定的可信主機 factory；
任務／RPC 不可選 SDK、server、app 綁定或 factory。``RemoteDeviceAdapter`` 要求唯讀就緒／觀察／
準備、即時真人活動檢查及有限的主機端 ``PreparedRemoteAction``；主機與子程序都會精確綁定
任務／擁有者，區分 JSON 布林、整數與浮點，不允許更換範圍。

``RemoteEffectController`` 必須等主機持久化 begin 並 ACK 後才呼叫一次 SDK；worker 在輸入前
重新核對帳號權限、期限與真人接回。只有相符裝置／世代、輸入已釋放且遠端待送佇列清空的
可信證據，才可送出並確認 end；shell 返回或 Android 階段不能提供這項證明。缺少／錯誤 ACK、
撤權、逾時、晚到回覆及清理失敗都不重播、更換 helper 或代送桌面釋放。結束自有 helper 後，
未知遠端副作用仍保留隔離。可信裝置控制來源、WDA adapter、profile 與共用使用者介面
仍待接合；模擬 SDK 測試不代表真機就緒。

Android checked SDK 派送
----------------------------------------------------------------------

內部 ``AndroidRemoteAdapter`` 接合 session 與自有 worker，要求固定套件及有限工具集；沒有
明確的 ``AndroidControlProvider`` 時，在連 ADB 前就拒絕就緒。Provider 須獨立證明真人活動／
閒置、按住輸入及全域監看器審閱，並在裝置端阻止接回、取消或到期後的舊寫入。主機 lock、
context manager 或本機 helper 結束不能提供這項保證；不提供預設來源、受管 profile 或真機就緒宣告。

動作須有新的原生 metadata 觀察；準備時重讀身分／路由／安全，拒絕變動證據並消耗這次觀察。
主機端 ``AndroidCommandLease`` 綁定 checked proposal、新隨機命令 ID 與 epoch。Worker 持久化
begin 並 ACK 後，``dispatch_checked`` 重新編譯有限命令；參數／body 被改動、未檢查提案或不同
session／boot 都在傳輸前拒絕。只在可信裝置防護內呼叫一次，不重播。完整 v2 階段／退出結果
不能代表應用完成，片段結果仍未知。End ACK 前另須核對命令 ID、boot、裝置及 epoch，以及輸入
已釋放、遠端待送佇列清空的獨立證據；舊證據不能清除新命令。未配置 hierarchy reader 時只有
身分／安全 metadata；真實擷取／控制來源、受保護欄位值驗證、Unicode／IME 及 profile／共用 API／GUI 仍待交付。

Android 經審閱的語義觀察
----------------------------------------------------------------------

可明確配置主機 ``hierarchy_reader`` callable，回傳相符命令 nonce、原生裝置／視窗與顯示尺寸的
``AndroidHierarchySample``。Reader 須核對實際來源且不干擾其他無障礙服務；把要求的身分貼到
未核對的 SDK 結果不算來源證明。不自選裝置、安裝／啟動 SDK、CLI、重連或備援。固定 AOSP 的
``DumpCommand`` 會建立 ``UiAutomation``，預設連線抑制既有無障礙服務，因此不當作唯讀替代。

``android_hierarchy`` 限定有界 UTF-8、單一視窗與 rotation zero，欄位／布林封閉；defused XML
拒絕 DTD、entity 與外部來源。深度、節點／輸出數、文字及原生顯示邊界都有限制；重複索引或
不明文字授權拒絕。外部套件子樹不輸出；只有主機明確授權的非敏感唯讀標籤會揭露，XML 不可
自行授權。編輯／密碼值與受保護子節點持續遮罩；原生路由／遮擋判定元素是否可操作。

私有 keyed witness 偵測包含遮罩值的變動，但不公開。公開版本為隨機 token，同一未變動觀察保持
穩定；來源變更／還原或動作準備後都換版，包括輸入沒有改變畫面的情況，不提供隱藏值的可重用
hash。擷取前後核對原生範圍，準備與裝置防護內都重讀 hierarchy；``AC_android_tap`` 元素索引
只接受目前可操作的 Android 語義元素，不回退到截圖座標。

既有 observe／act／finish 可帶動作後的新讀回。已審閱的已知匹配可通過 ``screen.text_present``；
未擷取／遮罩觀察中的空白仍為未知，不能證明文字不存在；已知匹配可推翻 ``text_absent``。
其他部分觀察的畫面條件維持未知，能力旗標須為精確布林，錯誤資料不可變成通過。受保護輸入值
比較、Unicode／IME、預設受管 profile 與真機驗收仍未提供。格式／生命週期的固定 AOSP 原始碼
連結見英文頁。
內建 ``DesktopTarget`` 與 ``BrowserTarget`` 宣告 ``semantic_observation=True``、
``text_redacted=True``：有限控制項、略過欄位值、遮罩編輯項及不完整 frame 不代表完整文字覆蓋。
``FileTarget`` 與等待桌面視窗階段宣告 ``semantic_observation=False``，空清單不能證明文字不存在。
部分文字驗證略過密碼／敏感／遮罩列、明確隱藏或格式錯誤的可見性，以及非字串標籤；遮罩占位字
不能作為完成文字。組合條件遇到已知矛盾即失敗，其餘必要條件只要未知就保持未知；部分證據的
計數／狀態／變動條件仍為未知。精確 DOM／欄位值用既有 ``kind=browser`` 新讀回，仍須任務的
讀取／來源授權。未宣告能力旗標的自訂 target 保留既有行為，須自行提供經審閱的覆蓋契約。
