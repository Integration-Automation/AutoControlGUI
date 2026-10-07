行動裝置 context 與所有權
================================

Beta ``je_auto_control.api.mobile`` 匯出 ``DeviceContext``、``DeviceSession``、
``DeviceSessionError``、``DeviceFrame``、``Gesture``、``open_device``、
``probe_device_contexts``、``mobile_capture``、``mobile_gesture`` 與 ``mobile_type_text``；
歷史門面同步匯出這些名稱。

明確所有權
----------

.. code-block:: python

   from je_auto_control.api.mobile import DeviceContext, open_device
   from je_auto_control.ios.input import tap

   context = DeviceContext('ios', 'phone-a', target='http://127.0.0.1:8100', timeout_s=5)
   with open_device(context) as session:
       with session.bind():
           tap(120, 200)  # 明確送出裝置輸入；必須先配置 WDA。

Android ``DeviceContext('android', 'emulator-5554')`` 預設以該 serial 為 target；
``adb_path`` 可指定 Platform Tools。iOS 必須提供明確的 HTTP/HTTPS/usbmux WDA URL，
不接受 URL 帳密、query 或 fragment。``device_id`` 是報告標籤，``target`` 是實際
serial／endpoint。identity/config 凍結；``timeout_s`` 須為正的有限數且不超過 300 秒。

建立 session 不會連線。``connected`` 僅代表邏輯 owner 仍開啟，不代表裝置可達。
``bind()`` 選擇當前執行情境的 owner；離開時還原，包含巢狀 binding 及例外。
binding 外的既有 helper 保留相容的程序預設；binding 內若 owner 已關閉、
傳入外來 client 或 serial/URL override 不符，會拋出 ``DeviceSessionError``，不改投其他裝置。

``cancel()`` 與可重複 ``close()`` 只撤銷此 owner。已送出的請求可能在裝置上完成，
但取消後的結果會被拒絕。等待中的 SDK constructor 不阻擋取消；它稍後建立的
自有 Android helper 會被回收。只停止此 uiautomator2 client 啟動的 helper，並移除
SDK 的退出回呼；全域 ADB server 及既存服務仍各有 owner。
關閉 WDA root client 不會刪除借用的 server-side app session。

ADB subprocess、uiautomator2 RPC/shell/device-wait 與 WDA HTTP 的每次請求逾時
各自受 context 限制，不修改 SDK 全域值。SDK bootstrap／原生 retry 的整體截止時間
尚未完成實機驗證；裝置恢復仍列驗收。選用 SDK 錯誤保留 framework exception 邊界。
實作參考：`uiautomator2 core <https://github.com/openatx/uiautomator2/blob/master/uiautomator2/core.py>`_
與 `facebook-wda client <https://github.com/openatx/facebook-wda/blob/master/wda/__init__.py>`_。

裝置矩陣與被動查詢
------------------

``run_on_devices``／``AC_run_device_matrix`` 為每個 worker 綁定獨立 owner；
未指定 target 的 mobile 命令也使用該 worker 的 serial/URL。
spec 支援 ``platform``、``serial``/``url``（或 ``target``）、``device_id``、
``timeout_s`` 與 ``adb_path``。重複配置的 target 在任何輸入前拒絕；
不同 endpoint alias 是否指向同一台實機，無法自動判定。
worker 成功或失敗皆關閉自有 session，報告各自的結果。

.. code-block:: json

   ["AC_probe_mobile_devices", {"devices": [
       {"platform": "android", "serial": "emulator-5554"},
       {"platform": "ios", "url": "http://127.0.0.1:8100"}
   ]}]

Python probe 與 MCP ``ac_probe_mobile_devices`` 回傳 JSON 依賴證據，不載入 SDK、
掃描裝置、連線或輸入。找到依賴時回報 ``needs_permission``，reason 明確說明
尚未驗證 connectivity／authorization；缺少依賴則為 ``needs_dependency``。
這是被動觀察。遠端查詢需 host admin；read-only annotation 不授予權限。

Device Matrix 的 Actions 選單提供「查詢行動裝置依賴」與「執行矩陣」，查詢結果
顯示為 JSON；矩陣在背景 worker 執行，編輯器及事件迴圈保持回應。
Script Builder 使用同一 JSON 指令。``examples/mobile_contexts.py`` 示範被動查詢及
不操作硬體的矩陣；原生 Android/emulator 與 remote WDA 驗收仍列 Progress.md。
專用 mobile 面板依 E4 交付。

