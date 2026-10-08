=======================================
MCP 伺服器 (讓 Claude 使用 AutoControl)
=======================================

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
  ``ac_window_maximize``、``ac_window_restore``。最後三個在視窗已不存在時，
  或（最大化與還原）Windows 拒絕把它帶到前景時，會回工具錯誤（``isError``）
  ——此時視窗可能已改變狀態但沒有成為作用中視窗。以前不論結果都回傳視窗代碼。

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
  ``ac_list_action_commands``、``ac_list_run_history``、
  ``ac_stop_execution``、``ac_list_executions``（停止／列出可停止的執行；把清單包進
  ``AC_run_stoppable`` 就是可停止的）。

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
  桌面」分頁所用的 process-global registry,作用在目前那一個 host 或
  viewer,不論是誰開的(狀態結果以 ``owner`` 回報;連線被工具取代或結束的
  GUI 面板會關掉自己的視窗),模型可以代為啟動 host
  (``token``、``bind``、``port``、``fps``、``quality``、
  ``host_id``)、連線 viewer 至另一台主機、查詢狀態,並透過目前的
  viewer 將滑鼠 / 鍵盤 / type / hotkey 動作轉送給遠端 host。狀態
  類工具屬於唯讀,在 ``--readonly`` 模式下仍然可用;
  ``send_input`` 屬於破壞性工具。

每個工具都會帶上 MCP 2025-06-18 規範的 ``annotations``
(``readOnlyHint``、``destructiveHint``、``idempotentHint``、
``openWorldHint``),client 可以據此自動允許唯讀查詢,並在執行破壞
性動作前要求使用者確認。

會送出輸入、執行 action 清單／腳本／程式碼(當下執行,或之後由排程、
觸發器、熱鍵、監看、語音指令執行)、刪除資料、把資料送出本機,或放寬安全
控制(對外連線、USB ACL、核准、秘密租借、開放遠端工作階段)的工具,都標為
破壞性。會寫入呼叫端指定路徑的工具一律不是唯讀;唯讀工具拿到不存在的
``db`` 時回傳空結果,不會建立檔案。``ac_assert_http`` 只送 ``GET`` 或
``HEAD``。

參數不符合工具的輸入 schema 時(缺少或型別錯誤的屬性、不在 ``enum`` 裡的值、schema
沒宣告的參數),會在工具執行前拒絕,並以工具執行錯誤回報:結果帶 ``isError: true``,
文字說明哪裡不對,讓模型能修正參數再試(MCP 2025-11-25)。未知的工具或根本不是
``tools/call`` 的請求,仍是 ``-32602`` 協定錯誤。

工具以任何例外失敗時也以同樣方式回覆:``isError: true`` 加上例外的型別與訊息,所以每個呼叫都有回應。
已經執行的工具不會因為審計記錄寫不進去而被回報成失敗,改為寫進記錄檔。不是 JSON-RPC 2.0 請求的訊息
(沒有或錯誤的 ``jsonrpc``、不是字串的 ``method``、不是字串、數字或 ``null`` 的 ``id``)回 ``-32600``。
``"id": null`` 的請求以 ``"id": null`` 回覆;只有沒有 ``id`` 成員的訊息才是通知。

Resources、Prompts、Sampling
============================

Resources
  - ``autocontrol://files/<name>`` — workspace 根目錄底下的所有
    JSON action 檔(client 推送 ``roots/list`` 後會自動切換根目錄)。
    只讀得到單純的 ``*.json`` 檔名;根目錄裡的其他檔案、子目錄和含
    ``:`` 的串流名稱都讀不到。
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
  等級。2026-07-28 的請求只收到它自己產生的記錄,而且只在它設了
  ``io.modelcontextprotocol/logLevel`` 時才收到(見 `無狀態請求
  (2026-07-28)`_)。
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
   je_auto_control_mcp --read-only          # 伺服器只提供唯讀工具
   je_auto_control_mcp --tool-mode progressive   # 只提供少量核心工具;見「工具模式」
   je_auto_control_mcp --list-tools --tool-mode progressive   # 新 session 看到的清單
   je_auto_control_mcp --fake-backend       # 切換成記憶體版 backend

