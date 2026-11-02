================================
Android 與 iOS 裝置
================================

AutoControl 透過 ``adb``\ （加上選用的 ``uiautomator2`` daemon）操作 Android 裝置，
透過 WebDriverAgent（``facebook-wda`` 用戶端）操作 iOS 裝置。兩者都是選用相依：
用到才匯入，所以沒裝的主機仍然可以匯入本套件。

.. warning::

   **尚未在實機上驗證。** 本頁所有功能都是對著假的 ADB 主機與假的 WebDriverAgent
   用戶端（``test/unit_test/headless/_mobile_doubles.py``）開發與測試的。這些測試
   證明 AutoControl 送出的指令就是它打算送的指令；它們不能證明真的模擬器、手機或
   WebDriverAgent 版本會接受這些指令。沒有任何 CI 工作接上裝置。下方的設定說明是
   預期的流程，不是測過的流程。

裝置 context 與 session
=======================

:class:`DeviceContext` 是一台裝置不可變的身分，\ :func:`open_device` 把它變成
:class:`DeviceSession`\ ——擁有自己的傳輸層、逾時與取消訊號::

    from je_auto_control import DeviceContext, open_device

    left = open_device(DeviceContext("android", "emulator-5554"))
    right = open_device(DeviceContext("ios", "http://192.168.1.20:8100"))

    print(left.capabilities()["unicode_text"].state)
    left.cancel()            # 只停 ``left``
    assert right.connected
    right.close()

``device_id`` 在 Android 是 adb serial，在 iOS 是 WebDriverAgent 的 URL。
開 session 不會送出任何東西：adb 用戶端或 WDA 用戶端在第一次操作時才建立，
所以沒有 ``adb`` 的主機也能開 session。

* ``cancel()`` 只停一個 session。正在等裝置回應的呼叫端會立刻收到
  ``DeviceCancelledError``\ ，之後不再送出任何東西。已經送往裝置的呼叫收不回來。
* 超過 ``timeout_s``\ （預設 30 秒）的呼叫會丟 ``DeviceTimeoutError``
  **並關閉 session**\ ：裝置處於沒人觀察到的狀態，所以下一步會被拒絕
  （``DeviceClosedError``\ ），而不是疊上去送。要繼續請開新的 session。
* ``close()`` 釋放 session 自己建立的東西。呼叫端交進來的用戶端
  （``open_device(context, adb=...)`` / ``device=...``\ ）只借用、不擁有。
  關閉 iOS session 不會終止 App，也不會刪除遠端的 WDA session。

同一個行程操作多台裝置
----------------------

``use_device(session)`` 在目前的執行緒綁定一個 session；沒寫 ``serial`` / ``url``
的行動指令就會打到它。Device matrix 對每台裝置都這樣做，所以兩個 worker
不會因為省略位址而打到對方的裝置::

    from je_auto_control import run_on_devices

    run_on_devices(
        actions=[["AC_android_tap", {"x": 100, "y": 200}]],
        devices=[{"platform": "android", "serial": "emulator-5554"},
                 {"platform": "android", "serial": "emulator-5556"}],
    )

步驟裡明確寫出的 ``serial`` / ``url`` 仍然優先於綁定的裝置。舊有的行程層級
helper（``default_ui_device()``\ 、\ ``default_ios_device()``\ 、executor 的
per-serial adb 快取）在單一裝置腳本裡照常運作；matrix 不再碰它們。

能力
====

``session.capabilities()`` 對每項功能回傳一個 :class:`DeviceCapability`\ ——
``input``\ 、\ ``unicode_text``\ 、\ ``multi_touch``\ 、\ ``screenshot``\ 、
``ui_tree``\ 、\ ``app_lifecycle``\ 、\ ``alerts``\ 、\ ``install``\ 、\ ``files``\ 、
``clipboard``\ 、\ ``recording``\ ——每一項是下列四種狀態之一：

.. list-table::
   :header-rows: 1
   :widths: 25 75

   * - 狀態
     - 意義
   * - ``available``
     - 現在可用。
   * - ``needs_permission``
     - 裝置拒絕了這台主機（尚未授權 USB 偵錯）。
   * - ``needs_dependency``
     - 缺了東西；\ ``reason`` 會指出是什麼（``adb``\ 、\ ``uiautomator2``\ 、
       ``facebook-wda``\ 、連不上的 WDA 端點、沒接上的裝置、主機端的 adapter）。
   * - ``unsupported``
     - 後端做不到；\ ``alternative`` 說明可以改用什麼。

