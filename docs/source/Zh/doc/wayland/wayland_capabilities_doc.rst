==========================
Wayland 上的能力與授權狀態
==========================

在 Windows 上，後端不是能用就是拋例外。在 Wayland 上，有意思的答案都落在中間：
輸入可能走桌面 portal，也可能走 ``/dev/uinput``；使用者可能拒絕了同意對話框，
也可能根本沒有 portal 可以問；也可能是 X11 後端透過 XWayland 在服務一個 Wayland
工作階段，只碰得到部分視窗。``probe_capabilities()`` 把這些全部當成資料回報。

探測
====

.. code-block:: python

   import je_auto_control as ac

   snapshot = ac.probe_capabilities()
   print(snapshot.display_server, snapshot.xwayland)
   for capability in snapshot.capabilities:
       print(capability.name, capability.state.value, capability.backend,
             capability.desktop_wide, capability.recovery)

**探測沒有任何副作用。** 它只讀環境變數、在 ``PATH`` 上找名字、問載入器某個函式庫
在不在、讀授權紀錄。它不會發出 portal 請求、不會跳出同意對話框、不會連上 libei
sender，也不會送出任何事件。

同一份資料在每個入口都拿得到：

* JSON 動作：``[["AC_probe_capabilities"]]``
* MCP 工具：``ac_probe_capabilities``\ （唯讀）
* GUI：**診斷** 分頁的第二張表

四項能力各自獨立診斷，因為它們各自獨立地壞：

.. list-table::
   :header-rows: 1

   * - 名稱
     - 是什麼
   * - ``input``
     - 合成鍵盤與指標事件
   * - ``capture``
     - 讀取螢幕像素
   * - ``recording``
     - 讀取 *使用者* 自己打的字與點的鍵
   * - ``stop_shortcut``
     - 停止執行中腳本的全域按鍵

狀態
====

.. list-table::
   :header-rows: 1

   * - ``state``
     - 意義
   * - ``available``
     - 現在可用
   * - ``not_requested``
     - 可用，但還沒問過桌面；第一次使用時才會問
   * - ``requesting``
     - 同意請求現在正顯示在螢幕上
   * - ``needs_permission``
     - 同意被拒絕或沒人回應，或裝置不可讀
   * - ``needs_setup``
     - 需要安裝或設定某些東西
   * - ``session_closed``
     - 本行程自己關掉了工作階段；下次使用會再問一次
   * - ``revoked``
     - 合成器收回了已經授予的工作階段
   * - ``compositor_restarted``
     - 授權來自一個已經不是現在這個的合成器
   * - ``unknown``
     - 不產生副作用就無法判定（例如 macOS 的權限）

每項能力另外帶有 ``backend``（由誰提供）、``desktop_wide``、``detail``、
``recovery``\ （英文的處理方式）與 ``recovery_key``\ （同一段建議在 GUI 語系表的鍵）。

libei 路徑上的 ``restore_token`` 是 ``unsupported``：這個綁定不向 portal 要求
restore token，所以同意是每個行程問一次，重新啟動後不會保留。

拒絕不會被繞過
==============

``JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=auto``（預設）先試 libei，在 libei
*起不來* 的時候退回 ``ydotool`` CLI：沒有 libei、沒有 RemoteDesktop portal、
交握一直沒完成。這一點沒有變。

有兩種結果不再退回，因為兩者都是有權說不的人說了不：

* portal **拒絕** 了請求（``state == "needs_permission"``）；
* 合成器 **收回** 了一個原本存活的工作階段（``state == "revoked"``）。

這時輸入動作會拋出 ``WaylandAuthorisationError``——帶有 ``state``、
``capability`` 與 ``recovery`` 指示——而不是在拒絕的背後改用 ``/dev/uinput``
驅動桌面。復原方式：

.. code-block:: python

   ac.reset_input_authorisation()   # 下一個輸入動作會再問一次
   ac.close_input_session()         # 現在就結束工作階段（撤銷授權）

或 ``[["AC_reset_input_authorisation"]]``，或診斷分頁的 **操作 > 重新要求輸入
授權**。若要刻意使用 ydotool，請在啟動前設定
``JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND=cli``；那條路徑完全不會去問 portal。

被收回的工作階段也不會再被寫入：合成器斷線之後，libei 後端拒絕每一次送出。