只給一個 ``--list-*`` 旗標時輸出該陣列;給多個時輸出一個以 ``tools`` / ``resources`` /
``prompts`` 為鍵的物件。不論主控台的碼頁為何,輸出與 stdio 伺服器的訊息一律是 UTF-8。

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
- 缺少或錯誤的 ``Authorization: Bearer <token>`` 都回 401，並帶
  ``WWW-Authenticate: Bearer`` 挑戰（送了錯誤 token 時加上
  ``error="invalid_token"``），這是 MCP 授權規格的要求；比對透過
  ``hmac.compare_digest`` 以常數時間進行。
- ``ssl_context`` 會包住 socket,讓同一條傳輸支援 HTTPS。
- 預設綁定 ``127.0.0.1``;若要對外,務必同時設定 ``auth_token``
  與(非 localhost 場景)``ssl_context``。

Bearer token 也可從 ``JE_AUTOCONTROL_MCP_TOKEN`` 環境變數讀取。

**角色（選用的 RBAC）。** 把 ``JE_AUTOCONTROL_RBAC_USERS`` 設為使用者存放檔，或對
``start_mcp_http_server``／``HttpMCPServer`` 傳 ``user_store=UserStore(path)``，HTTP
傳輸就會把每個請求驗證為存放檔中的某位使用者，而不是比對共用 token（此時
``auth_token`` 與 ``JE_AUTOCONTROL_MCP_TOKEN`` 不再被接受，且一律需要 bearer token）。
存放檔、角色與建立使用者的方式見維運層 REST API 章節的「角色」；兩個伺服器可以共用
同一個檔案。沒有設定存放檔時行為完全不變。stdio 傳輸沒有 bearer token，不受 RBAC
約束。

- 工具標示 ``readOnlyHint`` 時需要 ``read_screen``，否則需要 ``drive_input``。
  ``ac_remote_host_start``／``_stop``、``ac_usb_acl_add``／``_remove``／
  ``_set_default``、``ac_usb_passthrough_enable``、``ac_egress_allow``／``_reset`` 與
  ``ac_load_plugins`` 需要 ``manage_hosts``\ （``admin``）；``ac_user_add``／
  ``_remove``／``_set_role``／``_rotate_token``／``_list`` 需要 ``manage_users``\
  （``admin``）。
- 唯讀不等於可以給人看：回傳主機資料而不是畫面狀態的唯讀工具需要 ``read_data``，
  ``operator`` 與 ``admin`` 有這個能力，``viewer`` 沒有。包括剪貼簿工具
  （``ac_get_clipboard`` 及其 ``_csv``／``_files``／``_html``／``_image``／``_rtf``
  變體、``ac_clipboard_formats``、``ac_assert_clipboard``、``ac_clip_history_list``／
  ``_search``）；讀檔工具（``ac_load_dotenv``、``ac_load_data``、
  ``ac_read_action_file``、``ac_read_document``、``ac_read_presentation``、
  ``ac_read_workbook``、``ac_extract_pdf_text``、``ac_assert_pdf_text``、
  ``ac_assert_file``、``ac_build_provenance``、``ac_verify_provenance``）；資料庫與
  具名儲存區（``ac_sql_query``、``ac_assert_db``、``ac_get_asset``、``ac_list_assets``、
  ``ac_cas_get``、``ac_outbox_pending``、``ac_checkpoint_status``、``ac_memory_recall``、
  ``ac_memory_recent``、``ac_s3_list``）；參照與 token（``ac_resolve_ref``、
  ``ac_resolve_refs``、``ac_generate_otp``、``ac_jwt_encode``、``ac_jwt_decode``）；
  以及行程清單、網路與麥克風探測（``ac_list_processes``、``ac_assert_process``、
  ``ac_wait_for_process``、``ac_assert_http``、``ac_wait_for_port``、
  ``ac_assert_audio``）。完整清單是 ``je_auto_control.utils.rbac.policy`` 的
  ``DATA_TOOLS``。其餘唯讀工具 ``viewer`` 都保留：螢幕尺寸、視窗、像素、影像與文字
  定位、無障礙讀取、等待。
- ``tools/list`` 只回呼叫者可以呼叫的工具；對其他工具 ``tools/call`` 會回 JSON-RPC
  錯誤 ``-32003``\ （``Forbidden: ...``、``data.required_capability``），且不會執行。
- 接受動作清單的工具（``ac_execute_actions`` 等）在清單含有呼叫者角色沒有的指令時
  同樣被拒絕，例如 operator 的 ``AC_sign_action_file``。
- Token 的角色不在存放檔定義的角色之內時回 HTTP 403。
- 每一行稽核紀錄都帶 ``user_id`` 與 ``role``；被拒絕的呼叫記為
  ``"status": "denied"``。

