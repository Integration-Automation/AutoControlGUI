================================
維運與管理層
================================

本頁說明 AutoControl 在 2026 年 4 月強化週期（第 22–29 輪）所加入的
維運層。每個功能都是 headless-first：每項都附 Python API、可在 JSON
動作腳本中使用的 ``AC_*`` executor 指令、可透過 HTTP 取用的 REST 端點，
以及在需要視覺互動時提供的 Qt GUI 分頁。

統一目標：讓 AutoControl 不依賴桌面 GUI 也能執行，可作為 daemon 部署在
遠端機器上並集中管理。

.. contents::
   :local:
   :depth: 2


資料夾同步（增量鏡像）
======================

以輪詢方式運作的資料夾鏡像，透過既有的遠端桌面檔案 channel 把新增與
修改過的檔案推送到對端。同步是 *增量唯一* — 不會把本地刪除與重新命名
傳出去，因此即使在編輯途中啟用同步也不會默默破壞遠端內容。

Headless::

   from pathlib import Path
   from je_auto_control.utils.remote_desktop.file_sync import FolderSyncEngine

   engine = FolderSyncEngine(
       watch_dir=Path("/home/me/notes"),
       sender=lambda local_path, remote_name: my_send(local_path, remote_name),
       poll_interval_s=3.0,
       include_subdirs=False,
   )
   engine.start()
   ...
   engine.stop()

行為：

- ``start()`` 時建立初始快照但 *不* 傳送 — 既存檔案視為已同步。
- 每個 tick 掃描資料夾；``mtime`` 或大小與快照不同的檔案會被傳送。在檔案自己最後一次寫入後
  兩秒內被記錄的檔案還會比對內容，所以同一個時間刻度內的編輯不會漏掉。
- 傳送失敗會在下一個 tick 重試（快照只記錄成功的傳送）。
- 本地刪除會停止追蹤但不會呼叫 sender。

GUI：WebRTC viewer 分頁中的 *Folder sync* 群組，含資料夾選擇器與啟動／
停止按鈕。


coturn TURN 設定包
==================

產生可部署的 coturn 設定，使用者可自架 TURN 中繼而不必付錢給服務商。
輸出四個檔案：

- ``turnserver.conf`` — coturn 設定
- ``coturn.service`` — systemd unit 檔
- ``docker-compose.yml`` — 單容器部署（host 網路模式）
- ``README.txt`` — 含 ``turn:`` / ``turns:`` URL、使用者名稱、密鑰的
  快速參考

含換行的欄位，或含 ``:`` 的 ``user``，會以 ``ValueError`` 拒絕（命令列回傳
結束碼 2）；否則它會在 ``turnserver.conf`` 裡加入自己的指令。

Headless::

   from pathlib import Path
   from je_auto_control.utils.remote_desktop.turn_config import write_bundle

   write_bundle(
       Path("./turn-bundle"),
       realm="turn.example.com",
       user="alice", secret="HUNTER2",
       listen_port=3478, tls_port=5349,
       tls_cert="/etc/letsencrypt/cert.pem",
       tls_key="/etc/letsencrypt/key.pem",
       external_ip="203.0.113.5",
   )

CLI::

   python -m je_auto_control.utils.remote_desktop.turn_config \
       --realm turn.example.com --user alice \
       --secret HUNTER2 \
       --tls-cert /etc/letsencrypt/cert.pem \
       --tls-key /etc/letsencrypt/key.pem \
       --output-dir ./turn-bundle

若省略 ``--secret``，會自動產生 32 字元的 ``secrets.token_urlsafe``。


強化版 REST API
================

REST API 圍繞三個面向重建：bearer token 認證、稽核軌跡、以及 per-IP
速率限制。

認證閘道
--------

- 除了 ``/health`` 與 ``/dashboard`` 之外，所有端點都需要
  ``Authorization: Bearer <token>`` 標頭。
- Token 為 URL-safe 隨機字串；以 ``secrets.compare_digest`` 做常數
  時間比較。
