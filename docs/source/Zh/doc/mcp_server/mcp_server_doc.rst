================================
MCP 伺服器 (讓 Claude 使用 AutoControl)
================================

MCP 伺服器將 AutoControl 包裝成 Model Context Protocol 服務，讓任何
支援 MCP 的客戶端（Claude Desktop、Claude Code、自製 Claude API
tool-use 迴圈等）都能透過 AutoControl 操控本機桌面。傳輸採用 stdio
上的 JSON-RPC 2.0，純標準函式庫實作，不需要額外依賴。

連線後 Claude 能做什麼
======================

註冊 AutoControl MCP 伺服器後，模型可使用約 24 個工具：

- 滑鼠：``ac_click_mouse``、``ac_set_mouse_position``、
  ``ac_get_mouse_position``、``ac_mouse_scroll``
- 鍵盤：``ac_type_text``、``ac_press_key``、``ac_hotkey``
- 螢幕：``ac_screen_size``、``ac_screenshot``、``ac_get_pixel``
- 影像 / OCR：``ac_locate_image_center``、``ac_locate_and_click``、
  ``ac_locate_text``、``ac_click_text``
- 視窗（僅 Windows）：``ac_list_windows``、``ac_focus_window``、
  ``ac_wait_for_window``、``ac_close_window``
- 系統：``ac_get_clipboard``、``ac_set_clipboard``
- 動作執行器：``ac_execute_actions``（執行 ``AC_*`` 指令清單）、
  ``ac_execute_action_file``、``ac_list_action_commands``、
  ``ac_list_run_history``

以程式啟動伺服器
================

.. code-block:: python

   import je_auto_control as ac

   # 會阻塞到 stdin 關閉為止 — 通常作為 MCP 客戶端的進入點。
   ac.start_mcp_stdio_server()

也能自訂工具集：

.. code-block:: python

   import je_auto_control as ac

   tools = ac.build_default_tool_registry()
   server = ac.MCPServer(tools=tools)
   server.serve_stdio()

以命令列啟動伺服器
==================

執行 ``pip install -e .``（或 ``pip install je_auto_control``）後，
``je_auto_control_mcp`` 命令會在 ``$PATH``。也可以用模組形式啟動：

.. code-block:: shell

   je_auto_control_mcp
   # 或
   python -m je_auto_control.utils.mcp_server

兩種啟動方式都會透過 stdin/stdout 與 MCP 客戶端通訊，不適合直接在
終端機互動執行。

註冊到 Claude Desktop
=====================

編輯 ``claude_desktop_config.json``，在 ``mcpServers`` 加入：

.. code-block:: json

   {
     "mcpServers": {
       "autocontrol": {
         "command": "python",
         "args": ["-m", "je_auto_control.utils.mcp_server"]
       }
     }
   }

重啟 Claude Desktop，AutoControl 工具就會出現在工具列表，模型可自
動呼叫。

註冊到 Claude Code
==================

.. code-block:: shell

   claude mcp add autocontrol -- python -m je_auto_control.utils.mcp_server

或寫進專案的 ``.claude/mcp.json``：

.. code-block:: json

   {
     "mcpServers": {
       "autocontrol": {
         "command": "python",
         "args": ["-m", "je_auto_control.utils.mcp_server"]
       }
     }
   }

安全注意事項
============

- MCP 伺服器可以移動滑鼠、送鍵盤事件、截圖、並透過 ``AC_*`` 執行
  任意動作。請只註冊給可信任的 MCP 客戶端。
- 傳輸只走本機 stdio，不對外開放網路。
- ``ac_screenshot`` 與 ``ac_execute_action_file`` 收到的檔案路徑會
  先經過 ``os.path.realpath`` 正規化才進行 I/O。

唯讀 / 安全模式
===============

若要限制伺服器只暴露唯讀工具（不准點擊、輸入、執行腳本），可將
``JE_AUTOCONTROL_MCP_READONLY`` 環境變數設為 ``1`` / ``true``。只
有帶有 ``readOnlyHint`` 的工具（座標、螢幕尺寸、OCR 查詢、歷史紀
錄、剪貼簿讀取等）會被暴露：

.. code-block:: json

   {
     "mcpServers": {
       "autocontrol_safe": {
         "command": "python",
         "args": ["-m", "je_auto_control.utils.mcp_server"],
         "env": {"JE_AUTOCONTROL_MCP_READONLY": "1"}
       }
     }
   }

或以程式設定：

.. code-block:: python

   import je_auto_control as ac

   safe_tools = ac.build_default_tool_registry(read_only=True)
   ac.MCPServer(tools=safe_tools).serve_stdio()