瀏覽器送來的請求只接受本機來源：``Origin`` 不是 loopback 的一律回 403；伺服器綁在
loopback 時，``Host`` 不是 loopback 名稱的也回 403（防 DNS rebinding）。非瀏覽器的
客戶端不送 ``Origin``，不受影響。要讓其他來源的瀏覽器客戶端連線，把完整來源列在
``JE_AUTOCONTROL_MCP_ALLOWED_ORIGINS``（逗號分隔，例如 ``https://tool.example:8443``）。

設定 ``JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE=1`` 時，宣告了 ``elicitation`` 的握手時代客戶端
必須先開著該 session 的事件串流，破壞性工具才能確認；沒有串流就拒絕執行，而不是直接放行。
確認提示只接受它被送往的那個 session 的回覆。

Session
=======

``initialize`` 會協商協定版本:client 提出的版本若是伺服器支援的(``2025-11-25``、
``2025-06-18``、``2025-03-26``、``2024-11-05``)就用它,否則用其中最新的。2025-11-25 的
client 還會在 ``serverInfo`` 拿到 ``description``。完全拿掉 ``initialize`` 的 2026-07-28
改成逐請求服務(見 `無狀態請求 (2026-07-28)`_);``initialize`` 若指名它,拿到的是
2025-11-25。走 HTTP 時,``MCP-Protocol-Version``
標頭寫的若是伺服器不支援的版本,請求會以 400 拒絕,回覆的是列出支援版本的
``UnsupportedProtocolVersion``(``-32022``)錯誤。伺服器只宣告伺服器端能力(tools、resources、
prompts、logging);``sampling/createMessage``、``roots/list`` 與 ``elicitation/create``
只會送給在 initialize 時宣告了對應能力的 client。

``initialize`` 會產生一個 session,並用 ``Mcp-Session-Id`` 回應標頭
交給 client。之後每個請求都帶上這個標頭,伺服器就會把它們視為同一個
scope——包含你在 ``initialize`` 聲明的能力,以及進行中呼叫佔用的槽位
——不管你開了幾條 TCP 連線。不帶這個標頭時,每個請求只以自己的連線
為範圍,也就是這條傳輸從前唯一的行為。

- ``GET /mcp`` 帶 ``Accept: text/event-stream`` 與有效的
  ``Mcp-Session-Id``,會開啟**常駐的 server→client 串流**。凡是不
  屬於某個特定請求之回覆的伺服器主動訊息都走這條:進度通知,以及
  下面確認關卡要送的 ``elicitation/create``。一個 session 只能有一
  條串流,第二個 ``GET`` 會收到 409。串流會定期送出 SSE 註解當作
  心跳,好讓斷掉的 socket 變成一個寫入錯誤,而不是一條卡住的執行緒。
- 要回答伺服器的請求,就在任何一條連線上 ``POST`` 一個普通的
  JSON-RPC response(同樣帶 session 標頭)。伺服器會依 id 對回正在
  等待的那個呼叫,並以 202 回覆。
- ``DELETE /mcp`` 帶標頭會終止 session,並釋放掛在它底下的所有狀態;
  不帶標頭時照舊接受,不影響沒有 session 概念的 client。
- 未知或已過期的 id 一律回 **404**,不會改用一個新的 scope 服務它:
  client 手上有伺服器沒有的狀態,它需要知道自己該重新 initialize。
- 啟用角色(RBAC)時,session 屬於用 ``initialize`` 建立它的那位使用者。其他使用者
  拿同一個 id 來 ``POST``、開 ``GET`` 串流或 ``DELETE``,一律回 **403**,而且這次嘗試
  不會讓 session 保持存活。以前只要通過驗證,任何使用者都能用這個 id,因此可以接上
  別人的串流、結束別人的 session,或看到別人啟用了哪些工具。沒有設定使用者存放檔時
  沒有人被識別,id 的行為與以前相同。
- 在任何請求之外註冊或移除的工具(由 watcher 執行緒載入的 plugin),會對每個 session
  的常駐串流送出 ``notifications/tools/list_changed``。沒有 ``GET`` 串流的 session
  無處可收。
- session 有上下界。十分鐘沒被碰過就會被掃掉(常駐串流會讓自己的
  session 保持新鮮),而註冊表滿 128 個時,最久沒動的那個會被淘汰。

