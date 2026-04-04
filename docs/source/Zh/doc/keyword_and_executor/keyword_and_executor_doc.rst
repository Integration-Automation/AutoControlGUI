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
     - ``AC_type_keyboard``, ``AC_press_keyboard_key``, ``AC_release_keyboard_key``, ``AC_write``, ``AC_hotkey``, ``AC_check_key_is_press``
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

查看目前執行者的指令字典：

.. code-block:: python

   from je_auto_control import executor

   print(executor.event_dict)