探測不會送出任何輸入。Android 只執行 ``adb devices`` 並讀一個設定值；
iOS 只請求 WDA 的 ``/status``\ 。

錯誤
====

不論是哪個後端丟的，所有錯誤都繼承 ``DeviceError``\ （它是
``AutoControlException``\ ，也是 ``RuntimeError``\ ）：

.. list-table::
   :header-rows: 1
   :widths: 35 65

   * - 錯誤
     - 何時丟出
   * - ``DeviceUnavailableError``
     - 缺少 ``adb`` / SDK，或連不上裝置或 WDA 端點（``AdbNotAvailable``\ 、
       ``AdbDeviceMissingError``\ 、\ ``UIAutomatorUnavailableError``\ 、
       ``IOSUnavailableError``\ ）。
   * - ``DevicePermissionError``
     - 裝置尚未授權這台主機（``AdbUnauthorizedError``\ ）。
   * - ``DeviceTimeoutError``
     - 呼叫超過逾時（``AdbTimeoutError``\ ）；同時也是 ``TimeoutError``\ 。
   * - ``DeviceCancelledError``
     - session 已被取消。
   * - ``DeviceClosedError``
     - session 已關閉，或因逾時而失效。
   * - ``DeviceUnsupportedError``
     - 後端做不到所要求的事；帶有 ``reason`` 與 ``alternative``\ 。

``AdbError`` 等既有名稱照樣丟出，既有的 ``except`` 也照樣接得到；
它們現在共用這個基底。

文字
====

``session.type_text(text)`` 要嘛把文字送到，要嘛丟例外；裝置沒收到的文字
絕不會回報成功。

**Android。** ``adb shell input text`` 只能送可列印的 ASCII。其他字元會被丟掉
或弄亂，每個 ``%s`` 會變成空白，而且不管怎樣結束碼都是 0。所以：

1. 不含字面 ``%s`` 的可列印 ASCII 走 ``input text``\ 。
2. 其他文字在裝置選用 `ADBKeyBoard <https://github.com/senzhk/ADBKeyBoard>`_
   輸入法時交給它（``adb shell ime set com.android.adbkeyboard/.AdbIME``\ ）。
3. 否則在主機裝有 ``uiautomator2`` 時交給它。
4. 兩者都沒有就丟 ``AdbUnsupportedError``\ （屬於 ``DeviceUnsupportedError``\ ），
   什麼都不送。

``AC_android_text`` 走同一條路。\ ``AdbClient.text()`` 本身現在也會拒絕
``input text`` 送不了的文字，而不是照送。

.. note::

   ADBKeyBoard 的 broadcast 不論有沒有輸入法接收，回傳結果都一樣，所以「送達」
   是從輸入法已被選用推斷的，並非由裝置確認。

**iOS。** WebDriverAgent 的按鍵端點可以送 Unicode；文字原樣傳遞。

手勢
====

``session.perform(gesture)`` 接受五種 frozen dataclass 之一，全部使用裝置的
輸入座標：

.. list-table::
   :header-rows: 1
   :widths: 22 39 39

   * - 手勢
     - Android
     - iOS
   * - ``Tap(x, y)``
     - ``input tap``
     - WDA tap
   * - ``LongPress(x, y, duration_s)``
     - 不移動的 ``input swipe``
     - WDA touch-and-hold
   * - ``Swipe(x1, y1, x2, y2, duration_s)``
     - ``input swipe``
     - WDA drag
   * - ``Drag(x1, y1, x2, y2, hold_s, duration_s)``
     - ``input draganddrop``\ ；裝置的 ``input`` 沒有這個子指令時退回
       ``uiautomator2``
     - WDA drag，\ ``hold_s`` 是按住的時間
   * - ``Pinch(x, y, scale, duration_s, span)``
     - ``uiautomator2`` 的雙指手勢；\ ``adb shell input`` 只有一個觸控點，
       沒裝的話丟 ``DeviceUnsupportedError``
     - 對最前景的 App 做 pinch。WDA 的 pinch 對象是元素而不是座標，所以
       ``x`` / ``y`` / ``span`` 會被忽略。

畫面與座標
==========

``session.capture()`` 回傳 :class:`DeviceFrame`\ ：轉正後的截圖，加上輸入座標
空間的大小。

* **iOS** 的 WebDriverAgent 收的是 *point*\ 、回的是 *pixel*\ （多數 iPhone 是
  一個 point 三個 pixel）。\ ``frame.pixel_to_point(x, y)`` 負責換算；把截圖的
  pixel 當成 point 去點會點錯位置。