.. note::

   「拒絕」是從 liboeffis 自己的錯誤文字辨認出來的。真實桌面是否這樣措辭，
   由 ``portal-verification`` CI job 量測，不在這裡斷言。認不出來的時候沿用
   舊行為（退回 ydotool）：授權記為 ``failed``，該能力的後端顯示為 ``ydotool``。

XWayland
========

當 X11 後端在服務一個 Wayland 工作階段時——因為設了
``JE_AUTOCONTROL_LINUX_DISPLAY_SERVER=x11``，或因為 Wayland 後端載入失敗——
``snapshot.xwayland`` 為 ``True``，每項能力的 ``desktop_wide`` 都是 ``False``：
碰得到 X11 應用程式，原生 Wayland 視窗收不到輸入，也不會出現在擷取畫面裡。

錄製
====

Wayland 沒有全域輸入掛鉤，所以 ``record()`` 在那裡仍然會拋例外。有兩件範圍
較小的事可以做。

**程式自己執行了什麼**，在任何平台上都不需要掛鉤：

.. code-block:: python

   journal = ac.InputStepLog()
   journal.run(actions)             # 就是你會交給 execute_action 的那份清單
   print(journal.steps)

**你實際打的字與點的鍵**，可以從你指名的核心裝置讀取。這是逐裝置的明確
opt-in，會排除虛擬（uinput）裝置，讓本程式自己的 ydotool 輸出不會被錄成你的
輸入，而且絕不取得額外權限：

.. code-block:: python

   devices = [d for d in ac.list_input_devices() if not d.is_virtual]
   recorder = ac.PhysicalRecorder()
   recorder.start(devices[:1])          # 沒有權限時拋出 InputPermissionError
   events = recorder.stop()             # InputEvent(type, code, value) 的清單

``JE_AUTOCONTROL_WAYLAND_RECORD_DEVICES``（以逗號分隔的
``/dev/input/event*`` 路徑）把這個選擇記下來，供能力探測使用。使用者讀不到的
裝置會拋出 ``InputPermissionError`` 並附上處理方式：把使用者加入 ``input``
群組，或安裝 udev 規則。不要為此以 root 執行整個程式。

不使用 portal 的 *InputCapture* 介面：它何時開始由合成器決定，所以不能當成
腳本要求時才啟動的錄製器。

全域停止鍵
==========

``StopShortcutSession`` 透過 ``GlobalShortcuts`` portal 註冊一個具名的快捷鍵，
在它被按下時回呼。它只回報那一個快捷鍵，不會回報其他按鍵。

.. code-block:: python

   import threading

   stop = threading.Event()
   with ac.StopShortcutSession(stop.set) as session:
       session.start()
       ...                              # 執行；檢查 stop.is_set()
   # 離開區塊就會關閉 portal 工作階段

如果桌面沒有 GlobalShortcuts portal，或使用者拒絕，``ShortcutUnavailable``
（或 ``ShortcutPermissionError``）會指出仍然可用的停止方式。這條路徑沒有 CI
覆蓋，見 ``test/manual_test/wayland_authorisation_checklist.md``。

libei helper 行程（opt-in）
===========================

``JE_AUTOCONTROL_WAYLAND_EI_WORKER=1`` 會把 libei 工作階段放進 helper 行程。
它 **預設關閉**。行程內的路徑——包含交握一直沒完成時刻意漏掉的一個 context 與
一個 fd——沒有改變，仍然是預設；它所迴避的上游 ``ei_unref`` crash 並沒有因此
被修好。

使用 helper 時，無法安全釋放的工作階段會在 helper 結束時由作業系統回收。
請求有上限（每批 64 個事件、每個 frame 64 KiB）、帶有 id、遵守時限與取消，
helper 被關閉時會放開仍被按住的鍵。代價是每次送出多一趟 pipe 往返；
``docker/eis_verify.py`` 會量測它。

失敗依一個問題分成兩類——別的後端可以重做這件事嗎？``EiWorkerError``（含
``EiDependencyMissing``）是 ``LibeiUnavailable``：什麼都沒送出去，ydotool 可以
接手。``EiWorkerTimeout``、``EiWorkerCancelled`` 與 ``EiWorkerDied`` 不是：請求
已經寫出去、結果未知，所以它們會傳到呼叫端。
