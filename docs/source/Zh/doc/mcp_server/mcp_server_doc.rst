================================
MCP 伺服器 (讓 Claude 使用 AutoControl)
================================

MCP 伺服器把 AutoControl 包裝成 Model Context Protocol 服務,讓任何
支援 MCP 的客戶端(Claude Desktop、Claude Code、自製 Anthropic /
OpenAI tool-use 迴圈)都能透過 AutoControl 操控本機桌面。實作純標
準函式庫:JSON-RPC 2.0 走 stdio 或 HTTP+SSE,不需要額外的執行階段
依賴。

預設暴露約 90 個工具,並支援完整的 MCP 協定能力:tools、resources、
prompts、sampling、roots、logging、progress、cancellation、
list-changed 通知與 elicitation。

工具目錄
========

預設註冊表會把每個正式 ``ac_*`` 工具同時註冊一個短別名(``click``、
``type``、``screenshot``...),提示文字可以更精簡。要看實際目錄請
用下方「CLI 檢視」段落的 ``--list-tools``。

滑鼠 / 鍵盤
  ``ac_click_mouse``、``ac_set_mouse_position``、
  ``ac_get_mouse_position``、``ac_mouse_scroll``、
  ``ac_drag``、``ac_send_mouse_to_window``、
  ``ac_type_text``、``ac_press_key``、``ac_hotkey``、
  ``ac_send_key_to_window``。

螢幕 / 影像 / OCR
  ``ac_screen_size``、``ac_screenshot``(回傳 base64 PNG image
  內容,可選擇存檔,並支援 ``monitor_index`` 對多螢幕單獨擷取)、
  ``ac_list_monitors``、``ac_get_pixel``、``ac_diff_screenshots``、
  ``ac_locate_image_center``、``ac_locate_and_click``、
  ``ac_locate_text``、``ac_click_text``、
  ``ac_wait_for_image``、``ac_wait_for_pixel``。

視窗管理 (Windows)
  ``ac_list_windows``、``ac_focus_window``、``ac_wait_for_window``、
  ``ac_close_window``、``ac_window_move``、``ac_window_minimize``、
  ``ac_window_maximize``、``ac_window_restore``。

語意定位
  ``ac_a11y_list``、``ac_a11y_find``、``ac_a11y_click``、
  ``ac_vlm_locate``、``ac_vlm_click``。

剪貼簿 / 程序 / Shell
  ``ac_get_clipboard``、``ac_set_clipboard``、
  ``ac_get_clipboard_image``、``ac_set_clipboard_image``、
  ``ac_launch_process``、``ac_list_processes``、
  ``ac_kill_process``、``ac_shell``。

錄製 / 重播
  ``ac_record_start``、``ac_record_stop``、
  ``ac_read_action_file``、``ac_write_action_file``、
  ``ac_trim_actions``、``ac_adjust_delays``、
  ``ac_scale_coordinates``、
  ``ac_screen_record_start``、``ac_screen_record_stop``、
  ``ac_screen_record_list``。

動作執行器 / 歷程
  ``ac_execute_actions``、``ac_execute_action_file``、
  ``ac_list_action_commands``、``ac_list_run_history``。

排程 / 觸發 / 熱鍵
  ``ac_scheduler_add_job``、``ac_scheduler_remove_job``、
  ``ac_scheduler_list_jobs``、``ac_scheduler_start``、
  ``ac_scheduler_stop``、``ac_trigger_add``、``ac_trigger_remove``、
  ``ac_trigger_list``、``ac_trigger_start``、``ac_trigger_stop``、
  ``ac_hotkey_bind``、``ac_hotkey_unbind``、``ac_hotkey_list``、
  ``ac_hotkey_daemon_start``、``ac_hotkey_daemon_stop``。

遠端桌面(TCP host + viewer registry)
  ``ac_remote_host_start``、``ac_remote_host_stop``、
  ``ac_remote_host_status``、``ac_remote_viewer_connect``、
  ``ac_remote_viewer_disconnect``、``ac_remote_viewer_status``、
  ``ac_remote_viewer_send_input``。這組工具直接包裝 GUI 的「遠端
  桌面」分頁所用的 process-global registry,模型可以代為啟動 host
  (``token``、``bind``、``port``、``fps``、``quality``、
  ``host_id``)、連線 viewer 至另一台主機、查詢狀態,並透過目前的
  viewer 將滑鼠 / 鍵盤 / type / hotkey 動作轉送給遠端 host。狀態
  類工具屬於唯讀,在 ``--readonly`` 模式下仍然可用;
  ``send_input`` 屬於破壞性工具。

每個工具都會帶上 MCP 2025-06-18 規範的 ``annotations``
(``readOnlyHint``、``destructiveHint``、``idempotentHint``、
``openWorldHint``),client 可以據此自動允許唯讀查詢,並在執行破壞
性動作前要求使用者確認。