* **Android** 的 ``screencap`` 與 ``input tap`` 共用同一個座標空間，換算是恆等
  的。這一點是對照 ``wm size`` 與顯示旋轉檢查出來的，不是假設。
* 顯示已旋轉、截圖卻以面板原生方向回來時，會先轉正再做任何定位。要往哪邊轉
  （\ ``landscape_left`` 轉 270 度、\ ``landscape_right`` 轉 90 度）依據的是兩個
  平台文件記載的慣例，沒有在實機上確認過。上下顛倒的顯示無法從影像形狀判斷，
  視為已經是正的。

定位
----

定位直接在 frame 上做——不會去截主機的桌面——而且答案一律是裝置的 point，
可以直接交給手勢::

    from je_auto_control import Tap, self_heal_locate

    frame = session.capture()
    session.perform(Tap(*frame.locate_image("login_button.png")))

    point = frame.locate_text("Sign in")              # OCR，找不到回 None
    point = frame.locate_description("the blue button")   # VLM，找不到回 None

    outcome = self_heal_locate(template_path="login_button.png",
                               description="the login button", frame=frame)
    if outcome.found:
        session.perform(Tap(*outcome.coordinates))

``self_heal_locate(..., frame=frame)`` 跑的是同一套「先樣板、後 VLM」的退路，
寫的也是同一份 heal log；\ ``screen_region`` 不適用於 frame。
``self_heal_click`` 仍然是點桌面的滑鼠，不接受 frame。

App 生命週期與 alert
====================

::

    from je_auto_control import (
        AppState, accept_alert, launch_app, stop_app, wait_for_app,
    )

    launch_app(session, "com.example.shop")          # Android package / iOS bundle id
    wait_for_app(session, "com.example.shop", timeout_s=15)
    accept_alert(session)
    assert stop_app(session, "com.example.shop") == AppState.NOT_RUNNING

``AppState`` 是 ``not_installed``\ 、\ ``not_running``\ 、\ ``background`` 或
``foreground``\ ，可以直接與這些字串比較。

.. list-table::
   :header-rows: 1
   :widths: 22 39 39

   * - 呼叫
     - Android
     - iOS
   * - ``launch_app``
     - ``monkey -p <package> -c android.intent.category.LAUNCHER 1``\ ；
       id 寫成 ``package/activity`` 時用 ``am start -n``
     - WDA app launch
   * - ``stop_app``
     - ``am force-stop``
     - WDA app terminate
   * - ``app_state``
     - ``pidof``\ 、\ ``pm path``\ ，以及 ``dumpsys`` 裡的 resumed activity
     - WDA app state。WDA 把沒安裝的 App 回報成沒在執行，所以不會回傳
       ``not_installed``\ 。
   * - ``wait_for_app``
     - 輪詢 ``app_state`` 直到逾時，逾時丟 ``DeviceTimeoutError``\ ；
       取消 session 會結束等待。
     - 相同。
   * - ``accept_alert`` / ``dismiss_alert``
     - 透過 ``uiautomator2`` 按下標準對話框或權限按鈕（``android:id/button1`` /
       ``button2``\ 、permission controller 的允許／拒絕按鈕）。沒有
       ``uiautomator2`` 時丟 ``DeviceUnsupportedError``\ ；請改在 frame 裡定位
       按鈕再點它。
     - WDA alert accept / dismiss；回傳 alert 的文字。

沒有 alert 時兩者都丟 ``AlertNotPresentError``\ 。App id 在送進裝置 shell 之前
會先驗證。

Device matrix 的裝置規格可以寫 ``app_id``\ ：第一個步驟之前會啟動 App 並等它到
前景，步驟結束後不論成功與否都會停止它（\ ``"keep_app": true`` 則保留執行）。
``DeviceResult.app_state`` 記錄它最後的狀態。

安裝、檔案、剪貼簿、錄影
========================

這些是後端可能沒有的功能。\ ``mobile_extension(session)`` 回傳
:class:`MobileExtension`\ ；\ ``capability(feature)`` 說明 ``install``\ 、
``files``\ 、\ ``clipboard``\ 、\ ``recording`` 各自能不能用，缺少的功能呼叫時
會丟 ``DeviceUnsupportedError`` 並附上原因::

    from je_auto_control import mobile_extension

    extension = mobile_extension(session)
    if extension.capability("recording").available:
        extension.start_recording(time_limit_s=60)
        ...
        extension.stop_recording("run.mp4")

