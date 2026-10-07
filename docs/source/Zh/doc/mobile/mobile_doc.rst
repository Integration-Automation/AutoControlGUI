行動裝置 context 與所有權
================================

Beta ``je_auto_control.api.mobile`` 匯出 ``DeviceContext``、``DeviceSession``、
``DeviceSessionError``、``open_device`` 與 ``probe_device_contexts``；
歷史門面同步匯出這五個名稱。

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
Unicode、手勢、App lifecycle 依後續 E task 交付。