- Per-IP token bucket：每分鐘 120 次、burst 30。
- 失敗認證追蹤：60 秒內 8 次錯誤 token → 之後該 IP 再送錯誤 token 會得到
  ``locked_out``\ （回 429）；正確的 token 永遠不會被鎖，鎖定也不會是全域的。
- POST 的內文要等路徑與 token 檢查通過才讀取，未認證的請求直接得到 401／429，
  不會被解析。
- 401 會帶 ``WWW-Authenticate: Bearer realm="autocontrol"``\ （送了錯誤 token
  時加上 ``error="invalid_token"``）。已知路徑用了另一個方法會得到 405 與
  ``Allow`` 標頭；未知路徑仍是 404。

Headless::

   from je_auto_control.utils.rest_api import (
       RestApiServer, generate_token,
   )
   server = RestApiServer(host="127.0.0.1", port=9939, enable_audit=True)
   server.start()
   print("Bearer:", server.token)

CLI::

   python -m je_auto_control.utils.rest_api --host 127.0.0.1 --port 9939

設定了 ``JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS`` 而檔案沒有簽章或驗章失敗時，
``POST /execute_file`` 回 ``403`` 並附上原因；該檔案不會被執行。

角色（選用的 RBAC）
--------------------

預設情況下所有呼叫端共用同一個 token，可以使用所有端點。把伺服器指向一個使用者
存放檔之後，每個呼叫端改為擁有自己的 token 與角色：

- **啟用方式**：把 ``JE_AUTOCONTROL_RBAC_USERS`` 設為使用者存放檔路徑、對
  ``python -m je_auto_control.utils.rest_api`` 傳 ``--users <檔案>``，或對
  ``RestApiServer``／``start_rest_api_server`` 傳 ``user_store=UserStore(path)``。
  除此之外不會自動啟用——單純存在 ``~/.je_auto_control/users.json`` 並不算。
- **啟用後共用 token 一律被拒絕。** Bearer token 必須屬於存放檔中的某位使用者；
  存放檔是空的或讀不出來時，任何人都進不來。
- **沒有啟用時完全不變**：單一共用 token、沒有角色、不會有 403。

第一位 admin 在主機上從終端機建立；明文 token 只印出一次，檔案裡只存雜湊::

   je_auto_control users --users /etc/autocontrol/users.json add alice --role admin
   je_auto_control users list                 # 存放檔取自 JE_AUTOCONTROL_RBAC_USERS
   je_auto_control users set-role bob operator   # 角色：viewer / operator / admin
   je_auto_control users rotate-token bob
   je_auto_control users remove bob

（``python -m je_auto_control.utils.rbac ...`` 是同一組指令；``--json`` 以 JSON 輸出
結果。）之後 admin 可以從任何介面管理使用者，每一個都需要 ``manage_users`` 能力：

- 動作清單裡的 ``AC_user_add``\ （``user_id``、``role``、``display_name``、``tags``）、
  ``AC_user_remove``、``AC_user_set_role``、``AC_user_rotate_token`` 與
  ``AC_user_list``——所以 ``POST /execute`` 也可以。Script Builder 在 **Security**
  分類列出這五個指令；執行結果面板顯示 ``AC_user_add``／``AC_user_rotate_token`` 時
  會遮蔽 token，所以新 token 請從使用者群組、CLI 或腳本取得；
- MCP 工具 ``ac_user_add``／``ac_user_remove``／``ac_user_set_role``／
  ``ac_user_rotate_token``／``ac_user_list``；
- REST API 分頁的 **使用者（RBAC）** 群組（指令在 Actions 選單），該分頁也可以用這個
  使用者存放檔啟動伺服器；
- Python：``ac.rbac_add_user``／``rbac_remove_user``／``rbac_set_user_role``／
  ``rbac_rotate_user_token``／``rbac_list_users``，或直接用 ``UserStore``。

已驗證的呼叫者一律操作驗證它的那個存放檔；選用的 ``users_path`` 參數是給腳本與 CLI
用的。最後一位 admin 不能被移除或降級。``add`` 與 ``rotate`` 只回傳 token 一次：它在
回覆裡，回覆被寫進記錄時會被遮蔽，也不會出現在稽核紀錄中（稽核只記
``rbac_user_added`` 這類事件、對象與操作者）。