裝置輸入與不可變畫面
--------------------

``session.type_text('測試 café 🙂')`` 使用 uiautomator2 Unicode IME／剪貼簿
或 WDA Unicode keys。缺少 SDK 時會顯示相依資訊，不退回 ``adb input text``；
舊 ADB ASCII 入口現在會在輸入前拒絕非 ASCII。SDK 可能設定 IME／剪貼簿，
原生恢復及焦點欄位 round-trip 仍需驗收。

``Gesture`` 驗證種類、座標及持續時間。tap／long_press 使用一點、drag／swipe
使用兩點、pinch 使用四點（start1、start2、end1、end2），全部是原生輸入座標。
時間不能超過 session request timeout。Android 使用 SDK click／long_click／
drag／swipe 及雙指 RPC；WDA 使用原生 touch，雙指操作需 W3C ``/actions``。
不支援的 endpoint 會失敗並保留框架例外。WDA swipe duration 是起點按住時間，
Android 則是移動時間。

``session.capture()`` 回傳不可變 ``DeviceFrame``，帶 PNG、context、``pixel_size``、
``point_size`` 及順時鐘 orientation（0／90／180／270）。Android 輸入是原生 pixel；
iOS 是 UIKit point。既有 iOS 觸控、viewport 及樹定位保留數值行為，文件修正單位。
擷取在原生截圖前後讀取 geometry，拒絕變動、零尺寸、未知方向或長寬比不符。
WDA 使用原始 viewport 查詢，避開 SDK window_size 可能關閉 alert／開啟 Settings
的 fallback。

.. code-block:: python

   from je_auto_control.api.mobile import DeviceContext, Gesture, open_device

   context = DeviceContext('ios', 'phone-a', target='http://127.0.0.1:8100')
   with open_device(context) as session:
       frame = session.capture()
       point = frame.pixel_to_point((200, 100))
       session.perform(Gesture('tap', (point,), frame=frame))

``pixel_to_point`` 依截圖時的 viewport 換算，並反轉額外顯示旋轉。
``frame.rotated(90)`` 產生順時鐘旋轉的新畫面，保留原生座標關係。
Gesture 附上 ``frame`` 時，輸入前會檢查 owner 及當前 geometry；方向改變會拒絕
舊座標。裝置仍可能在最後一次 metadata 讀取後旋轉，原生 race／恢復需另驗收。
``examples/mobile_frame_mapping.py`` 示範 Retina／旋轉換算，不連線也不輸入。

``frame.ocr(backend=engine)`` 共用這份 bytes，回傳 image-local OCR 結果。
``frame.locate(TemplateFrameStrategy(...))``／``VLMFrameStrategy`` 回傳 frame pixel
預測，再以 ``pixel_to_point`` 換算。``session.bind()`` 內的 ``self_heal_locate``／
``self_heal_click`` 讓 template 與 VLM 共用一次裝置擷取，保留 frame hash 證據，
不呼叫桌面擷取／輸入。self-heal click 會附上 frame，再次檢查 geometry。
mobile 全畫面搜尋拒絕桌面 ``screen_region``；touch 僅支援 ``mouse_left``。

JSON 動作、MCP 與 Builder
-------------------------

``mobile_capture(file_path, device=None)``、``mobile_gesture(gesture, device=None)``
及 ``mobile_type_text(text, device=None)`` 對應 ``AC_mobile_*``／MCP ``ac_mobile_*``。
``device`` 是 matrix 格式物件；省略時必須有啟用中的 matrix owner，外來 device
override 會拒絕。capture 寫入經 root 檢查的 PNG 並回傳 geometry。文字回應不複誦；
action／journal 遮罩具名及位置文字參數，journal 保留 secret reference。
三項遠端服務均需 host admin。

.. code-block:: json

   ["AC_run_device_matrix", {"devices": [
     {"platform": "android", "serial": "emulator-5554"}
   ], "actions": [
     ["AC_mobile_type_text", {"text": "測試 café 🙂"}],
     ["AC_mobile_gesture", {"gesture": {"kind": "long_press", "points": [[120, 200]], "duration_s": 1}}],
     ["AC_mobile_capture", {"file_path": "phone.png"}]
   ]}]

