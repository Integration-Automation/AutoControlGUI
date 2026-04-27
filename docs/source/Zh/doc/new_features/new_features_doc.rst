=====================
新功能 (2026-04)
=====================

本頁說明 2026 年 4 月加入的新功能。每一項新功能都同時提供 **無 GUI 的
Python API** 與 **對應的 GUI 介面**，並已連接到 executor，可從 JSON 腳
本、socket server、REST API 及 CLI 直接使用，無需撰寫額外 Python 程式
碼。

.. contents::
   :local:
   :depth: 2


剪貼簿 (Clipboard)
==================

程式碼呼叫::

   import je_auto_control as ac
   ac.set_clipboard("hello")
   text = ac.get_clipboard()

Action-JSON 指令::

   [["AC_clipboard_set", {"text": "hello"}]]
   [["AC_clipboard_get", {}]]

平台後端：Windows (ctypes + Win32)、macOS (``pbcopy`` / ``pbpaste``)、
Linux (``xclip`` 或 ``xsel``)。若無可用後端會拋出 ``RuntimeError``。


試跑 / 逐步除錯 (Dry-run / Step Debug)
======================================

無副作用執行 action 列表，方便驗證 JSON 腳本::

   from je_auto_control.utils.executor.action_executor import executor
   record = executor.execute_action(actions, dry_run=True)

``step_callback`` 可在每一條 action 執行前收到通知::

   executor.execute_action(actions, step_callback=lambda a: print(a))

CLI::

   python -m je_auto_control.cli run script.json --dry-run


全域熱鍵 (Windows)
==================

綁定系統級熱鍵到 action-JSON 腳本::

   from je_auto_control import default_hotkey_daemon
   default_hotkey_daemon.bind("ctrl+alt+1", "scripts/greet.json")
   default_hotkey_daemon.start()

支援的修飾鍵：``ctrl``、``alt``、``shift``、``win`` / ``super`` /
``meta``。按鍵：英文字母、數字、``f1``–``f12``、方向鍵、``space``、
``enter``、``tab``、``escape`` 等。

macOS 與 Linux 目前在 ``start()`` 會拋出 ``NotImplementedError`` ──
採 Strategy pattern，未來可擴充對應後端。

GUI：**全域熱鍵** 分頁。


事件觸發器 (Triggers)
=====================

輪詢式觸發器，偵測到畫面或狀態變化時執行腳本::

   from je_auto_control import default_trigger_engine, ImageAppearsTrigger
   default_trigger_engine.add(ImageAppearsTrigger(
       trigger_id="", script_path="scripts/click_ok.json",
       image_path="templates/ok_button.png", threshold=0.85,
       repeat=True,
   ))
   default_trigger_engine.start()

可用類型：

- ``ImageAppearsTrigger`` — 螢幕上偵測模板影像
- ``WindowAppearsTrigger`` — 視窗標題包含子字串
- ``PixelColorTrigger`` — 某座標像素顏色在容差內
- ``FilePathTrigger`` — 監看檔案 mtime 變化

GUI：**事件觸發器** 分頁。


Cron 排程
=========

五欄位 cron (``minute hour day-of-month month day-of-week``)，支援
``*``、逗號列表、``*/step`` 步進、``start-stop`` 範圍::

   from je_auto_control import default_scheduler
   job = default_scheduler.add_cron_job(
       script_path="scripts/daily.json",
       cron_expression="0 9 * * 1-5",   # 週一到週五 09:00
   )
   default_scheduler.start()

interval 與 cron 排程可同時存在，可由 ``job.is_cron`` 判斷類型。
GUI：**排程器** 分頁新增 cron/interval 切換。


外掛載入器 (Plugin Loader)
==========================

外掛檔案為任何定義頂層 ``AC_*`` callable 的 ``.py``，每個都會成為新的
executor 指令::

   # my_plugins/greeting.py
   def AC_greet(args=None):
       return f"hello, {args['name']}"

::

   from je_auto_control import (
       load_plugin_directory, register_plugin_commands,
   )
   commands = load_plugin_directory("my_plugins/")
   register_plugin_commands(commands)

GUI：**外掛** 分頁，可選擇目錄一鍵載入。

.. warning::
   外掛檔案會直接執行任意 Python 程式。請務必只載入自己信任的目錄。


REST API 伺服器
===============

純 stdlib HTTP server，公開 executor 與 scheduler::

   from je_auto_control import start_rest_api_server
   server = start_rest_api_server(host="127.0.0.1", port=9939)

