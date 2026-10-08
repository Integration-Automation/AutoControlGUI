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