無狀態請求 (2026-07-28)
=======================

伺服器同時支援兩個協定時代,逐請求決定。``params._meta`` 帶著
``io.modelcontextprotocol/protocolVersion`` 的請求以無狀態方式服務,只看這個請求本身;
``initialize`` 與所有不帶這個鍵的請求,照 `Session`_ 一節的方式服務。所以既有的
client 不用改,可以和 2026-07-28 的 client 並存。

- **逐請求欄位。** 除了版本,還必須有 ``io.modelcontextprotocol/clientCapabilities``
  (物件);``clientInfo`` 與 ``logLevel`` 可省略。欄位缺少或格式不對是 ``-32602``。
  伺服器不以無狀態方式服務的版本是 ``-32022``,它的 ``data`` 列出 ``supported``
  (``2026-07-28`` 在前,接著是需要 ``initialize`` 的握手時代版本)與 ``requested``。
- **``server/discover``** 回覆 ``supportedVersions``、伺服器的 ``capabilities``
  (工具清單變更與 resource 訂閱,都經由 ``subscriptions/listen``)與身分。沒有逐請求欄位時是 ``-32602``。
- **方法。** ``tools/list``、``tools/call``、``resources/list``、``resources/read``、
  ``prompts/list``、``prompts/get`` 與 ``subscriptions/listen``。這個版本移除了 ``ping``、``logging/setLevel``
  與 ``resources/(un)subscribe``,在無狀態請求裡它們是 ``-32601``。