端點：

- ``GET /health``
- ``GET /jobs``
- ``POST /execute`` (body: ``{"actions": [...]}``)

GUI：**Socket 伺服器** 分頁新增獨立的 REST 區塊。

.. note::
   預設綁定 ``127.0.0.1`` (符合 CLAUDE.md 規範)。只有在網路邊界已做好
   身分驗證時才綁定 ``0.0.0.0``。


CLI 子指令介面
==============

以 headless API 為基礎的輕量 CLI::

   python -m je_auto_control.cli run script.json
   python -m je_auto_control.cli run script.json --var name=alice --dry-run
   python -m je_auto_control.cli list-jobs
   python -m je_auto_control.cli start-server --port 9938
   python -m je_auto_control.cli start-rest --port 9939

``--var name=value`` 優先以 JSON 解析 (``count=10`` 會變 int)，失敗時
當作字串。


GUI 多語系
==========

可透過 **Language** 選單即時切換。內建語言包：

- English
- 繁體中文 (Traditional Chinese)
- 简体中文 (Simplified Chinese)
- 日本語 (Japanese)

執行期可註冊額外語言::

   from je_auto_control.gui.language_wrapper.multi_language_wrapper import (
       language_wrapper,
   )
   language_wrapper.register_language("French", {"menu_file": "Fichier", ...})

缺少的 key 會退回英文，讓新功能未翻譯前仍可正常顯示。


可關閉分頁 + 選單列
===================

主視窗改為 ``QMainWindow`` + 選單列：

- **File** → 開啟腳本 / 結束
- **View → Tabs** → 每個分頁可勾選顯示或隱藏
- **Tools** → 啟動熱鍵 / 排程 / 觸發器服務
- **Language** → 切換語言
- **Help** → 關於

點擊分頁的 ✕ 即可關閉，之後可從 *View → Tabs* 恢復。


OCR 螢幕文字辨識
================

以 Tesseract 為後端的文字定位。適用於沒有穩定 Accessibility 名稱、也
不方便擷取模板影像的按鈕或標籤::

   import je_auto_control as ac

   matches = ac.find_text_matches("Submit")
   cx, cy = ac.locate_text_center("Submit")
   ac.click_text("Submit")
   ac.wait_for_text("載入完成", timeout=15.0)

若 Tesseract 不在 ``PATH`` 中::

   ac.set_tesseract_cmd(r"C:\Program Files\Tesseract-OCR\tesseract.exe")

Action-JSON 指令：``AC_locate_text``、``AC_click_text``、
``AC_wait_text``。


Accessibility 元件搜尋
======================

透過作業系統無障礙樹查詢控制項（Windows UIA 透過 ``uiautomation``；
macOS AX），支援依名稱 / 角色 / 應用程式過濾::

   import je_auto_control as ac

   elements = ac.list_accessibility_elements(app_name="Calculator")
   ok = ac.find_accessibility_element(name="OK", role="Button")
   ac.click_accessibility_element(name="OK", app_name="Calculator")

當前平台若沒有可用後端會拋出 ``AccessibilityNotAvailableError``。
Action-JSON 指令：``AC_a11y_list``、``AC_a11y_find``、
``AC_a11y_click``。GUI：**Accessibility** 分頁。


VLM（AI）元件定位
=================

當模板匹配與 Accessibility 都無法找到目標時，可用自然語言描述元件，
交給視覺語言模型回傳像素座標::

   import je_auto_control as ac

   x, y = ac.locate_by_description("綠色的 Submit 按鈕")
   ac.click_by_description(
       "Cookie 橫幅中的『全部接受』按鈕",
       screen_region=[0, 800, 1920, 1080],   # 可選：只在此區域搜尋
   )

後端（延遲載入，import ``je_auto_control`` 時不會引入）：

- Anthropic (``anthropic`` SDK，``ANTHROPIC_API_KEY``)
- OpenAI (``openai`` SDK，``OPENAI_API_KEY``)

環境變數（金鑰不會被記錄或寫入磁碟）：

- ``ANTHROPIC_API_KEY`` / ``OPENAI_API_KEY``
- ``AUTOCONTROL_VLM_BACKEND=anthropic|openai``
- ``AUTOCONTROL_VLM_MODEL=<model-id>``

Action-JSON 指令：``AC_vlm_locate``、``AC_vlm_click``。GUI：
**AI Locator** 分頁。


執行歷史 + 錯誤截圖附件
=======================

