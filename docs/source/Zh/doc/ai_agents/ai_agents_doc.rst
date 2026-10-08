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

先只給少量工具，讓 session 自行搜尋並啟用其餘工具（見 MCP 伺服器章節的「工具模式」）：

.. code-block:: bash

   je_auto_control_mcp --tool-mode progressive

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