執行中的伺服器會在檔案變動時重新讀取，所以移除使用者、輪替 token 或改角色都在
下一個請求生效。

.. list-table::
   :header-rows: 1

   * - 能力
     - 角色
     - 端點
   * - ``read_screen``
     - viewer、operator、admin
     - 除下列兩個之外的所有 ``GET``，包含 ``/metrics``
   * - ``read_data``
     - operator、admin
     - 沒有 REST 路由；回傳主機資料而非畫面的 MCP 工具（見 MCP 章節）
   * - ``drive_input``
     - operator、admin
     - ``POST /execute``、``/execute_file``、``/usb/loopback/open``、
       ``/usb/remote/open``
   * - ``read_audit``
     - admin
     - ``GET /audit/list``、``/audit/verify``
   * - ``manage_hosts``
     - admin
     - ``POST /config/export``、``/config/import``、``/usb/passthrough/enable``、
       ``/usb/acl/add``、``/usb/acl/remove``、``/usb/acl/default``，以及任何
       尚未指定能力的路由
   * - ``sign_actions``
     - admin
     - ``AC_sign_action_file`` 指令（見下）
   * - ``manage_users``
     - admin
     - ``AC_user_*`` 指令（見上）

角色沒有該能力時回 ``403``
``{"error": "forbidden", "required_capability": "...", "role": "..."}``。
同一個值也以 ``x-required-capability`` 列在 ``/openapi.json`` 的每個 operation 上。

可以 ``POST /execute`` 代表可以執行動作，不代表可以執行每一個指令。替動作檔簽章
（``sign_actions``）、讀取稽核紀錄（``read_audit``），以及管理主機本身的指令——
``AC_admin_*``、啟動或停止 REST／MCP／遠端桌面／webhook 伺服器、``AC_usb_acl_*``、
``AC_usb_passthrough_enable``、``AC_config_import``／``AC_config_export``、
``AC_egress_allow``／``AC_egress_reset``、``AC_load_plugins``、
``AC_add_package_to_executor``、``AC_secret_init``／``set``／``remove``／``lock``／
``unlock``、``AC_audit_log_clear``\ （皆為 ``manage_hosts``）與 ``AC_user_*``\
（``manage_users``）——不論在動作清單裡巢狀多深，都需要各自的能力。請求會在第一個動作執行前就回 403 並指出 ``command``；
同樣的指令若來自動作檔，則由 executor 拒絕。

角色不是沙箱：operator 操作的是真實鍵盤，也能啟動程式，桌面使用者手動做得到的事
它都做得到。角色保護的是主機自身的特權狀態。

**延後執行的工作會記住擁有者。** 已驗證的呼叫者註冊的排程工作、觸發器、熱鍵綁定、
webhook、e-mail 觸發器或 watchdog 規則，會連同該使用者一起存下來（``job.owner`` 等，
型別為 ``DeferredOwner``），之後以該使用者的身分執行。角色是在工作觸發時到使用者
存放檔查的，不是記下來的：之後被降級的使用者，已註冊的工作也失去特權；不再有
``drive_input`` 或已被移除的使用者，其工作完全不會執行（該次執行記為失敗）；被升級
的使用者則取得新角色。沒有 RBAC 時註冊的工作（GUI、腳本、沒有使用者存放檔的伺服器）
沒有擁有者，行為與以前相同。

螢幕 observer 的監看（``AC_observe_add``、MCP 工具 ``ac_observe_add``、
``ScreenObserver.add``）是同一類延後工作：不論是誰呼叫 ``AC_observe_poll``、或由哪條
執行緒偵測到變化，回呼都以加入它的使用者（``rule.owner``）的身分執行；擁有者被移除或
降級時回呼會被拒絕。狀態機（``StateMachine``、``AC_run_state_machine``）與 planner 的
執行（``run_from_description``、``AC_llm_run``）通常就在提出要求的那個請求裡執行，身分
就是該請求的；``StateMachine`` 另外會記住建立它的使用者，``run_from_description`` 則
接受 ``owner=capture_owner()``，所以交給另一條執行緒執行時仍以該使用者的身分執行，而
不是沒有身分。