排程器、觸發器、熱鍵守護程序、REST API 與 GUI 手動回放的每一次執行
都會被寫入 ``~/.je_auto_control/history.db``（SQLite）。失敗時會自動
擷取螢幕截圖並附到該筆紀錄上::

   from je_auto_control import default_history_store

   for run in default_history_store.list_runs(limit=20):
       print(run.id, run.source, run.status, run.artifact_path)

截圖檔存於 ``~/.je_auto_control/artifacts/``，相關紀錄被 prune 或整個
歷史被清除時會一併刪除。GUI：**Run History** 分頁 — 雙擊截圖欄位可開
啟 OS 預覽。


OCR — 區域 dump 與 regex 搜尋
=============================

原本 OCR 模組只支援字串／精確比對，新增兩個 API 補強其他常見場景::

   import je_auto_control as ac

   # 把區域（或整個螢幕）內辨識到的所有文字傾倒出來
   for match in ac.read_text_in_region(region=[0, 0, 800, 600]):
       print(match.text, match.center, match.confidence)

   # Regex 搜尋 — 適合內容會變的文字（訂單編號、錯誤代碼）
   for match in ac.find_text_regex(r"Order#\d+"):
       print(match.text, match.center)

   # 也接受 compiled pattern 與 flags
   import re
   ac.find_text_regex(re.compile(r"foo", re.IGNORECASE))

Action-JSON 指令::

   [["AC_read_text_in_region", {"region": [0, 0, 800, 600]}]]
   [["AC_find_text_regex", {"pattern": "Order#\\d+"}]]

GUI：**OCR Reader** 分頁。可用既有的選取 overlay 圈出區域（留空則整螢幕），
設定語言／最低信心度後按 *抓取區域全部文字* 或 *用 regex 搜尋*。結果
以 JSON 列出，含文字、邊界框、信心度。


執行期變數與資料驅動流程控制
============================

過去 :mod:`script_vars.interpolate` 只能在執行前一次性把 ``${var}``
取代成靜態 mapping 中的值，腳本沒辦法在執行時修改狀態。``VariableScope``
是 executor 暴露給流程控制指令的執行期 mapping，讓它們能讀寫與
runtime interpolator 相同的容器。

executor 現在改成「每次呼叫」才解析 ``${var}`` placeholder（不會
事先攤平），所以巢狀的 ``body`` / ``then`` / ``else`` 清單會保留
placeholder，每次重複執行時重新繫結 — 因此 ``AC_for_each`` 走訪
list 時，body 內看到的就是當前的元素。

::

   import je_auto_control as ac
   from je_auto_control.utils.executor.action_executor import executor

   executor.execute_action([
       ["AC_set_var", {"name": "items", "value": ["alpha", "beta"]}],
       ["AC_set_var", {"name": "i", "value": 0}],
       ["AC_for_each", {
           "items": "${items}", "as": "name",
           "body": [
               ["AC_inc_var", {"name": "i"}],
               ["AC_if_var", {
                   "name": "i", "op": "ge", "value": 2,
                   "then": [["AC_break"]], "else": [],
               }],
           ],
       }],
   ])

``AC_if_var`` 的比較運算子：``eq``、``ne``、``lt``、``le``、``gt``、
``ge``、``contains``、``startswith``、``endswith``。

Action-JSON 指令：``AC_set_var``、``AC_get_var``、``AC_inc_var``、
``AC_if_var``、``AC_for_each``。

GUI：**Variables** 分頁 — 即時檢視 ``executor.variables``，可單筆設
定、JSON 整批 seed、清空，反映 ``AC_set_var`` / ``AC_for_each`` 在執
行期的變動。


LLM 動作規劃器
==============

把一段中／英文描述交給 LLM（預設 Anthropic Claude），生成驗證過的
``AC_*`` 動作清單。輸出採寬鬆解析（會剝 code fence、從散文中抽出
第一個 JSON array），再用 executor 同樣的 schema 驗證，所以結果可
以直接餵給 ``execute_action``::

   import je_auto_control as ac
   from je_auto_control.utils.executor.action_executor import executor

   actions = ac.plan_actions(
       "點擊 Submit 按鈕，然後輸入 'done' 並儲存",
       known_commands=executor.known_commands(),
   )
   executor.execute_action(actions)

   # 或者一行做完：
   ac.run_from_description("開記事本，輸入 hello", executor=executor)

後端選擇對齊 :mod:`vision.backends`：

