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