使用者存放檔啟用時，狀態查詢（``AC_rest_api_status``、REST API 分頁）回報
``"rbac": true``、``"users_path"`` 與 ``"token": null``：共用 token 會被拒絕，所以不再
顯示它。

只實作 ``check(client_ip=, header_value=)`` 的自製 gate 物件仍可使用：採用它的判定，
請求以沒有使用者身分的方式處理，與共用 token 相同。要提供身分，請實作回傳
``AuthResult`` 的 ``authenticate(...)``。

RBAC 請求的每一筆稽核紀錄都會記下使用者：``viewer_id`` 欄位存使用者 id，detail 為
``POST /execute -> ok:200 user=alice role=operator``\ （被拒絕時為
``forbidden:<能力>``）。

端點清單
--------

唯讀（GET）：

- ``/health`` *（未認證）* — 存活檢查
- ``/screen_size`` — 目前螢幕解析度
- ``/mouse_position`` — 目前滑鼠座標
- ``/sessions`` — 遠端桌面 host + viewer 狀態
- ``/commands`` — 已註冊 ``AC_*`` executor 指令清單
- ``/jobs`` — 排程任務清單
- ``/history`` — 最近執行紀錄
- ``/screenshot`` — base64 PNG 截圖
- ``/windows`` — 作業系統視窗清單（目前僅 Windows）
- ``/audit/list`` — 最近稽核紀錄（可篩選 ``event_type``、``host_id``、``limit``）
- ``/audit/verify`` — 雜湊鏈完整性檢查（見 *稽核紀錄雜湊鏈*）
- ``/inspector/recent`` / ``/inspector/summary`` — WebRTC 統計
- ``/usb/devices`` — 連接的 USB 裝置
- ``/diagnose`` — 系統診斷報告
- ``/metrics`` — Prometheus 格式（text/plain）
- ``/dashboard`` — 網頁管理介面（HTML；JS 從 sessionStorage 讀 token）

動作（POST）：

- ``/execute`` — body ``{"actions": [...], "raise_on_error": false}`` — 執行動作清單；
  ``raise_on_error`` 為 true 時在第一個失敗的動作停下，回 ``{"ok": false, "error": ...}``
  （成功則回 ``{"ok": true, "result": ...}``）
- ``/execute_file`` — body ``{"path": "..."}`` — 執行 JSON 動作檔

Executor 指令::

   AC_rest_api_start, AC_rest_api_stop, AC_rest_api_status

GUI：*REST API* 分頁 — 啟動/停止、host/port 輸入、稽核 checkbox、
複製 URL／token 按鈕。


Prometheus 指標
================

REST 伺服器在 ``/metrics`` 輸出 Prometheus exposition v0.0.4。
指標家族（counter / gauge）：

- ``autocontrol_rest_uptime_seconds`` — gauge
- ``autocontrol_rest_failed_auth_total`` — counter
- ``autocontrol_rest_audit_rows`` — gauge
- ``autocontrol_active_sessions`` — gauge（host + viewer）
- ``autocontrol_scheduler_jobs`` — gauge
- ``autocontrol_rest_requests_total{method,path,status}`` — counter

與其他端點一樣需要認證 — Grafana scraper 必須帶 bearer token。

Headless::

   from je_auto_control.utils.rest_api.rest_metrics import RestMetrics
   metrics = RestMetrics()
   metrics.record_request("GET", "/health", 200)
   print(metrics.render())


多主機管理主控台
================

管理主控台維護一份遠端 AutoControl REST 端點的通訊錄。輪詢透過
``ThreadPoolExecutor`` 並行；廣播會把同一份動作清單對 N 個主機跑一遍
並回傳每台主機的結果。