- Anthropic（``anthropic`` SDK，``ANTHROPIC_API_KEY``）— 預設
- 用 ``AUTOCONTROL_LLM_BACKEND``、``AUTOCONTROL_LLM_MODEL`` 覆寫

Action-JSON 指令：``AC_llm_plan``、``AC_llm_run``。

GUI：**LLM Planner** 分頁。描述輸入框、``QThread`` 背景執行的 *Plan*
按鈕、預覽指令清單、以及 *Run plan* 按鈕 — 長時間呼叫不會卡 UI。


遠端桌面（Host + Viewer）
=========================

把本機畫面串流給別人看／控制，**或** 觀看並控制別人的機器 — 雙向都有
headless API 與 GUI 分頁。

協定是 raw TCP 上的長度前綴框架（沒有額外相依），先做一輪 HMAC-SHA256
challenge/response 認證；認證失敗的 viewer 在看到任何畫面前就被踢掉。
JPEG frame 依設定的 FPS／品質產生，透過共享 latest-frame slot 廣播給
通過認證的 viewers，慢的 viewer 只會掉 frame 而不會卡其他人。Viewer
輸入訊息是 JSON，host 端用允許清單驗證後才透過既有 mouse／keyboard
wrapper 派送。

Headless host（被別人遠端）::

   from je_auto_control import RemoteDesktopHost

   host = RemoteDesktopHost(
       token="hunter2",          # 共用密鑰（HMAC key）
       bind="127.0.0.1",         # 預設值；要對外請走 SSH tunnel
                                 # 或可信的 VPN
       port=0,                   # 0 = 自動指派
       fps=10, quality=70,
   )
   host.start()
   print("listening on", host.port, "viewers:", host.connected_clients)
   # ...
   host.stop()

Headless viewer（控制別人）::

   from je_auto_control import RemoteDesktopViewer

   viewer = RemoteDesktopViewer(
       host="10.0.0.5", port=51234, token="hunter2",
       on_frame=lambda jpeg_bytes: ...,   # 顯示或存檔
   )
   viewer.connect()
   viewer.send_input({"action": "mouse_move", "x": 100, "y": 200})
   viewer.send_input({"action": "type", "text": "hello"})
   viewer.disconnect()

輸入訊息允許清單（host 派送前驗證）：

- ``mouse_move`` ``{x, y}``
- ``mouse_click`` ``{x?, y?, button}``
- ``mouse_press`` / ``mouse_release`` ``{button}``
- ``mouse_scroll`` ``{x?, y?, amount}``
- ``key_press`` / ``key_release`` ``{keycode}``
- ``type`` ``{text}``
- ``ping``

Action-JSON 指令（使用 :mod:`utils.remote_desktop.registry` 的單例）::

   AC_start_remote_host       # token, bind, port, fps, quality, region
   AC_stop_remote_host
   AC_remote_host_status      # → {running, port, connected_clients}

   AC_remote_connect          # host, port, token, timeout
   AC_remote_disconnect
   AC_remote_viewer_status    # → {connected}
   AC_remote_send_input       # action: {...}

GUI：**Remote Desktop** 分頁，內含兩個子分頁。

- **Host**（被遠端的本機）— Token 欄位附 *產生* 按鈕（24 bytes
  URL-safe 隨機字串）、bind 位址安全提示、啟動／停止控制、即時刷新
  的 port + viewer 數量狀態列，以及底部 4fps 的預覽面板，讓被遠端
  的人看到 viewer 看到的畫面。
- **Viewer**（控制別人）— 位址／port／token 表單、*連線* / *中斷
  連線*，以及自繪的 frame display widget，會把 JPEG 等比縮放繪入。
  display 上的滑鼠／滾輪／鍵盤事件，會用最新 frame 的尺寸把 widget
  座標映射回原始遠端螢幕的像素座標，再用 ``INPUT`` 訊息送回。

.. warning::
   取得 host:port 與 token 的人，等同擁有本機完整滑鼠／鍵盤控制權。
   預設只綁 ``127.0.0.1``；要對外暴露請務必搭配 SSH tunnel 或 TLS
   前端。Token 是唯一防線 — 請當作密碼來保管。


遠端桌面 — 加密傳輸、音訊、剪貼簿、檔案傳輸
============================================

Host ID 握手
------------

