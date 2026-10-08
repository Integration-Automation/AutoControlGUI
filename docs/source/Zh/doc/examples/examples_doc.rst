============
可執行範例
============

儲存庫的 ``examples/`` 資料夾裡，每個功能都有一支簡短的腳本。下列六支涵蓋最近
新增的功能，而且每一支都接受 ``--validate``：

.. code-block:: bash

   pip install -e .
   python examples/29_config_sync.py --validate

加上 ``--validate`` 時，腳本會以記憶體、暫存目錄或 loopback 的替身來執行真正的
API，觀察到的結果與文件所述相符時以 ``0`` 結束。它不會移動游標、不會輸入文字、
不會擷取畫面、不會連到任何裝置，也不會與 ``127.0.0.1`` 以外的對象通訊。CI 就是
這樣執行這六支腳本的（``test_modernization_examples.py``），而且每一個輸入與
行程的接點都換成了絆線。

這能證明呼叫的接法與這些頁面所寫的一致，但不能證明硬體行為：這裡沒有任何東西
碰過 Wayland 合成器、Android 裝置或 iPhone。真正執行時需要什麼，各腳本自己的
docstring 會寫明。

.. list-table::
   :header-rows: 1
   :widths: 30 40 30

   * - 腳本
     - ``--validate`` 做什麼
     - 不加旗標時
   * - ``28_wayland_diagnostics.py``
     - 探測四個以描述建構的桌面（拒絕授權前後的 GNOME、搭配 ``ydotool`` 的
       sway、Wayland 工作階段上的 X11），並用 ``InputStepLog`` 記錄一次 dry run。
     - 探測目前的工作階段，同樣沒有副作用。
   * - ``29_config_sync.py``
     - 兩台機器透過暫存目錄裡的儲存庫同步腳本檔：送達、伺服器重啟、離線佇列、
       衝突與衝突的解決。
     - 印出已記錄的狀態；加上 ``--run`` 才會真的同步這台機器。
   * - ``30_mobile_devices.py``
     - 以離線傳輸開啟 Android 工作階段，檢查設定報告、擷取、手勢與輸入各送出
       哪些 ``adb`` 指令。
     - 印出裝置的設定報告；加上 ``--tap X Y`` 才會點擊。
   * - ``31_healing_comparison.py``
     - 以記憶體中畫出的五張已標註畫面（HiDPI、負座標原點、目標不存在、改版後）
       為兩個版本的樣板比對評分。
     - ``--dataset FILE`` 評估資料集檔案，同樣是離線的。
   * - ``32_codegen_from_log.py``
     - 把一次只含變數與流程控制指令的執行寫入日誌，重建成候選腳本，再 dry run
       一次。
     - ``--journal FILE`` 轉換你自己錄下的日誌。
   * - ``33_mcp_progressive.py``
     - 驅動行程內的 MCP 伺服器：列出、搜尋、讀取 schema、啟用一個工具。不會呼叫
       任何會碰到桌面的工具。
     - 以 progressive 模式透過 stdio 提供 MCP 服務。

各功能的文件位置
================