Headless::

   from je_auto_control.utils.admin import (
       AdminConsoleClient, default_admin_console,
   )

   client = default_admin_console()
   client.add_host(label="lab-01",
                   base_url="http://10.0.0.5:9939",
                   token="...", tags=["lab"])
   for status in client.poll_all():
       print(status.label, status.healthy, f"{status.latency_ms:.0f} ms")

   results = client.broadcast_execute(
       actions=[["AC_get_mouse_position"]],
   )

傳 ``raise_on_error=True`` 時，每台主機在第一個失敗的動作停下，並以
``ok: false`` 附上錯誤回報；否則 ``ok`` 只代表主機有回應，動作失敗記在
``result`` 裡。DAG runner 的遠端節點與 Admin Console 分頁都會傳這個參數。

持久化：主機儲存在 ``~/.je_auto_control/admin_hosts.json``\ （POSIX 上
模式 0600）。建構時自動 reload。

健康探測使用 ``/sessions``（已認證的端點），所以 token 錯誤的主機會
顯示為 ``HTTP 401`` 不健康狀態，而非誤導性的「可達但無用」。

Executor 指令::

   AC_admin_add_host, AC_admin_remove_host, AC_admin_list_hosts,
   AC_admin_poll, AC_admin_broadcast_execute

GUI：*Admin Console* 分頁 — 註冊主機表單、含健康/延遲/任務數欄位的
主機表、廣播文字框。


稽核紀錄雜湊鏈
==============

稽核紀錄改成可偵測竄改：每筆紀錄儲存
``SHA-256(JSON([prev_hash, ts, event_type, host_id, viewer_id, detail]))``，
形成鏈狀。修改任何過去的紀錄會改變該筆的 ``row_hash``，便不再吻合
下一筆的 ``prev_hash`` — 在下次 ``verify_chain()`` 時就會看到。

Headless::

   from je_auto_control.utils.remote_desktop.audit_log import default_audit_log

   log = default_audit_log()
   log.log("rest_api", host_id="127.0.0.1", detail="GET /health -> ok:200")
   result = log.verify_chain()
   print(result.ok, result.broken_at_id, result.total_rows)

雜湊鏈為「初次使用即信任」：在欄位加入前就存在的紀錄，會在具備雜湊鏈的版本
第一次開啟時依插入順序回填一次（記在 ``PRAGMA user_version``）。之後雜湊被清空的
紀錄就是斷鏈。

第一筆紀錄必須指向雜湊鏈的錨點：創始雜湊，或自動修剪時刪掉的最後一筆的雜湊，
所以手動刪掉最舊的紀錄也會被發現。``clear()`` 會以一筆 ``audit_log_cleared``
事件開始新的鏈，記下刪了幾筆。

雜湊是不帶金鑰的 SHA-256：沒有改寫後面所有雜湊的修改、刪除與重排都看得出來，
但能寫入資料庫檔案的人可以重建整條鏈，而刪掉最新的幾筆，單看檔案本身無法發現。
需要時請把最後一筆的 ``row_hash`` 另外保存。

REST 端點::

   GET /audit/list?event_type=rest_api&limit=50
   GET /audit/verify

Executor 指令::

   AC_audit_log_list, AC_audit_log_verify, AC_audit_log_clear

GUI：*Audit Log* 分頁 — 篩選表單、可捲動的表格、Verify Chain 按鈕，
顯示「Chain OK (N rows)」或「Chain broken at row id X of N」。


WebRTC 封包監測
================

由 WebRTC 分頁產生的 ``StatsPoller`` 餵入的程序級 WebRTC
``StatsSnapshot`` 滾動視窗。預設容量 600 筆樣本（在 1 Hz 下約 10 分鐘）。

Headless::

   from je_auto_control.utils.remote_desktop.webrtc_inspector import (
       default_webrtc_inspector,
   )

   inspector = default_webrtc_inspector()
   summary = inspector.summary()
   recent = inspector.recent(60)

``summary()`` 對 ``rtt_ms``、``fps``、``bitrate_kbps``、
``packet_loss_pct``、``jitter_ms`` 各回傳 ``last``/``min``/``max``/
``avg``/``p95``。

REST 端點::

   GET /inspector/recent?n=60
   GET /inspector/summary