每台 host 現在都有一個穩定的 9 位數字 ID，存在
``~/.je_auto_control/remote_host_id``，重啟後仍是同一個。ID 在
``AUTH_OK`` 訊息內回傳（只有通過認證的 viewer 才看得到），viewer 可
以指定 ``expected_host_id`` 驗證，避免「同樣位址但是別的程序」的
冒充攻擊::

   from je_auto_control import RemoteDesktopHost, RemoteDesktopViewer
   host = RemoteDesktopHost(token="tok")
   print(host.host_id)        # 例如 "123456789"

   viewer = RemoteDesktopViewer(
       host="10.0.0.5", port=51234, token="tok",
       expected_host_id="123456789",
   )
   viewer.connect()           # 不一致就拋 AuthenticationError

另外提供 ``format_host_id("123456789") == "123 456 789"`` 與
``parse_host_id("123 456 789") == "123456789"`` 助手。GUI 會顯示分組
過的 ID 並有 *複製* 按鈕；viewer 端的輸入欄接受常見的空白／破折號。

TLS
---

``RemoteDesktopHost`` 與 ``RemoteDesktopViewer`` 都接受
``ssl.SSLContext`` 參數。設定後，host 會把每條接受的連線在伺服器側
套上 TLS；viewer 在客戶端側套上。失敗的握手會被記錄並關閉，不會
進到 connected client 計數::

   import ssl
   ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
   ctx.load_cert_chain("cert.pem", "key.pem")
   host = RemoteDesktopHost(token="tok", ssl_context=ctx)

   client_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
   client_ctx.load_verify_locations("cert.pem")
   viewer = RemoteDesktopViewer(host=..., ssl_context=client_ctx)

自簽憑證 loopback 測試時，把 ``ctx.check_hostname = False`` 與
``ctx.verify_mode = ssl.CERT_NONE`` 設在 client context 上。GUI host
分頁有 TLS 憑證／私鑰的檔案選擇器；viewer 分頁有 *忽略憑證驗證* 的
checkbox 配自簽用。

WebSocket 傳輸
--------------

新增 ``WebSocketDesktopHost`` / ``WebSocketDesktopViewer``，用 RFC
6455 BINARY frame 傳同樣的 typed message。實作放在 in-tree（沒有
額外相依）；每個 application message 對應一個完整的 WS frame，所以
不需要重組機制。同一個 ``ssl_context`` 也是 ``wss://`` 的開關::

   from je_auto_control import (
       WebSocketDesktopHost, WebSocketDesktopViewer,
   )
   host = WebSocketDesktopHost(token="tok", ssl_context=ctx)   # wss://
   viewer = WebSocketDesktopViewer(
       host="example.com", port=443, token="tok",
       ssl_context=client_ctx, path="/rd",
   )

為什麼用 WS：穿牆友善、容易接反向代理、跟瀏覽器 viewer 相容。GUI
viewer 的傳輸下拉（*TCP* / *WebSocket* / *TLS* / *WSS*）會自動選對
應的 class。

音訊串流
--------

新增 ``AUDIO`` 訊息類型，攜帶 16-bit signed PCM 區塊（預設 16 kHz
mono，每塊 50 ms / 1600 bytes）。``sounddevice`` 為 optional 相依，
延遲載入；沒裝就 host 端音訊回報停用且整個 host 仍能運作::

   from je_auto_control.utils.remote_desktop import AudioCaptureConfig
   host = RemoteDesktopHost(
       token="tok",
       audio_config=AudioCaptureConfig(
           enabled=True, device=None,             # 預設 mic
           sample_rate=16000, channels=1,
       ),
   )

   from je_auto_control.utils.remote_desktop import AudioPlayer
   player = AudioPlayer(); player.start()
   viewer = RemoteDesktopViewer(host=..., on_audio=player.play)

Host 把每塊抓到的音訊透過每個 client 一個有上限的 deque（~2.5 秒緩
衝）廣播出去；慢的 viewer 只會丟掉舊的音訊塊，不會卡到大家的擷取
執行緒。如果要抓系統聲音（而非 mic），用 device index 指定 — Win
是 WASAPI loopback、Linux 是 PulseAudio monitor source、macOS 要
BlackHole 之類。GUI：Host 分頁的 *串流系統音訊*，Viewer 分頁的 *播
放接收的音訊*。

剪貼簿同步（文字 + 圖片）
-------------------------

新增 ``CLIPBOARD`` 訊息類型，payload 是 JSON envelope，方便日後加新
類別不用動到 framing：

* ``{"kind": "text", "text": "..."}``
* ``{"kind": "image", "format": "png", "data_b64": "..."}``

