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

主機目標以 AgentTargetProfile 與 manage_agent_target（AC_agent_target，register/get/disable/enable）設定。名稱及設定固定不可替換，目前提供 desktop／files adapter，未實作類型及可執行設定會被拒絕。任務固定主機設定摘要，不能擴大工具、應用、根目錄或網路來源。啟停狀態會跨重啟保存並於分派時檢查；停用會要求暫停及清理，重新啟用仍須明確恢復任務。list_agent_targets／AC_agent_target_list／CLI agent-task targets 只提供被動資訊，readiness=not_probed、native_evidence=not_recorded；完整設定需要 manage_hosts。CLI agent-task target 及 GUI「主機目標」頁使用同一服務。匿名有效 MCP 工具 session 的直接及舊式包裝呼叫都以 operator 權限執行；MCP 主機管理需要已驗證的管理員，可信任的直接 Python 呼叫維持原行為。瀏覽器自動化統一由 WebRunner（je_web_runner）提供，本機開發來源為 D:/Codes/WebRunner；這批目標註冊尚不含受管瀏覽器 adapter。

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