Executor 指令::

   AC_inspector_recent, AC_inspector_summary, AC_inspector_reset

GUI：*Packet Inspector* 分頁 — 摘要列、各指標滾動標籤、最近樣本表格、
1 秒自動更新。


USB 裝置列舉
=============

唯讀的 USB 裝置列舉。優先嘗試 ``pyusb``\ （透過 libusb 跨平台）；若
pyusb 不存在則退回平台特定指令。

後端：

- Windows：``Get-PnpDevice -PresentOnly -Class USB | ConvertTo-Json``
  （從 InstanceId 解析 VID/PID）
- macOS：``system_profiler -json SPUSBDataType``\ （遞迴走訪）
- Linux：``/sys/bus/usb/devices``\ （讀取 sysfs）

Headless::

   from je_auto_control.utils.usb import list_usb_devices

   result = list_usb_devices()
   print(f"backend={result.backend} count={len(result.devices)}")
   for dev in result.devices:
       print(f"  {dev.vendor_id}:{dev.product_id}  {dev.product}")

REST 端點::

   GET /usb/devices

Executor 指令::

   AC_list_usb_devices

GUI：*USB Devices* 分頁 — 後端標籤、裝置表格（VID/PID/廠商/產品/
序號/位置）、重新整理按鈕。

Phase 2（真正的 USB passthrough）分階段發布 — 協定與 backend ABC 見
:doc:`usb_passthrough_design`\ ，端到端使用方式見
:doc:`usb_passthrough_operator_guide`\ ，外部安全審查清單見
:doc:`usb_passthrough_security_review`\ 。


USB hotplug 事件
================

輪詢式 USB add/remove 監測。對連續的 :func:`list_usb_devices` 快照以
``(vendor_id, product_id, serial, bus_location)`` 為 key 比對；
產生 :class:`UsbEvent` 推入 callback 與 bounded、帶序號的 ring buffer
（預設 500），讓晚加入的訂閱者可用 ``recent_events(since=seq)`` 補進度。

Headless::

   from je_auto_control.utils.usb import default_usb_watcher

   watcher = default_usb_watcher()
   watcher.start()
   ...
   for event in watcher.recent_events(since=0):
       print(event["seq"], event["kind"], event["device"])

REST 端點::

   GET /usb/events?since=<seq>&limit=<n>

Executor 指令::

   AC_usb_watch_start, AC_usb_watch_stop, AC_usb_recent_events

GUI：*USB Devices* 分頁加上 *Auto-refresh + watch hotplug* 勾選，
勾起時啟動單例 watcher 並顯示最近數筆事件。


系統診斷
========

針對 AutoControl 各子系統「目前正常嗎？」的探測。每項檢查是個小函式，
回傳 ``Check(name, ok, severity, detail)``；runner 對每項分別 catch
例外，所以單一壞掉的探針不會污染其他項目。

內建檢查：

- ``platform`` — OS 與 Python 版本
- ``optional_deps`` — 選用模組清單（aiortc、av、pyusb、pyaudio、
  pytesseract、cv2、PySide6），提供已裝/缺少的明細
- ``executor`` — 已註冊的 ``AC_*`` 指令數
- ``audit_chain`` — 雜湊鏈完整性（使用 ``verify_chain()``）
- ``screenshot`` — 實際擷取一張螢幕影像
- ``mouse`` — 讀取目前滑鼠座標
- ``disk_space`` — 使用者家目錄剩餘空間（<1 GB warn、<100 MB error）
- ``rest_api`` — registry 單例狀態

Headless::

   from je_auto_control.utils.diagnostics import run_diagnostics

   report = run_diagnostics()
   for check in report.checks:
       print(f"[{check.severity}] {check.name}: {check.detail}")
   print("ok:", report.ok)

CLI::

   python -m je_auto_control.utils.diagnostics
   # 全綠 exit 0、否則 exit 1

REST 端點::

   GET /diagnose

Executor 指令::

   AC_diagnose

GUI：*Diagnostics* 分頁 — 執行按鈕、依嚴重度上色的結果表、摘要列。