- **``subscriptions/listen``** 每個請求開一個訂閱。它的 ``notifications`` 篩選可以要
  ``toolsListChanged`` 與 ``resourceSubscriptions`` (URI 清單;可訂閱的是
  ``autocontrol://screen/live``)。第一則訊息是 ``notifications/subscriptions/acknowledged``,
  列出伺服器會送的部分:``promptsListChanged`` 與 ``resourcesListChanged`` 不列(這兩個清單
  不會變),無法訂閱的 URI 也不列。之後每則通知都在
  ``_meta["io.modelcontextprotocol/subscriptionId"]`` 帶這個請求的 id。只有伺服器結束訂閱時
  (``serve_stdio`` 結束、``HttpMCPServer.stop()``)這個請求才會收到回覆:一個 ``complete``
  結果,帶同樣的 ``_meta``。client 在 stdio 用 ``notifications/cancelled`` 結束它,走 HTTP
  則關掉串流;HTTP 需要 ``Accept: text/event-stream``,否則是 406。已經在監聽的 id 是
  ``-32600``,篩選格式錯誤是 ``-32602``。
- **結果。** 每個結果都帶 ``resultType`` (``complete``,或下面的 ``input_required``),
  並在 ``_meta["io.modelcontextprotocol/serverInfo"]`` 放伺服器的名稱、版本與說明。
  ``server/discover``、三個清單與 ``resources/read`` 另帶快取提示:``cacheScope``
  一律是 ``private``;``ttlMs`` 在 ``server/discover`` 是一小時、清單是一分鐘、
  ``resources/read`` 是 ``0`` (內容是即時的)。
- **不送 client 沒要的東西。** 關卡讀的能力是這個請求自己的,不是某條連線的;伺服器
  不主動送請求(``request_sampling`` 與 ``refresh_roots`` 在無狀態請求裡會丟例外);
  記錄只送給設了 ``logLevel`` 的請求,而且只送該等級以上;第一個請求就是無狀態的
  stdio 對端,不會收到背景記錄,清單變更與 resource 更新也只經由它的
  ``subscriptions/listen`` 送達。
- 破壞性工具的確認改用多輪往返:見 `破壞性動作確認(Elicitation)`_。
- **走 HTTP 時**,``MCP-Protocol-Version`` 標頭或 ``_meta`` 寫 2026-07-28 的請求就是無狀態
  請求。它必須把 body 映到標頭:``MCP-Protocol-Version`` 等於 ``_meta`` 的版本、
  ``Mcp-Method`` 等於 ``method``,``tools/call``/``prompts/get``/``resources/read`` 還要
  ``Mcp-Name`` 等於工具或 prompt 名稱、或 resource URI(不是純 ASCII 的值用
  ``=?base64?...?=``)。標頭缺少或與 body 不符是 400 加 ``HeaderMismatch``(``-32020``);
  版本不對、缺中繼資料或缺 client 能力是 400;未知方法是 404。不保留 session:
  ``Mcp-Session-Id`` 會被忽略、也不會發新的;指名 2026-07-28 的 ``GET``/``DELETE`` 是 405。
  普通的 JSON ``POST`` 就能做所有事,確認也一樣(問題放在結果裡回來);SSE ``POST``
  另外會送出呼叫的進度通知。

工具模式:full、progressive、static
====================================

預設情況下 ``tools/list`` 會回傳所有已註冊的工具,這就是 **full** 模式;它是預設值,
回應內容與以前完全相同。另外兩種模式給不該背著幾百份用不到的 schema 的 client 使用:

.. list-table::
   :header-rows: 1
   :widths: 16 84

   * - 模式
     - ``tools/list`` 提供什麼
   * - ``full``
     - 全部工具,一次回完。預設值。
   * - ``progressive``
     - 五個核心工具。Session 先搜尋 registry、讀取想用的工具的 schema、再啟用它;
       之後該工具才出現在 *這個 session* 的清單裡,並且可以呼叫。
   * - ``static``
     - 一份固定的 profile,不能再啟用任何工具。給只讀一次清單、之後不再更新的 client。

用 ``JE_AUTOCONTROL_MCP_TOOL_MODE``、``je_auto_control_mcp --tool-mode
{full,progressive,static}`` 或程式碼選擇模式:

.. code-block:: python

   import je_auto_control as ac

   ac.start_mcp_stdio_server(tool_mode="progressive")
   ac.start_mcp_http_server(tool_mode="progressive")
   ac.HttpMCPServer(tool_mode="static")

``AC_start_mcp_server`` 與 ``AC_start_mcp_http_server`` 接受同一個 ``tool_mode``
參數;環境變數則對所有啟動方式生效。不是這三個值之一時伺服器會拒絕啟動,而不是悄悄地
提供全部工具。Dispatcher 的模式在建立時就固定了,所以同時傳 ``tool_mode`` 與另一種
模式的 ``mcp=`` 會丟出 ``ToolDisclosureError``。

**核心工具** (僅 progressive 模式):

.. list-table::
   :header-rows: 1
   :widths: 24 76

   * - 工具
     - 作用
   * - ``ac_tools_search``
     - ``query``、``limit`` (1-50,預設 10),可選的 ``category`` 與 ``capability``。
       回傳 ``name`` / ``summary`` / ``category`` / ``capability`` / ``read_only`` /
       ``takes_paths`` / ``enabled`` 的列,以及 ``total`` 與 ``truncated``——絕不含 schema。
   * - ``ac_tools_schema``
     - 依 ``name`` 取得單一工具的完整描述。
   * - ``ac_tools_enable``
     - ``names``:工具名稱,或用 ``category:<名稱>`` 啟用整個分類。回覆
       ``enabled`` / ``already_enabled`` / ``unavailable``,以及是否送出了
       ``notifications/tools/list_changed``。
   * - ``ac_tools_disable``
     - 移除這個 session 啟用過的工具。
   * - ``ac_tools_state``
     - 目前模式、這個 session 已啟用的工具、各分類及其數量,以及呼叫所受的限制
       (唯讀、路徑根目錄、``env://`` 允許清單、角色)。

分類就是建立該組工具的 factory 名稱(``mouse``、``screen``、``window`` ……);plugin
的工具歸在 ``plugin``。

**Session。** 已啟用的集合只屬於一個 session,不與任何人共用:HTTP 上是
``Mcp-Session-Id`` (client 忽略該標頭時則是它的連線),stdio 伺服器則有唯一一個隱含的
session。Session 被刪除、被清掃、被淘汰、連線關閉或 stdio 迴圈結束時就會釋放。啟用或
停用只會對該 session 送出 ``notifications/tools/list_changed``;沒有常駐 ``GET`` 串流的
普通 HTTP ``POST`` 無處可收,所以回覆會是 ``"list_changed_sent": false``,client 應該
重新請求 ``tools/list``。

**分頁。** 在這兩種模式下 ``tools/list`` 會分頁,每頁 100 個工具
(``server.disclosure.page_size``):還有下一頁的結果會帶 ``nextCursor``,下一次請求
以 ``cursor`` 送回。每一頁都在 ``_meta`` 的
``io.github.integration-automation/toolSnapshot`` 帶著所屬清單的 id。Cursor 延續的是
第一頁被請求當下的那份清單,即使中途有 plugin 載入或移除也一樣,所以不會有一頁混到
兩份 registry。格式錯誤、屬於別的 session、或指向伺服器已不再保留的清單(每個 session
只記最近八份)的 cursor 會得到 ``-32602``;請不帶 cursor 重新請求 ``tools/list``。
full 模式不分頁,並且和以前一樣忽略 ``cursor``。

**靜態 profile。** ``JE_AUTOCONTROL_MCP_TOOL_PROFILE`` 是以逗號分隔的工具名稱與
``category:<名稱>`` 項目。在 static 模式下它就是整份清單;未設定時,profile 是短別名
背後的 19 個工具(``ac_click_mouse``、``ac_type_text``、``ac_screenshot`` ……)。在
progressive 模式下,有設定的 profile 會和核心工具一起提供給每個 session,因此從不更新
清單的 client 仍然有這些工具可用。MCP 沒有任何 client capability 能表示「我會處理
``tools/list_changed``」,所以伺服器無法偵測這種 client:請對它使用 static 模式或
profile。2026-07-28 的請求在 progressive 模式下一律得到靜態 profile——該版本沒有可以
存放已啟用集合的 session。

**模式不會改變的事。** 它決定的是「提供」什麼,從來不是「允許」什麼:

* 每一次呼叫仍然依同樣的順序通過同樣的關卡——角色、輸入 schema、路徑根目錄與
  ``env://`` 允許清單、rate limit、確認——稽核紀錄也和以前一樣。
* 搜尋、schema 與啟用都只依呼叫者可以呼叫的工具回答。角色不允許、或唯讀模式排除的
  工具找不到、查不到描述,啟用時會被回報為 ``unavailable``。
* 呼叫 session 清單裡沒有的工具會得到 ``-32602``,並在稽核 log 記為 ``denied``。
  角色拒絕仍然是它自己的代碼 ``-32003``。
* 唯讀模式下不能啟用會變更狀態的工具,包含伺服器啟動後才由 plugin 註冊的工具。
* Plugin 移除的工具會立刻從所有 session 消失。之後若以同名重新註冊,必須重新啟用。
* 核心工具的名稱不能被覆蓋註冊,也不能被移除。

**成本。** ``benchmarks/mcp_discovery.py`` 透過兩種傳輸共用的 dispatcher,在同一個
process 內量測兩種模式。以 680 個工具的 registry 量測(2026-10-09,一台 Windows 11
機器,30 次取中位數):

.. list-table::
   :header-rows: 1
   :widths: 40 30 30

   * - 項目
     - ``full``
     - ``progressive``
   * - 新 session 的 ``tools/list`` 工具數
     - 680
     - 5
   * - 該結果的大小
     - 327,378 bytes
     - 2,411 bytes(0.74 %)
   * - ``initialize`` + ``initialized`` + ``tools/list``
     - 43.7 ms
     - 1.0 ms
   * - 一次 ``ac_tools_search`` (10 列,2,390 bytes)
     - --
     - 3.1 ms
   * - 一次 ``ac_tools_schema``
     - --
     - 0.3 ms
   * - 一次 ``ac_tools_enable`` + ``ac_tools_disable``
     - --
     - 0.9 ms

.. code-block:: shell

   python benchmarks/mcp_discovery.py --rounds 30

唯讀 / 安全模式
===============

設定 ``JE_AUTOCONTROL_MCP_READONLY=1``(或對 ``je_auto_control_mcp`` 加上
``--read-only``,或呼叫 :func:`build_default_tool_registry` 時傳 ``read_only=True``)只暴
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

伺服器啟動之後,在每一種工具模式下都維持這個限制:在執行中的唯讀伺服器上註冊、且沒有
標為唯讀的工具(透過 ``register_tool``、``ac_load_plugins`` 或 plugin watcher),不會
出現在 ``tools/list``,呼叫它會得到 ``-32602`` 並在稽核 log 記為 ``denied``。預設的
``full`` 模式以前只在建立 registry 時過濾,所以這種工具會被列出、也會執行。Plugin
工具一律註冊為破壞性,因此\ **唯讀伺服器不會執行任何 plugin 工具**;你自己的程式以
``readOnlyHint`` 為 true 註冊的工具仍然會提供。設了該環境變數時,
``MCPServer(tools=[...])`` 也會被同樣過濾——內嵌的伺服器若必須忽略該變數,請傳
``read_only=False``。

把檔案參數限制在根目錄內
========================

唯讀模式限制的是「有哪些工具」，不是「工具能開哪些檔案」：``ac_load_dotenv``、
``ac_read_document``、``ac_extract_pdf_text`` 仍能讀伺服器行程讀得到的任何檔案。要限制這一點，
請給伺服器根目錄。預設關閉——兩個變數都沒設的伺服器行為與以前完全相同，唯讀模式也一樣。

``JE_AUTOCONTROL_MCP_PATH_ROOTS``
    以 ``os.pathsep`` 分隔的目錄（Windows 是 ``;``，其他平台是 ``:``）。設了就啟用檢查。

``JE_AUTOCONTROL_MCP_PATH_ROOTS_FROM_CLIENT``
    設為 ``1`` / ``true`` / ``yes`` / ``on`` 時，除了上面那個變數之外，也接受用戶端透過
    ``roots/list`` 回報的目錄。單獨設它也會啟用檢查；在用戶端回覆之前，所有檔案參數都會被拒絕，
    而不是先放行。只在你信任用戶端描述的工作區時使用——走 HTTP 時，任何連得到伺服器的呼叫端
    都能回報根目錄。

.. code-block:: json

   {
     "mcpServers": {
       "autocontrol_safe": {
         "command": "python",
         "args": ["-m", "je_auto_control.utils.mcp_server"],
         "env": {"JE_AUTOCONTROL_MCP_READONLY": "1",
                 "JE_AUTOCONTROL_MCP_PATH_ROOTS": "C:/work/project"}
       }
     }
   }

根目錄生效後，schema 標了 ``"format": "path"`` 的工具參數都會先經過 ``os.path.realpath``，
結果必須落在某個根目錄內。``..``、指向外面的 symlink 或 junction、其他磁碟機、UNC 分享，
都以實際指向的位置判斷；以 ``~`` 開頭的路徑，展開與不展開兩種讀法都必須在根目錄內。
被拒絕時回的是工具執行錯誤（``isError: true``，``Invalid arguments for <tool>: ...``），
和其他參數錯誤一樣。通過檢查後，工具收到的是檢查過的那個絕對路徑，所以相對路徑是相對於
伺服器的工作目錄。

這個標記看的是語意，不是屬性名稱：``ac_json_query`` 的 ``path`` 是 JSONPath，不受影響。

**只有某些情況下才是路徑的參數**\ 帶第二種標記 ``"format": "path-or-other"``：
``ac_open_path`` / ``ac_plan_open`` 的 ``target``（路徑或 URL）、``ac_file_association``
的 ``target``（路徑或副檔名）、``ac_act_in_view`` 的 ``target``（樣板路徑或文字），以及
``ac_handle_file_dialog`` 的 ``path``。這類值\ *是*\ 路徑時才受根目錄約束，也就是符合
下列其中一項：

* 看起來是絕對路徑——以 ``/``、``\``、``~`` 或磁碟機（``C:\`` / ``C:/``）開頭，含 UNC
  共用——不論它是否存在；
* 是 ``file:`` URL，依它指向的檔案判斷；
* 相對於伺服器的工作目錄，它指向某個存在的東西（``..``、``notes.txt``）。

其他的值——``https://...``、``.txt``、文字 ``Submit``——原樣通過；通過檢查的值也會原封不動
交給工具（不會改寫成標準化路徑，因為同一個字串可能就是呼叫者要找的文字）。有兩點要知道：
設定了根目錄時，看起來像絕對路徑（``/help``）或剛好是根目錄外某個現存檔案名稱的\ *文字*\
目標會被拒絕；``ac_handle_file_dialog`` 是把字打進別的應用程式，相對名稱的意義由那個程式
自己的目前目錄決定——伺服器只判斷它判斷得了的部分。

根目錄**涵蓋不到**的地方：

* ``ac_execute_actions`` 與其他執行動作清單的工具——動作可以開任何檔案，這也是它們不屬於
  唯讀工具的原因。
* ``ac_launch_process`` 的 ``argv`` 與 ``ac_shell`` 的 ``command``，這是刻意的：命令列就是
  一個程式，參數的意義由該程式決定，只拒絕看起來像路徑的參數並不能限制任何東西。不要把這些
  工具提供給你想限制的 client。
* 自由格式物件裡的路徑（``ac_run_suite`` 的 ``spec``、``ac_run_dag`` 的 ``definition``、
  ``ac_assert_all`` 的 ``specs``）。
* 外掛註冊的工具，除非它的 schema 也帶這個標記。

``ac_resolve_ref`` / ``ac_resolve_refs`` 的 ``file://`` 參照套用同一組根目錄；``env://``
另有自己的開關：

``JE_AUTOCONTROL_MCP_ENV_REF_ALLOW``
    以逗號分隔的變數名稱，可用 ``fnmatch`` 樣式（``APP_*,HOME``）。設了之後，``env://NAME``
    只有名稱符合時才會解析，其餘回工具執行錯誤。沒設時和以前一樣，任何變數都讀得到——
    包括放 API 金鑰的那些。

在程式裡，同一份設定是 ``server.argument_policy``\ （:class:`ArgumentPolicy`，內含
:class:`je_auto_control.PathPolicy` 與允許清單）；自己建立的伺服器可以指派另一個。

破壞性動作確認(Elicitation)
=============================

設定 ``JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE=1`` 後,所有 destructive
工具在執行前會送出 MCP ``elicitation/create``。Client 顯示確認對話框,
使用者拒絕時模型會收到乾淨的錯誤,不會執行動作。需要 client 自己
聲明 ``elicitation`` 能力;舊 client 會留下 warning log 後繼續執行。

這個提示是伺服器在「收到呼叫」與「回答呼叫」**之間**問出去的問題,
所以它需要一條 client 當下正在聽的通道。各傳輸的情況:

- **stdio** — 一定有;client 就在同一條 pipe 的另一端。
- **HTTP** — 只要 client 回送 ``Mcp-Session-Id``(見 `Session`_),
  並且給伺服器一條送問題的通道就有。兩種通道都算:常駐的 ``GET``
  串流,或是一個 SSE ``POST``——它自己的回應串流會在結果之前先送出
  ``elicitation/create``。兩種情況下,答案都要用另一個 ``POST`` 送
  回來,因為 client 正忙著讀它問過去的那條串流。

**2026-07-28** 的請求不會收到 ``elicitation/create``。第一次呼叫的回覆是
``resultType: "input_required"``:問題放在 ``inputRequests["confirm"]``,另有一個
``requestState``。client 問過使用者之後,以同樣的參數重送同一個呼叫,把答案放在
``inputResponses["confirm"]``(例如 ``{"action": "accept"}``),並原樣帶回
``requestState``。這個 state 以只存在於伺服器行程裡的金鑰簽章,寫明工具與參數摘要,
五分鐘後過期,而且只接受一次;任何一項不符都是 ``-32602``。走 HTTP 時不需要 session,
也不需要開著串流。``decline`` 或 ``cancel``
是工具執行錯誤(``isError: true``),工具不會執行;沒帶答案的重送會再問一次。沒有
宣告 ``elicitation`` 的無狀態 client 會收到 ``-32021``,``data.requiredCapabilities``
寫明缺的能力,而不是像握手時代那樣不經詢問直接執行。

.. warning::

   如果 client 不回送 ``Mcp-Session-Id``,或是自始至終只送普通的
   JSON ``POST``、一條串流都沒開,伺服器就沒有地方可問——這時
   destructive 工具會**不經詢問直接執行**,和一個從未聲明
   ``elicitation`` 的 stdio client 完全一樣。
   這條退路會留下 log,但它終究是退路:對外開放的 HTTP 服務,請把
   bearer token、綁定 ``127.0.0.1`` 與 ``JE_AUTOCONTROL_MCP_READONLY``
   當成真正的控制手段,它們不需要 client 配合。

稽核 Log
========

稽核 log **預設關閉**:沒有設定下面的變數(也沒有把 ``AuditLogger(path=...)``
交給 ``MCPServer``)時,不會記錄任何東西,也不會建立任何檔案——工作目錄裡也不會;
先前的 docstring 把工作目錄寫成預設值是錯的。

設定 ``JE_AUTOCONTROL_MCP_AUDIT=/path/to/audit.jsonl``,每次
``tools/call`` 都會寫一筆 JSONL:時間戳、工具名稱、過濾過的參數
(``password`` / ``passphrase`` / ``token`` / ``secret`` / ``api_key`` /
``key`` / ``authorization`` 等名稱在任何層級都會被替換成 ``<redacted>``,
動作清單照執行器 log 的規則遮罩)、狀態(``ok`` /
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
==========================

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
  或指令字串(POSIX 規則切分;Windows 上原樣交給 ``CreateProcess``),
  從不啟用 OS shell。