``utils/clipboard/clipboard.py`` 補上 ``get_clipboard_image`` /
``set_clipboard_image``；Windows 用 ctypes 寫 CF_DIB（Pillow 把 PNG
轉成 BMP 再去掉 14 byte file header 變成 DIB），Linux 走
``xclip -t image/png``，macOS get 走 Pillow ImageGrab、set 暫時拋
NotImplemented 等 PyObjC backend。同步是「明確呼叫」的（避免雙向
auto-poll 造成 paste 迴圈）::

   # Viewer 把本機剪貼簿送到 host
   viewer.send_clipboard_text("hello")
   viewer.send_clipboard_image(open("logo.png", "rb").read())

   # Host 把本機剪貼簿送到所有 viewers
   host.broadcast_clipboard_text("greetings")
   host.broadcast_clipboard_image(png_bytes)

   # Viewer 接收回 callback，自己決定要不要 paste
   viewer = RemoteDesktopViewer(
       host=..., on_clipboard=lambda kind, data: ...,
   )

GUI：Viewer 分頁有 *把本機剪貼簿文字送到 Host* 按鈕；host 收到後
透過上述 helpers 套用到本機剪貼簿。

檔案傳輸 + 進度
---------------

三個新訊息組成一次傳輸：

* ``FILE_BEGIN`` — JSON ``{transfer_id, dest_path, size}``
* ``FILE_CHUNK`` — 36-byte ASCII transfer id + 原始 payload
* ``FILE_END``   — JSON ``{transfer_id, status, error?}``

雙向、分塊（256 KiB / chunk）、**沒有總大小上限**、**沒有目的路徑
限制**（拿到 token 就視為信任使用者）。進度由兩端各自本地計算，不
需要額外的 wire 訊息::

   from je_auto_control.utils.remote_desktop import (
       FileReceiver, RemoteDesktopHost, RemoteDesktopViewer, send_file,
   )

   # Viewer 上傳到 host
   viewer.send_file("local.bin", "/tmp/uploaded.bin",
                    on_progress=lambda tid, done, total: print(done, total))

   # Host 下發到所有 viewer（viewer 需要設一個 FileReceiver 來收）
   viewer.set_file_receiver(FileReceiver(
       on_progress=..., on_complete=...,
   ))
   host.send_file_to_viewers("local.bin", "/tmp/from_host.bin")

GUI：*傳送檔案...* 按鈕開啟檔案選擇器 + 目的路徑提示，上傳跑在
``QThread`` 上，底下 ``QProgressBar`` 綁到 sender 的 progress 事
件。Frame display widget 也接受 dragEnter／drop 拖放本機檔案，丟進
去就走同一個流程上傳。

.. warning::
   路徑無限制、大小無上限。任何拿到 token 的人都能把任意檔案寫到
   任意位置（覆蓋 ``C:\\Windows\\System32\\*.dll`` 都可能），也能
   塞滿磁碟。Token 持有者必須等同信任使用者；要更嚴格的話請自行
   繼承 ``FileReceiver`` 在 ``handle_begin`` 內驗證 dest_path。


遠端桌面 — AnyDesk 風格彈出視窗
================================

Viewer 分頁不再把遠端畫面內嵌在面板裡 — viewer 認證成功後,會
另外開啟一個獨立的 :class:`RemoteScreenWindow` 顯示遠端桌面,
面板本身只剩下連線卡片 + 控制元件。關閉 popup 視窗的 ✕ 按鈕
會自動斷線,跟 AnyDesk 的 session 視窗體驗一致。

* 新增模組:``je_auto_control/gui/remote_desktop/remote_screen_window.py``
* 內部包一個 ``_FrameDisplay`` 並重新發送其 mouse / keyboard
  / drag-and-drop / annotation signals,所以面板仍然只需要訂閱
  單一 signal source。
* 視窗底部保留檔案傳輸進度條 / 標籤,沒有傳輸時隱藏。
* TCP ``_ViewerPanel`` 與 WebRTC ``_WebRTCViewerPanel`` 都會在
  connect / auth_ok 時開啟此視窗,在 disconnect / stop 時關閉。

設計動機
   原先的版面在垂直方向擠得很滿:畫面顯示 + 連線卡 + 折疊區
   + action row + stats + sparkline + 傳輸進度 + 狀態列全部
   往下堆。把遠端畫面拉到獨立視窗後,操作者多了一個真正的工作
   區,控制面板也不用再跟畫面爭空間。