.. list-table::
   :header-rows: 1
   :widths: 24 38 38

   * - 功能
     - 說明頁
     - 進入點
   * - 能力與授權狀態
     - :doc:`../wayland/wayland_capabilities_doc`
     - ``probe_capabilities``、``AC_probe_capabilities``、
       ``ac_probe_capabilities``、Diagnostics 分頁
   * - 不靠全域掛鉤的錄製
     - :doc:`../record/record_doc`
     - ``InputStepLog``、``PhysicalRecorder``、``StopShortcutSession``
   * - 設定同步
     - :doc:`../config_sync/config_sync_doc`
     - ``config_sync_run`` / ``_status`` / ``_resolve`` / ``_full_resync``、
       ``AC_config_sync_*``、``ac_config_sync_*``、Config Sync 分頁
   * - 行動裝置工作階段
     - :doc:`../mobile/mobile_doc`
     - ``open_device``、``use_device``、``run_mobile_command``、
       ``AC_android_*`` / ``AC_ios_*``、Mobile 分頁
   * - 自我修復評估與樣板修訂
     - :doc:`../new_features/v2_features_doc`
     - ``evaluate_locators``、``evaluate_healing_dataset``、
       ``AC_self_heal_evaluate``、``propose_template_revision``
   * - 動作日誌與候選腳本
     - :doc:`../new_features/v5_features_doc`
     - ``start_action_journal``、``generate_candidate_from_log``、
       ``AC_journal_*``、``je_auto_control codegen --from-log``
   * - MCP 工具模式
     - :doc:`../mcp_server/mcp_server_doc`
     - ``--tool-mode``、``JE_AUTOCONTROL_MCP_TOOL_MODE``、``ac_tools_*``
   * - 角色與延後工作的擁有者
     - :doc:`../operations_layer/operations_layer_doc`
     - ``JE_AUTOCONTROL_RBAC_USERS``、``rbac_add_user``、``AC_user_*``、
       ``je_auto_control users``
   * - 動作檔簽章（Ed25519）
     - :doc:`../new_features/v4_features_doc`
     - ``create_signing_keypair``、``sign_action_file``、
       ``JE_AUTOCONTROL_REQUIRE_SIGNED_ACTIONS``
   * - 視窗外殼、導覽與背景工作
     - :doc:`../new_features/v223_features_doc`
     - Actions 與 View 選單、``JE_AUTOCONTROL_GUI_SETTINGS``
   * - 所有環境變數
     - :doc:`../configuration/configuration_doc`
     -

範例裡容易忽略的三件事
======================

**執行器的選項在執行器物件上。** 模組層級的
``je_auto_control.execute_action(actions)`` 只接受動作清單。``dry_run``、
``raise_on_error`` 與 ``step_callback`` 屬於
``je_auto_control.executor.execute_action``：

.. code-block:: python

   import je_auto_control as ac

   ac.executor.execute_action(actions, dry_run=True)          # 只解析，不呼叫
   ac.executor.execute_action(actions, raise_on_error=True)   # 第一個失敗就停

**同步失敗後會退避。** 送出失敗之後，在退避時間內（2 秒起、每次加倍、上限
5 分鐘）再呼叫 ``config_sync_run`` 並不會連線到伺服器：它會再次回報
``offline``，``error`` 為 ``waiting to retry after an earlier failure``。傳入
``wait=True`` 則會等到退避結束再送——排程同步需要的就是這個行為，而 ``cancel``
事件可以中斷等待。

**搜尋工具不等於啟用工具。** 在 progressive 模式下，``ac_tools_search`` 與
``ac_tools_schema`` 只負責描述；呼叫 ``ac_tools_enable`` 之後，該工作階段的
``tools/list`` 才會改變，並以 ``notifications/tools/list_changed`` 通知用戶端。

各腳本的驗證路徑
================

以下內容直接取自腳本本身，也就是 CI 實際執行的程式碼。

.. literalinclude:: ../../../../../examples/28_wayland_diagnostics.py
   :language: python
   :pyobject: validate
   :caption: examples/28_wayland_diagnostics.py

.. literalinclude:: ../../../../../examples/29_config_sync.py
   :language: python
   :pyobject: _walkthrough
   :caption: examples/29_config_sync.py

.. literalinclude:: ../../../../../examples/30_mobile_devices.py
   :language: python
   :pyobject: validate
   :caption: examples/30_mobile_devices.py

.. literalinclude:: ../../../../../examples/31_healing_comparison.py
   :language: python
   :pyobject: validate
   :caption: examples/31_healing_comparison.py

.. literalinclude:: ../../../../../examples/32_codegen_from_log.py
   :language: python
   :pyobject: validate
   :caption: examples/32_codegen_from_log.py

.. literalinclude:: ../../../../../examples/33_mcp_progressive.py
   :language: python
   :pyobject: validate
   :caption: examples/33_mcp_progressive.py
