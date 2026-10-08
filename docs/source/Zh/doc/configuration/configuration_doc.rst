============
設定參考
============

AutoControl 讀取的每一個環境變數都列在這裡。每一列會指向說明該功能的頁面；
本頁只說明變數是什麼、接受哪些值，以及未設定時的行為。

這裡沒有任何一項是必填的。完全不設定時，AutoControl 會自行選擇平台後端，
伺服器只綁定 ``127.0.0.1``，所有需要主動開啟的功能（簽章強制、RBAC、USB
直通、工具路徑限制）都是關閉的。

``test/unit_test/headless/test_modernization_examples.py`` 會拿本頁和程式碼
比對：套件讀取但本頁沒有列出的變數，中英兩個版本都會讓 CI 失敗。

.. contents::
   :local:
   :depth: 1

平台後端
========

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - 變數
     - 值（預設在前）
     - 作用
   * - ``JE_AUTOCONTROL_WIN32_BACKEND``
     - ``sendinput`` / ``interception``
     - Windows 的鍵盤與滑鼠後端。``interception`` 使用 Interception 驅動程式；
       找不到驅動或 DLL 時會警告並退回 ``SendInput``。
   * - ``JE_AUTOCONTROL_INTERCEPTION_DLL``
     - 未設定 / 路徑
     - ``interception.dll`` 的完整路徑。未設定時先找 ``PATH``，再找套件旁邊。
   * - ``JE_AUTOCONTROL_INTERCEPTION_KEYBOARD``
     - ``1`` / ``1``–``10``
     - 鍵盤事件要送往的 Interception 裝置編號。
   * - ``JE_AUTOCONTROL_INTERCEPTION_MOUSE``
     - ``11`` / ``11``–``20``
     - 滑鼠事件要送往的 Interception 裝置編號。
   * - ``JE_AUTOCONTROL_LINUX_BACKEND``
     - ``x11`` / ``uinput``
     - X11 的輸入後端。``uinput`` 直接寫入核心事件；``/dev/uinput`` 無法寫入時
       會警告並退回 XTest。
   * - ``JE_AUTOCONTROL_LINUX_DISPLAY_SERVER``
     - ``auto`` / ``wayland`` / ``x11``
     - 載入哪一個 Linux 後端。``auto`` 讀取 ``XDG_SESSION_TYPE`` 與
       ``WAYLAND_DISPLAY``；在 Wayland 工作階段設成 ``x11`` 只能操作 XWayland
       視窗。

Wayland
=======

請參考 :doc:`../wayland/wayland_capabilities_doc`。``probe_capabilities()``
可以在沒有任何副作用的情況下看到下列每一項的效果。

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - 變數
     - 值（預設在前）
     - 作用
   * - ``JE_AUTOCONTROL_WAYLAND_INPUT_BACKEND``
     - ``auto`` / ``cli``
     - ``cli`` 透過 ``ydotool`` 送出輸入，完全不向桌面 portal 提出要求。這是
       啟動前就做好的選擇：使用者拒絕授權後，AutoControl 不會自行切換過去。
   * - ``JE_AUTOCONTROL_WAYLAND_EI_WORKER``
     - 未設定 / ``1``
     - 把 libei 工作階段放到輔助行程裡執行，而不是放在本行程。
   * - ``JE_AUTOCONTROL_WAYLAND_POINTER_ACCEL``
     - ``warn`` / ``flat`` / ``strict``
     - 只影響 ``ydotool`` 路徑的絕對移動（那其實是會被合成器加速的相對位移）。
       ``warn``（未設定時亦同）警告一次後照樣移動；``flat`` 表示加速已關閉，
       不再警告；``strict`` 直接拒絕移動。
   * - ``JE_AUTOCONTROL_WAYLAND_CAPTURE_COMMAND``
     - 未設定 / 指令列
     - 自訂的截圖指令，以 ``{output}`` 表示 PNG 的輸出路徑。優先於 ``grim``、
       ``gnome-screenshot``、``spectacle`` 與 portal。
   * - ``JE_AUTOCONTROL_WAYLAND_RECORD_DEVICES``
     - 未設定 / 以逗號分隔的路徑
     - ``PhysicalRecorder`` 可以讀取的 ``/dev/input/event*`` 裝置。未設定代表
       一個都不讀：實體輸入錄製必須逐一指定裝置才會啟用。