使用 Device Matrix Actions 的 Run matrix，或 Script Builder Mobile 類別。
受控 SDK 契約不代表 emulator／WDA 已實測。官方參考：
`uiautomator2 input <https://github.com/openatx/uiautomator2/blob/master/uiautomator2/__init__.py>`_、
`雙指 RPC <https://github.com/openatx/uiautomator2/blob/master/uiautomator2/_selector.py>`_、
`WDA SDK <https://github.com/openatx/facebook-wda/blob/master/wda/__init__.py>`_ 與
`WDA W3C actions <https://github.com/appium/WebDriverAgent/blob/master/WebDriverAgentLib/Commands/FBTouchActionCommands.m>`_。

App 狀態與可選擴充
------------------

Beta API／門面另匯出 ``AppState``、``app_state``、``launch_app``、``wait_for_app``、
``stop_app``、``handle_mobile_alert``、``MobileExtension``、``MobileExtensionSpec``、
``run_mobile_extension``、``mobile_app``、``mobile_alert`` 與 ``mobile_extension_action``。

.. code-block:: python

   from je_auto_control.api.mobile import launch_app, stop_app, wait_for_app

   with open_device(context) as session:
       observed = launch_app(session, 'com.example.demo')
       observed = wait_for_app(session, 'com.example.demo', timeout_s=5)
       observed = stop_app(session, 'com.example.demo')

Android 使用 owner 的 ADB launch／pidof／force-stop，以程序存在代表 running。
iOS 建立並凍結新的 WDA session ID，避開 SDK 全域鎖、自動重試及 auto-unlock。
XCTest 0／1／2–4 分別對應 not_installed／not_running／running；連線失敗代表
未知狀態，不假稱 not_running。輪詢有期限且可取消，第一次 WDA 建立也使用呼叫者
剩餘預算；遺失輸入回覆不自動重送。

刪除 WDA session 可能終止它的 App，只刪除明確認領的 ID，保留借用 root session。
失敗清理（含取消後才完成的建立）可重試 ``session.close()``。
Android 關閉連線仍讓 App 執行，需明確 ``stop_app``。
iOS ``handle_mobile_alert`` 可 accept／dismiss；Android 無通用 alert endpoint，
需指定 UI-tree selector。原生授權及恢復仍列 H3。

在首次使用前呼叫 ``session.configure_extension(MobileExtensionSpec(name, version,
capabilities, factory))`` 配置被動資訊及延遲 factory(context, guard)。
factory 必須建立單一 owner 的 adapter、在 I/O 前後檢查 guard、使用 context.timeout_s
並清理自己的資源，不共用原生 client。查詢能力不執行 factory；未宣告的操作回報
unsupported，缺少可選 adapter 回報 needs_dependency 及修復方式。

``MobileExtension`` 定義 install(file_path)、files(action, local_path, remote_path)、
clipboard(text=None)、recording(file_path, duration_s)、close()。
Android 原生提供 ADB APK 安裝、push/pull 與 SDK Unicode 剪貼簿；iOS 對應功能及
雙平台錄影需配置擁有資源的 adapter，不將 ADB 假借到 iOS。
本機檔案檢查允許根目錄；遠端路徑需絕對 ASCII 路徑，不含 shell 字元或上層跳脫。

.. code-block:: json

   [
     ["AC_mobile_app", {"action": "launch", "app_id": "com.example.demo"}],
     ["AC_mobile_extension", {"operation": "clipboard", "options": {"text": "測試 café 🙂"}}],
     ["AC_mobile_app", {"action": "stop", "app_id": "com.example.demo"}]
   ]

以上使用 active matrix owner，或提供明確 device 物件。
``AC_mobile_alert`` 接受 action accept／dismiss；MCP ac_mobile_app/alert/extension、
Builder 與 Device Matrix Actions 共用服務。遠端需 MANAGE_HOSTS；自動日誌遮罩
extension options／結果。``examples/mobile_app_lifecycle.py`` 預設被動，
只有 --run 才啟停 App。受控 adapter 測試驗證分派及生命週期；emulator、簽章、
真實 WDA 及實體錄影驗收仍列 H3。

WDA App 操作需專用閒置 endpoint。有時限的 status 檢查會在建立前拒絕既有或缺少 ownership 資訊的狀態；本程序 lease 保護同 URL 的 pending／active owner。WDA 建立會取代既有 session，外部 client 及別名仍需操作上維持專用。建立回覆未知時保持未知狀態，明確重試前需檢查原生狀態。