Resources、Prompts、Sampling
============================

Resources
  - ``autocontrol://files/<name>`` — workspace 根目錄底下的所有
    JSON action 檔(client 推送 ``roots/list`` 後會自動切換根目錄)。
  - ``autocontrol://history`` — 最近的執行歷程快照。
  - ``autocontrol://commands`` — 完整 ``AC_*`` 執行器目錄。
  - ``autocontrol://screen/live`` — base64 PNG 直播,
    ``resources/subscribe`` 後當畫面有變化會推送通知。

Prompts
  五個內建範本:``automate_ui_task``、``record_and_generalize``、
  ``compare_screenshots``、``find_widget``、``explain_action_file``。

Sampling
  工具可呼叫 ``server.request_sampling(messages, ...)`` 反問 client
  端的模型,適合用在「這個對話框是否在顯示錯誤?」這種需要 LLM 判
  斷的步驟。走的是和工具回應同一條 writer。

Logging 通知 / Progress / Cancellation
======================================

- stdio session 期間,專案 logger 會以 ``notifications/message``
  的形式即時推給 client。Client 可用 ``logging/setLevel`` 動態調整
  等級。
- 接受 ``ctx`` 參數的長時間工具會收到
  :class:`ToolCallContext`:呼叫
  ``ctx.progress(value, total, message)`` 推送
  ``notifications/progress``(client 須提供 ``progressToken``);呼
  叫 ``ctx.check_cancelled()`` 在收到 ``notifications/cancelled``
  時合作式中止。

以程式啟動伺服器
================

.. code-block:: python

   import je_auto_control as ac

   # 阻塞直到 stdin 關閉 — 通常作為 MCP client 的進入點。
   ac.start_mcp_stdio_server()

也可以自訂 registry、切換 fake backend、或啟動 plugin hot-reload:

.. code-block:: python

   import je_auto_control as ac

   tools = ac.build_default_tool_registry(read_only=False, aliases=True)
   server = ac.MCPServer(tools=tools)
   watcher = ac.PluginWatcher(server, "./plugins")
   watcher.start()
   server.serve_stdio()

以命令列啟動伺服器
==================

執行 ``pip install -e .``(或 ``pip install je_auto_control``)後,
``je_auto_control_mcp`` 命令會在 ``$PATH``。也能用模組形式啟動:

.. code-block:: shell

   je_auto_control_mcp
   # 或
   python -m je_auto_control.utils.mcp_server

兩種啟動方式都透過 stdin/stdout 與 MCP client 通訊,不適合直接在終
端機互動執行。

CLI 檢視旗標
============

不加旗標就啟動 stdio dispatcher。下列旗標會把目錄 dump 成 JSON 後
退出,適合 CI 煙霧測試或事先準備提示:

.. code-block:: shell

   je_auto_control_mcp --list-tools
   je_auto_control_mcp --list-tools --read-only
   je_auto_control_mcp --list-resources
   je_auto_control_mcp --list-prompts
   je_auto_control_mcp --fake-backend       # 切換成記憶體版 backend

註冊到 Claude Desktop
=====================

編輯 ``claude_desktop_config.json``,在 ``mcpServers`` 加入:

.. code-block:: json

   {
     "mcpServers": {
       "autocontrol": {
         "command": "python",
         "args": ["-m", "je_auto_control.utils.mcp_server"]
       }
     }
   }

重啟 Claude Desktop。AutoControl 工具就會出現在工具列表,模型可自
動呼叫。

註冊到 Claude Code
==================

.. code-block:: shell

   claude mcp add autocontrol -- python -m je_auto_control.utils.mcp_server

或寫進專案的 ``.claude/mcp.json``:

.. code-block:: json

   {
     "mcpServers": {
       "autocontrol": {
         "command": "python",
         "args": ["-m", "je_auto_control.utils.mcp_server"]
       }
     }
   }

HTTP 傳輸(含 SSE / Auth / TLS)
==================================

當 stdio 不方便(長時間 GUI 主機、容器、遠端機器)時,改用 HTTP 啟
動相同的 dispatcher:

.. code-block:: python

   import je_auto_control as ac
   import ssl

   ssl_context = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
   ssl_context.load_cert_chain("server.crt", "server.key")

   server = ac.start_mcp_http_server(
       host="127.0.0.1", port=9940,
       auth_token="hunter2",
       ssl_context=ssl_context,
   )

- ``POST /mcp`` 接受 JSON-RPC 主體。預設回 ``application/json``;
  如果 ``Accept`` 包含 ``text/event-stream``,會以 SSE 串流推送進
  度通知,然後送出最終結果。