遠端桌面 — 自適應的子分頁尺寸
==============================

每一個 Remote Desktop 子分頁外面都改包了一層
``QScrollArea`` 並設 ``setWidgetResizable(True)``。包裝邏輯
放在 ``gui/remote_desktop/tab.py``(``_wrap_in_scroll_area``
helper)。

* 視窗縮小時:出現垂直捲軸,WebRTC 那種密集分頁不會被切到。
* 視窗放大(4K)時:內部 panel 會跟著 viewport 橫向延展,連線
  卡與 session 表格會撐滿到右邊緣,不再縮成左上角一坨。
* 各 panel 底部仍有 ``addStretch(1)``,額外空間時內容會被推到
  上方,版面不會下垂。

WebRTC viewer 分頁裡比較少用的群組(Manual SDP、Remote Files、
Sync)也透過新的 ``_wrap_collapsed`` 包成預設摺疊的
``_CollapsibleSection``,初次顯示高度大約砍半。

WebRTC host 的 session 表格原本固定為 ``setMaximumHeight(140)``
,改成 ``setMinimumHeight(140)`` — 維持原本 140 px 的起始高度,
但在大螢幕上不再被卡住。


遠端桌面 — MCP 工具
====================

MCP server 現在把 GUI 用的 process-global remote-desktop
registry 包成工具,工廠函式為
``je_auto_control/utils/mcp_server/tools/_factories.py`` 內的
``remote_desktop_tools()``:

``ac_remote_host_start``
   啟動(或重啟)singleton TCP host,參數 ``token``、
   ``bind``、``port``、``fps``、``quality``、``max_clients``、
   ``host_id``,回傳
   ``{running, port, host_id, connected_clients}``。

``ac_remote_host_stop``
   關閉 host(沒在跑時為 no-op)。

``ac_remote_host_status``
   唯讀的 host 狀態快照,在 ``--readonly`` 模式下仍然可用。

``ac_remote_viewer_connect``
   把 singleton viewer 連到遠端 host,可選 ``expected_host_id``
   驗證 9 位數 ID。

``ac_remote_viewer_disconnect`` / ``ac_remote_viewer_status``
   關閉 / 觀察 viewer(status 為唯讀)。

``ac_remote_viewer_send_input``
   透過已連線的 viewer 把輸入動作 dict(``mouse_move``、
   ``mouse_press``、``mouse_release``、``mouse_scroll``、
   ``key_press``、``key_release``、``type``、``hotkey``)轉送到
   遠端 host。屬於 destructive,在 ``--readonly`` 模式下會被剔
   除。

這樣一來模型就能在不開 GUI 的情況下完成完整的遠端控制流程:

.. code-block:: text

   ac_remote_host_start(token="tok", bind="127.0.0.1", port=0)
     → {"running": true, "port": 51234, "host_id": "123456789",
        "connected_clients": 0}

   # … 切到另一台機器 …
   ac_remote_viewer_connect(host="10.0.0.5", port=51234, token="tok",
                            expected_host_id="123456789")
     → {"connected": true, "host_id": "123456789"}

   ac_remote_viewer_send_input(action={
       "action": "mouse_move", "x": 100, "y": 200,
   })
   ac_remote_viewer_send_input(action={
       "action": "type", "text": "hello",
   })

狀態類工具(``ac_remote_host_status``、
``ac_remote_viewer_status``)為唯讀,可以通過 MCP server 的
``--readonly`` 過濾;會修改狀態的工具都正確帶上
``destructiveHint: true``,MCP client 端可以據此跳出使用者確認。


驅動層輸入後端 — 驅動不接受 SendInput / XTest 的遊戲
=====================================================

預設的 Windows(SendInput)與 Linux(XTest)輸入路徑落在 user-mode
/ X-server 那一層;會用 ``GetRawInputData``(Win)或 ``evdev``
(Linux)直接讀 raw input 的遊戲會跳過這些層,完全忽略合成事件。
新增三個可選的後端可以解決這個問題。

Interception(Windows)
------------------------