記錄檔與本機狀態
================

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - 變數
     - 值（預設在前）
     - 作用
   * - ``JE_AUTOCONTROL_LOG_FILE``
     - 未設定 / 路徑
     - 記錄檔寫入的位置。未設定時為
       ``~/.je_auto_control/logs/AutoControlGUI.log``。指定空裝置
       （``/dev/null``、``NUL``）即可關閉檔案輸出。在寫入第一筆記錄時才讀取，
       而不是在 import 時。
   * - ``JE_AUTOCONTROL_GUI_SETTINGS``
     - 未設定 / 路徑 / ``off``
     - 主視窗保存佈景主題、文字大小、導覽面板與視窗位置的檔案。未設定時為
       ``~/.je_auto_control/gui_settings.ini``。設成 ``off``、``0``、``none``、
       ``false`` 或空字串時，不讀也不寫。
   * - ``JE_AUTOCONTROL_ENV``
     - ``default`` / 名稱
     - 資產庫目前使用的環境（``active_environment()``），讓同一份腳本在
       ``dev`` 與 ``prod`` 讀到不同的值。
   * - ``JE_AUTOCONTROL_REDACTION``
     - ``off`` / ``moderate`` / ``strict``
     - 截圖遮蔽的預設政策。未知的名稱會報錯，不會被當成 ``off``。
   * - ``JE_AUTOCONTROL_REMOTE_DOWNLOAD_DIR``
     - 未設定 / 目錄
     - 遠端桌面檢視端存放主機傳來檔案的位置。未設定時為
       ``~/Downloads/AutoControl``。收到的路徑一律限制在這個目錄內。
   * - ``JE_AUTOCONTROL_PYTEST_ARTIFACTS``
     - 未設定 / 目錄
     - 測試沒有使用 ``autocontrol_screenshot_dir`` fixture 時，pytest 外掛寫入
       失敗截圖的位置。未設定時為 ``./autocontrol_screenshots``。

執行與簽署動作檔
================

請參考 :doc:`../keyword_and_executor/keyword_and_executor_doc` 與
:doc:`../new_features/v4_features_doc`。

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - 變數
     - 值（預設在前）
     - 作用
   * - ``JE_AUTOCONTROL_ALLOWED_PACKAGES``
     - 未設定 / 以逗號分隔的名稱
     - ``AC_add_package_to_executor`` 可以載入的套件（含子模組），對所有進入點
       生效。只在行程啟動時讀取一次。
   * - ``JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS``
     - 未設定 / ``1``
     - 所有會執行動作檔的路徑，都拒絕沒有有效簽章檔的動作檔。
   * - ``JE_AUTOCONTROL_ACTION_SIGNING_PRIVATE_KEY``
     - 未設定 / 路徑
     - Ed25519 私鑰（PEM）。只在負責簽署的機器上設定；設定後簽署會寫出第 2 版
       的簽章檔。
   * - ``JE_AUTOCONTROL_ACTION_SIGNING_PUBLIC_KEY``
     - 未設定 / 路徑
     - 對應的公鑰。在每一台執行端設定：它只能驗證，不能簽署。
   * - ``JE_AUTOCONTROL_ACTION_SIGNING_PASSPHRASE``
     - 未設定 / 通行碼
     - 私鑰建立時若有設定通行碼，在這裡提供。
   * - ``JE_AUTOCONTROL_ACCEPT_LEGACY_ACTION_SIGNATURES``
     - 未設定 / ``1``
     - 遷移模式：設定公鑰之後，第 2 版之前寫出的 HMAC 簽章檔會被拒絕，除非
       設定了這個變數。所有檔案重新簽署後請再關掉。

MCP 伺服器
==========

