================
關鍵字與執行者
================

關鍵字/執行者系統是 AutoControl 的 JSON 腳本引擎。你可以將自動化步驟定義為
JSON 陣列（關鍵字），由執行者解析並執行。

關鍵字格式
==========

關鍵字是 JSON 陣列，每個元素代表一個動作：

.. code-block:: json

   [
       ["function_name", {"param_name": "param_value"}],
       ["function_name", {"param_name": "param_value"}]
   ]

範例：

.. code-block:: json

   [
       ["AC_set_mouse_position", {"x": 500, "y": 300}],
       ["AC_click_mouse", {"mouse_keycode": "mouse_left"}],
       ["AC_write", {"write_string": "Hello"}]
   ]

開關類參數(``ignore_case``、``present``、``raise_on_fail``、``paste`` 等)接受 JSON 的 ``true`` / ``false``,
或依拼法判讀的字串:``"true"``、``"yes"``、``"on"``、``"1"`` 為開,其他字串(``"false"``、``"no"``、``"off"``、
``"0"``)為關。

可用的動作指令
==============

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - 分類
     - 指令
   * - 滑鼠
     - ``AC_click_mouse``, ``AC_set_mouse_position``, ``AC_get_mouse_position``, ``AC_press_mouse``, ``AC_release_mouse``, ``AC_mouse_scroll``
   * - 鍵盤
     - ``AC_type_keyboard``, ``AC_press_keyboard_key``, ``AC_release_keyboard_key``, ``AC_write``, ``AC_write_secret``, ``AC_hotkey``, ``AC_check_key_is_press``
   * - 圖片
     - ``AC_locate_all_image``, ``AC_locate_image_center``, ``AC_locate_and_click``
   * - 螢幕
     - ``AC_screen_size``, ``AC_screenshot``
   * - 錄製
     - ``AC_record``, ``AC_stop_record``
   * - 報告
     - ``AC_generate_html``, ``AC_generate_json``, ``AC_generate_xml``, ``AC_generate_html_report``, ``AC_generate_json_report``, ``AC_generate_xml_report``
   * - 專案
     - ``AC_create_project``
   * - Shell
     - ``AC_shell_command``
   * - 執行器
     - ``AC_execute_action``, ``AC_execute_files``

執行 JSON 檔案
===============

.. code-block:: python

   from je_auto_control import execute_action, read_action_json

   execute_action(read_action_json("actions.json"))

執行資料夾內所有 JSON 檔案
===========================

.. code-block:: python

   from je_auto_control import execute_files, get_dir_files_as_list

   execute_files(get_dir_files_as_list("./action_files/"))

擴充執行者
==========

你可以動態載入外部 Python 套件到執行者中：

哪些套件可以載入由套件閘門決定。``AC_add_package_to_executor`` 原本能替任何動作清單匯入 ``os`` 或
``subprocess``，所以 **沒有被放行的套件一律不載入**：不在允許清單上的套件在匯入前就被拒絕，該動作以
``AutoControlExecuteActionException`` 失敗。列出一個套件也同時放行它的子模組。放行的方式有三種：

.. code-block:: python

   from je_auto_control import executor

   executor.allow_packages("time")                # 這些套件與其子模組

.. code-block:: bash

   # 所有入口都適用：兩個 CLI、socket／REST／MCP server、排程器
   JE_AUTOCONTROL_ALLOWED_PACKAGES=time,my_plugins je_auto_control start-server

   # 只對 CLI 的這一次執行；旗標可以重複
   je_auto_control run script.json --allow-package time --allow-package my_plugins

``JE_AUTOCONTROL_ALLOWED_PACKAGES`` 是以逗號分隔的清單，只在行程啟動時讀一次；不是模組名稱（以點分隔的識別字）
的項目會被略過並記錄到日誌。``executor.set_allow_arbitrary_packages(True)`` 會放行所有套件，也就是這一版之前的
預設行為（當時任何套件都會載入，只發出 ``DeprecationWarning``）。以上都不是 ``AC_*`` 命令，所以動作清單不能
自己打開閘門。


.. code-block:: python

   from je_auto_control import package_manager

   # 載入 time 模組的所有函式
   package_manager.add_package_to_executor("time")

載入後，函式可透過 ``套件_函式名`` 的命名方式使用。
例如 ``time.sleep`` 會變成 ``time_sleep``：

.. code-block:: json

   [
       ["time_sleep", {"secs": 2}]
   ]

只要閘門允許該套件，動作檔可以在同一份清單裡載入套件並使用它：

.. code-block:: json

   [
       ["AC_add_package_to_executor", ["time"]],
       ["time_sleep", [2]]
   ]

所有指令名稱會在第一個動作執行前先檢查，而 ``time_sleep`` 要等載入指令執行後
才存在，所以這樣的清單以前不論閘門怎麼設定都會以 unknown command 被拒絕。
現在符合下列全部條件的名稱會留到執行時才檢查：名稱以 ``<套件>_`` 開頭；檔案中
較前面有一個 ``AC_add_package_to_executor`` 以字面值指名該套件（``["time"]``
或 ``{"package": "time"}``\ ，不能是 ``${變數}``\ ）；而且閘門會放行該套件。
其他情況——套件未被允許、名稱用在載入之前、``AC_*`` 名稱打錯——仍然在任何動作
執行前就被拒絕。留到執行時的名稱若其實不存在（``time_slep``\ ），執行到它時
該動作會以 ``Unknown action`` 失敗。``je_auto_control validate`` 與 REST 的
事前檢查遵循同一條規則。

查看目前執行者的指令字典：

.. code-block:: python

   from je_auto_control import executor

   print(executor.event_dict)