Oblita 的 WHQL-signed Interception driver
(https://github.com/oblitum/Interception)在 HID 層注入鍵鼠事件,
OS 看到的就是「真實裝置」事件。

* 新增子套件:``je_auto_control/windows/interception/``
  (``_dll.py`` ctypes bindings + ``keyboard.py`` + ``mouse.py``)。
* 與 ``win32_ctype_keyboard_control`` /
  ``win32_ctype_mouse_control`` 公開介面完全一致 — wrapper 在啟動
  時直接換模組,呼叫端不需要任何修改。
* 透過 ``JE_AUTOCONTROL_WIN32_BACKEND=interception`` 啟用;若
  driver 沒裝,wrapper 會打 warning 並回到 SendInput,所以可以分
  階段佈署。
* 用 ``JE_AUTOCONTROL_INTERCEPTION_KEYBOARD`` /
  ``JE_AUTOCONTROL_INTERCEPTION_MOUSE`` 覆寫 device id(預設
  ``1`` / ``11``)。

操作步驟::

   # 1. 以系統管理員身份安裝 driver(一次性,需要重開機)
   install-interception.exe /install

   # 2. 告訴 AutoControl 走這條路
   setx JE_AUTOCONTROL_WIN32_BACKEND interception

uinput(Linux)
----------------

kernel 自帶的合成輸入閘道。透過 ``/dev/uinput`` 送出的事件會被
建立成一個全新的 HID 裝置,任何讀 ``evdev`` 的程式(包含大部分
遊戲與 SDL2 app)都會視為真實輸入。

* 新增子套件:``je_auto_control/linux_with_x11/uinput/``
  (``_device.py`` 直接用 ctypes + ioctl 包 ``/dev/uinput`` +
  ``keyboard.py`` + ``mouse.py``)。
* 無第三方依賴 — 全程 ctypes + ioctl。
* 透過 ``JE_AUTOCONTROL_LINUX_BACKEND=uinput`` 啟用;若
  ``/dev/uinput`` 沒寫入權限,會 warning 後回退到 XTest。

操作步驟::

   # 載入 kernel module
   sudo modprobe uinput

   # 一次性測試:直接放寬權限
   sudo chmod 666 /dev/uinput

   # 持續性權限,寫一個 udev rule:
   echo 'KERNEL=="uinput", GROUP="input", MODE="0660"' \
     | sudo tee /etc/udev/rules.d/99-autocontrol-uinput.rules
   sudo udevadm control --reload && sudo udevadm trigger
   sudo usermod -aG input $USER  # 重新登入後生效

   # 啟用後端
   export JE_AUTOCONTROL_LINUX_BACKEND=uinput

ViGEm 虛擬手把(Windows)
-------------------------

針對「完全不吃鍵鼠、只認手把」的遊戲,可以用 ViGEmBus 建立一個虛
擬 Xbox 360 / DualShock 4 控制器;AutoControl 透過第三方 ``vgamepad``
套件來驅動它。

* 新增模組:``je_auto_control/utils/gamepad/`` 提供友善的
  ``VirtualGamepad`` API(字串名稱的 button / dpad / stick /
  trigger,支援 context manager)。
* Headless::

     from je_auto_control import VirtualGamepad
     with VirtualGamepad() as pad:
         pad.click_button("a")               # A 鍵
         pad.set_left_stick(16000, 0)        # int16 stick 偏移
         pad.set_right_trigger(255)          # 0..255 力度
         pad.set_dpad("up")                  # 按住方向鍵上
         pad.update()                        # 把狀態 flush 給 driver

* Executor 指令:``AC_gamepad_press``、``AC_gamepad_release``、
  ``AC_gamepad_click``、``AC_gamepad_dpad``、
  ``AC_gamepad_left_stick`` / ``_right_stick``、
  ``AC_gamepad_left_trigger`` / ``_right_trigger``,以及
  ``AC_gamepad_reset``。

* MCP 工具:同名加上 ``ac_`` 前綴(``ac_gamepad_press``、
  ``ac_gamepad_left_stick`` …),所以模型可以透過 MCP 玩只支援
  手把的遊戲。

操作步驟::

   # 1. 安裝 ViGEmBus driver(一次性,需要重開機)
   #    https://github.com/nefarius/ViGEmBus/releases
   # 2. 安裝 Python wrapper:
   pip install vgamepad

反作弊注意事項
---------------

驅動層注入比 SendInput / XTest 更難偵測,但帶 kernel-mode driver
的反作弊(Vanguard、有 kernel module 的 Easy Anti-Cheat、
BattlEye)依然可以列舉 Interception / ViGEmBus / 新建立的 uinput
裝置然後拒絕啟動。

這三個後端針對的是合法用途 — 輔助科技、遊戲 GUI 測試、從 headless
環境控制執行遊戲的遠端機器 — **不是** 通用反作弊繞過工具。