.. list-table::
   :header-rows: 1
   :widths: 18 41 41

   * - 功能
     - Android
     - iOS（WebDriverAgent）
   * - ``install``
     - ``adb install -r``
     - ``needs_dependency``\ ：WDA 沒有安裝的端點。
   * - ``files``
     - ``adb push`` / ``adb pull``
     - ``needs_dependency``\ ：WDA 沒有檔案的端點。
   * - ``clipboard``
     - 透過 ``uiautomator2``\ ；沒裝時是 ``needs_dependency``\ ，因為新版
       Android 上 ``adb`` 碰不到剪貼簿。
     - 只能寫入。WDA 只在 WDA 自己位於前景時才允許讀取；\ ``facebook-wda``
       版本沒有 ``get_clipboard`` 時丟 ``DeviceUnsupportedError``\ 。
   * - ``recording``
     - ``adb shell screenrecord``\ （最長 180 秒），以 ``SIGINT`` 停止好讓檔案
       收尾，再拉回主機並從裝置刪除。錄影是裝置端的狀態：關閉 session 不會
       停止它，只有 ``stop_recording`` 會。
     - ``needs_dependency``\ ：WDA 沒有錄影的端點。

iOS 裝置不會用到任何 ``adb`` 的東西。要補上 iOS 缺少的功能，請針對主機端工具
註冊 adapter；它會先被詢問，它沒提供的部分仍由 WebDriverAgent 負責::

    from je_auto_control import register_mobile_extension

    register_mobile_extension("ios", lambda session: MyTideviceAdapter(session))

AutoControl 本身沒有附帶這樣的 adapter。

指令、MCP 工具、Script Builder、GUI
===================================

每個行動指令只描述一次，就在 ``je_auto_control.MOBILE_COMMANDS``
（``wrapper/mobile_commands.py``\ ）。Executor 的 ``AC_android_*`` / ``AC_ios_*``
指令、\ ``ac_android_*`` / ``ac_ios_*`` MCP 工具、Script Builder 的 **Android** 與
**iOS** 分類，以及 **Mobile** 分頁，全部由這張表產生，所以不會有指令只出現在
某一個介面、卻在另一個介面缺席（缺了 ``test_mobile_surface_parity.py`` 就會失敗）。

每個指令都接受選用的位址——Android 是 ``serial`` 與 ``adb_path``\ ，iOS 是
``url``\ ——以及 ``device_timeout_s``\ 。沒寫位址時會跑在 ``use_device`` 綁定的
session（device matrix 的 worker）上，否則跑在後端的預設裝置上。不認得的參數
會被拒絕。

.. list-table::
   :header-rows: 1
   :widths: 24 38 38

   * - 分組
     - Android
     - iOS
   * - 裝置
     - ``AC_android_device_info``\ 、\ ``AC_android_screen_info``\ 、
       ``AC_android_list_devices``
     - ``AC_ios_device_info``\ 、\ ``AC_ios_screen_info``
   * - 輸入
     - ``AC_android_tap``\ 、\ ``_swipe``\ 、\ ``_long_press``\ 、\ ``_drag``\ 、
       ``_pinch``\ 、\ ``_key``\ 、\ ``_text``\ 、\ ``_type_text``
     - ``AC_ios_tap``\ 、\ ``_swipe``\ 、\ ``_long_press``\ 、\ ``_drag``\ 、
       ``_pinch``\ 、\ ``_press_key``\ 、\ ``_type``
   * - 畫面與定位
     - ``AC_android_screenshot``\ 、\ ``_find_image``\ 、\ ``_find_text``\ 、
       ``_find_by_description``\ 、\ ``_self_heal``\ 、\ ``_find_element``\ 、
       ``_click_element``\ 、\ ``_dump_hierarchy``
     - ``AC_ios_screenshot``\ 、\ ``_find_image``\ 、\ ``_find_text``\ 、
       ``_find_by_description``\ 、\ ``_self_heal``\ 、\ ``_find_element``\ 、
       ``_click_element``\ 、\ ``_dump_source``
   * - App 與 alert
     - ``AC_android_launch_app``\ 、\ ``_stop_app``\ 、\ ``_app_state``\ 、
       ``_wait_for_app``\ 、\ ``_alert_accept``\ 、\ ``_alert_dismiss``
     - 同樣六個，前綴為 ``AC_ios_``
   * - 擴充功能
     - ``AC_android_install_app``\ 、\ ``_push_file``\ 、\ ``_pull_file``\ 、
       ``_get_clipboard``\ 、\ ``_set_clipboard``\ 、\ ``_start_recording``\ 、
       ``_stop_recording``
     - 同樣七個，前綴為 ``AC_ios_``\ ；在註冊 adapter 之前，除了
       ``_set_clipboard`` 以外都會丟 ``DeviceUnsupportedError``
   * - Shell
     - ``AC_android_shell``
     - 無：iOS 沒有可以執行的 shell