網頁管理 dashboard
===================

掛在 REST API 上的單頁瀏覽器介面。Vanilla JavaScript（無 build step）
— 頁面是 ``/dashboard`` 上的薄殼，提示使用者輸入 bearer token，
以 ``sessionStorage`` 快取，每 5 秒輪詢既有端點。

面板：診斷、sessions、inspector、USB 裝置、稽核紀錄尾段。

頁面本身未認證（純靜態 HTML/CSS/JS）；所有資料呼叫都透過已認證端點
搭配使用者提供的 token。``sessionStorage`` 在分頁關閉時清除，token
不會在瀏覽器重啟後存活。

Path-traversal 防護：asset loader 比對白名單正規式
``^[A-Za-z0-9_][A-Za-z0-9._-]*$``，並驗證 ``Path.resolve()`` 仍在
dashboard 目錄之下。``..`` 與 URL 編碼的變形都會回 404。

在任何瀏覽器開 ``http://<host>:9939/dashboard``，貼上 *REST API* 分頁
裡的 bearer token，就有可在手機上使用的即時運維視圖。


OpenAPI 3.1 + Swagger UI
========================

REST 伺服器把完整路由表以 OpenAPI 3.1 文件對外提供，外部工具
（client SDK 產生器、API explorer、合約測試）可直接消費。

REST 端點::

   GET /openapi.json    — spec 本體，需 auth
   GET /docs            — Swagger UI 殼，未認證
                          （JS 會跳出 bearer token 輸入框並注入到
                           try-it-out 請求）

Headless::

   from je_auto_control.utils.rest_api.rest_openapi import (
       build_openapi_spec, known_endpoints,
   )
   spec = build_openapi_spec(server_url="http://my-host:9939")
   for method, path in known_endpoints():
       print(method, path)

驅動 spec 的 metadata 對應放在 ``rest_openapi._ENDPOINT_METADATA``\ ，
與生成器同檔。CI 上有 drift 測試（``test_every_route_has_metadata``\ ），
新加的 ``_GET_ROUTES`` / ``_POST_ROUTES`` 條目若沒有對應 metadata
會被擋下。

每個端點宣告 summary、query 參數、request body schema（POST）、預期
回應，並繼承全域 ``BearerAuth`` security scheme — public 路徑
（``/health``、``/dashboard``、``/docs``）以顯式 ``security: []``
覆蓋。


設定包
======

對 ``~/.je_auto_control/`` 下使用者設定的單檔 JSON 匯出／匯入。
allowlist 涵蓋 8 個編碼了實際操作員偏好的檔案（admin hosts、
address book、trusted viewers、known hosts、host service，加上
持久化的 ``remote_host_id``、``viewer_id`` 與 ``host_fingerprint``\ ）。
稽核紀錄（``audit.db``\ ）刻意 **不** 在 allowlist —— 從 bundle 還原
會破壞可偵測竄改鏈。

Headless::

   from je_auto_control.utils.config_bundle import (
       export_config_bundle, import_config_bundle,
   )

   bundle = export_config_bundle()
   # ... 把 bundle 送到新機器 ...
   report = import_config_bundle(bundle)
   print(report.written, report.skipped, report.backups)

匯入是非破壞性的：要覆寫的東西先複製成 ``<name>.bak.<unix_ts>``\ ，原檔在新內容寫好之前都留在原處。
壞版本、未知檔名、path-traversal 嘗試都會被拒；bundle 與 allowlist
之間的 format 不一致（例如 allowlist 期望 ``json`` 但 bundle 給
``text``）會被略過。

CLI::

   python -m je_auto_control.utils.config_bundle export <檔案>
   python -m je_auto_control.utils.config_bundle import <檔案>
                                                       [--dry-run]

REST::

   POST /config/export    — 將 bundle 直接放在回應 body
   POST /config/import    — body 即 bundle dict

Executor 指令::

   AC_config_export, AC_config_import

GUI：REST API 分頁的 *Export Config* / *Import Config* 兩顆按鈕，
都帶檔案對話框與覆寫確認。