- 缺少或錯誤的 ``Authorization: Bearer <token>`` 會回 401 / 403
  (透過 ``hmac.compare_digest`` 做常數時間比對)。
- ``ssl_context`` 會包住 socket,讓同一條傳輸支援 HTTPS。
- 預設綁定 ``127.0.0.1``;若要對外,務必同時設定 ``auth_token``
  與(非 localhost 場景)``ssl_context``。

Bearer token 也可從 ``JE_AUTOCONTROL_MCP_TOKEN`` 環境變數讀取。

唯讀 / 安全模式
===============

設定 ``JE_AUTOCONTROL_MCP_READONLY=1``(或呼叫
:func:`build_default_tool_registry` 時傳 ``read_only=True``)只暴
露 ``readOnlyHint`` 為 true 的工具(座標、OCR 查詢、剪貼簿讀取、歷
程等):

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

破壞性動作確認(Elicitation)
=============================

設定 ``JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE=1`` 後,所有 destructive
工具在執行前會送出 MCP ``elicitation/create``。Client 顯示確認對話框,
使用者拒絕時模型會收到乾淨的錯誤,不會執行動作。需要 client 自己
聲明 ``elicitation`` 能力;舊 client 會留下 warning log 後繼續執行。

稽核 Log
========

設定 ``JE_AUTOCONTROL_MCP_AUDIT=/path/to/audit.jsonl``,每次
``tools/call`` 都會寫一筆 JSONL:時間戳、工具名稱、過濾過的參數
(``password`` / ``token`` / ``secret`` / ``api_key`` /
``authorization`` 會被替換成 ``<redacted>``)、狀態(``ok`` /
``error`` / ``cancelled``)、執行時間、錯誤訊息與
auto-screenshot 路徑(見下)。

工具失敗自動截圖
================

設定 ``JE_AUTOCONTROL_MCP_ERROR_SHOTS=/path/to/dir``,每次工具失敗
就會寫一張 ``<tool>_<ts>.png`` 到該資料夾;路徑會同時帶在 audit log
與回傳給模型的錯誤訊息中,排查不穩定流程很快。

Rate Limiting
=============

把 :class:`RateLimiter` 傳給 :class:`MCPServer` 防止失控的迴圈灌
爆主機:

.. code-block:: python

   import je_auto_control as ac

   server = ac.MCPServer(rate_limiter=ac.RateLimiter(
       rate_per_sec=20.0, capacity=40,
   ))

超過上限就回 ``-32000`` ``Rate limit exceeded`` JSON-RPC 錯誤。

Plugin Hot-Reload
=================

把暴露頂層 ``AC_*`` callable 的 ``*.py`` 丟進資料夾,讓
:class:`PluginWatcher` 自動同步 registry:

.. code-block:: python

   import je_auto_control as ac

   server = ac.MCPServer()
   watcher = ac.PluginWatcher(server, directory="./plugins",
                                poll_seconds=2.0)
   watcher.start()
   ac.start_mcp_stdio_server()

每次 register / unregister 都會送出
``notifications/tools/list_changed``,client 會自動更新工具目錄。

CI 煙霧測試 (Fake Backend)
=========================

Fake backend 把 wrapper 層換成記憶體版的紀錄器,讓沒有顯示伺服器的
CI runner 也能走完所有 MCP 工具:

.. code-block:: shell

   JE_AUTOCONTROL_FAKE_BACKEND=1 python -m je_auto_control.utils.mcp_server

程式內使用:

.. code-block:: python

   from je_auto_control.utils.mcp_server.fake_backend import (
       fake_state, install_fake_backend, reset_fake_state,
       uninstall_fake_backend,
   )

   install_fake_backend()
   try:
       # 跑測試 / 工具 — 動作會累積在 fake_state()。
       ...
   finally:
       uninstall_fake_backend()
       reset_fake_state()

安全注意事項
============

- MCP 伺服器可以移動滑鼠、送鍵盤事件、截圖、執行任意 ``AC_*`` 動
  作。請只註冊給可信任的 MCP client。
- 預設只走 stdio,沒有任何網路曝險;若用 HTTP,預設綁定
  ``127.0.0.1``,若要 ``0.0.0.0`` 必須要有明確理由,**且必須**搭配
  ``auth_token`` 與(非 localhost 時)``ssl_context``。
- ``ac_screenshot``、``ac_screen_record_start``、
  ``ac_execute_action_file``、``ac_read_action_file``、
  ``ac_write_action_file`` 收到的路徑都會經過 ``os.path.realpath``
  正規化;FileSystem resource provider 也會在邊界擋住 path
  traversal。
- 子程序呼叫(``ac_launch_process`` / ``ac_shell``)只接受 argv list
  或 ``shlex.split`` 的解析結果,從不啟用 OS shell。