``_find_*`` 與 ``_self_heal`` 指令可以帶 ``tap`` 來點擊找到的位置。
``AC_android_shell`` 會在裝置上執行任意指令，刻意不提供成 MCP 工具。

在 Python 裡，同一張表可以透過 ``run_mobile_command(name, params)`` 與
``mobile_capability_matrix()`` 取用；後者同時列出沒有行動對應的桌面功能
（視窗管理、滑鼠按鍵與滾輪、鍵盤快速鍵、桌面無障礙樹、COM、USB 主機轉接、
全域熱鍵、桌面擷取），以及每一項的限制與替代做法。它的 ``capabilities`` 列出提供某項
裝置能力的指令；``other_commands`` 依用途列出不屬於任何能力的指令——``device_info``
（``AC_android_list_devices``、``AC_android_device_info``、``AC_ios_device_info``：
只描述裝置、不送輸入）與 ``shell``（``AC_android_shell``）。這四個指令以前被歸在 ``input`` 底下。

**Mobile 分頁。** 選平台、輸入 serial 或 WebDriverAgent URL、選指令，並以 JSON
物件編輯參數。「探測裝置」、「執行指令」、「填入參數範本」都在 Actions 選單。
探測會顯示能力表與設定報告，不送出任何輸入。這兩個動作都在 GUI 執行緒上執行，
在裝置回應或逾時之前會卡住介面。

設定
====

.. warning::

   尚未在實機上測試。以下是程式碼預期的步驟；沒有任何一步實際對真的模擬器、
   手機或 WebDriverAgent 執行過。

Android 模擬器或實機
--------------------

1. 安裝 `Android platform-tools
   <https://developer.android.com/tools/releases/platform-tools>`_\ ，並把
   ``adb`` 放進 ``PATH``\ （或傳入 ``adb_path``\ ）。
2. 模擬器：啟動 AVD，它會以 ``emulator-5554`` 出現。實機：開啟「開發人員選項」
   與「USB 偵錯」，接上後在裝置上接受授權提示。走 Wi-Fi：
   ``adb connect <ip>:5555``\ 。
3. ``adb devices`` 必須顯示該 serial 的狀態為 ``device``\ 。\ ``unauthorized``
   在這裡會呈現為 ``needs_permission`` / ``DevicePermissionError``\ 。
4. 選用（元件樹、pinch、對話框、剪貼簿、Unicode 文字需要）：
   ``pip install uiautomator2``\ 。
5. 選用（不裝 ``uiautomator2`` 而要輸入 Unicode）：安裝 ADBKeyBoard，並以
   ``adb shell ime set com.android.adbkeyboard/.AdbIME`` 選用它。
6. 檢查：\ ``AC_android_device_info``\ （或 Mobile 分頁的「探測裝置」）會回報
   adb 版本、Android 版本與每一項能力。

iOS 實機或模擬器，本機或遠端 WebDriverAgent
-------------------------------------------

建置與簽署 WebDriverAgent 需要裝有 Xcode 的 Mac；實機還需要 Apple 開發者簽章
身分。AutoControl 不負責建置或安裝它。

1. 在 Mac 上對裝置或模擬器建置並執行 WebDriverAgent（對
   ``WebDriverAgentRunner`` scheme 執行 ``xcodebuild ... test``\ ），並讓 8100
   埠可以連到——USB 裝置用 ``iproxy 8100 8100``\ 。
2. 在執行 AutoControl 的主機（任何作業系統）：\ ``pip install facebook-wda``\ 。
3. 本機：URL 是 ``http://localhost:8100``\ 。遠端：使用 Mac 或裝置的位址，例如
   ``http://192.168.1.20:8100``\ 。WebDriverAgent 沒有任何驗證機制，請放在可信任
   的網路或通道後面。
4. 檢查：帶 ``url`` 的 ``AC_ios_device_info`` 會從 ``/status`` 回報
   WebDriverAgent 版本與 iOS 版本；沒有回應的端點會回報為
   ``needs_dependency``\ ，並附上連線錯誤。

從 Windows 或 Linux 操作遠端的 WebDriverAgent，是這些主機使用 iOS 的支援方式。
這並不代表已在這些主機上驗證過 Xcode 建置或簽署。