請參考 :doc:`../mcp_server/mcp_server_doc`。

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - 變數
     - 值（預設在前）
     - 作用
   * - ``JE_AUTOCONTROL_MCP_READONLY``
     - 未設定 / ``1``
     - 只提供、也只能呼叫標示為唯讀的工具。
   * - ``JE_AUTOCONTROL_MCP_TOOL_MODE``
     - ``full`` / ``progressive`` / ``static``
     - ``tools/list`` 要提供登錄表的多少內容。未知的值會報錯，不會被當成
       ``full``。
   * - ``JE_AUTOCONTROL_MCP_TOOL_PROFILE``
     - 未設定 / 以逗號分隔的項目
     - ``static`` 模式的工具清單：工具名稱與 ``category:<名稱>``。
   * - ``JE_AUTOCONTROL_MCP_ALIASES``
     - ``1`` / ``0``
     - 是否在 ``ac_*`` 工具之外另外註冊簡短別名（``click``、``screenshot`` …）。
   * - ``JE_AUTOCONTROL_MCP_TOKEN``
     - 未設定 / 權杖
     - HTTP 傳輸的 Bearer 權杖。啟用 RBAC 之後不再接受。
   * - ``JE_AUTOCONTROL_MCP_ALLOWED_ORIGINS``
     - 未設定 / 以逗號分隔的來源
     - HTTP 傳輸額外接受的瀏覽器來源（須完全相符，例如
       ``https://example.test:8443``）。本機來源永遠接受。
   * - ``JE_AUTOCONTROL_MCP_CONFIRM_DESTRUCTIVE``
     - 未設定 / ``1``
     - 具破壞性的工具在執行前先向用戶端要求確認（MCP elicitation）。
   * - ``JE_AUTOCONTROL_MCP_PATH_ROOTS``
     - 未設定 / 目錄
     - 工具的每一個檔案參數都必須落在這些目錄內（以 ``os.pathsep`` 分隔）。
       未設定時不限制。
   * - ``JE_AUTOCONTROL_MCP_PATH_ROOTS_FROM_CLIENT``
     - 未設定 / ``1``
     - 同時接受 MCP 用戶端透過 ``roots/list`` 回報的根目錄。
   * - ``JE_AUTOCONTROL_MCP_ENV_REF_ALLOW``
     - 未設定 / 以逗號分隔的名稱
     - ``ac_resolve_ref`` 可以讀取的環境變數（可用 ``fnmatch`` 樣式）。未設定時
       不限制；設了卻沒有指名任何變數時，一個都不允許。
   * - ``JE_AUTOCONTROL_MCP_AUDIT``
     - 未設定 / 路徑
     - 每一次 ``tools/call`` 寫入一筆記錄的 JSON-lines 檔案。
   * - ``JE_AUTOCONTROL_MCP_ERROR_SHOTS``
     - 未設定 / 目錄
     - 工具每次失敗時，在這裡存一張截圖。
   * - ``JE_AUTOCONTROL_FAKE_BACKEND``
     - 未設定 / ``1``
     - MCP 伺服器只在記憶體中記錄滑鼠、鍵盤與剪貼簿呼叫而不實際執行，供沒有
       顯示器的 CI 使用。

存取控制與伺服器
================

請參考 :doc:`../operations_layer/operations_layer_doc` 與
:doc:`../config_sync/config_sync_doc`。

.. list-table::
   :header-rows: 1
   :widths: 34 20 46

   * - 變數
     - 值（預設在前）
     - 作用
   * - ``JE_AUTOCONTROL_RBAC_USERS``
     - 未設定 / 路徑
     - 使用者檔案。設定它就等於為 REST API 與 MCP HTTP 傳輸啟用角色；未設定時
       兩者都沿用共用權杖。
   * - ``JE_AUTOCONTROL_USB_PASSTHROUGH``
     - 未設定 / ``1``
     - 在遠端桌面通道上啟用 USB 直通指令。
   * - ``JE_AUTOCONTROL_CHATOPS_SCRIPT_ROOT``
     - 未設定 / 目錄
     - chat-ops 的 ``run`` 指令唯一可以載入動作檔的目錄。未設定時該指令會被
       拒絕。
   * - ``AC_SIGNALING_SECRET``
     - 未設定 / 密鑰
     - 信令／設定同步伺服器的共用密鑰（``X-Signaling-Secret``）。伺服器在沒有
       ``--shared-secret`` 時讀取它，``config_sync_run`` 在沒有 ``secret``
       時也讀取它。
   * - ``AC_SIGNALING_CONFIG_DB``
     - 未設定 / 路徑
     - 信令伺服器存放設定同步資料的 SQLite 檔案。未設定時為
       ``~/.je_auto_control/config_sync.sqlite3``。資產 blob(``/blobs``)
       放在同一路徑加上 ``.blobs`` 的資料夾,除非以 ``--blob-dir`` 指定;
       ``--max-blob-bytes`` 與 ``--blob-quota-bytes`` 限制它們的大小
       (只有旗標,沒有對應的環境變數)。
