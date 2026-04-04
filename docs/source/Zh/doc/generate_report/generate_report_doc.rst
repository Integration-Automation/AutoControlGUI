========
報告產生
========

AutoControl 可以產生 HTML、JSON 和 XML 格式的測試報告。報告會記錄哪些自動化步驟被執行，
以及是否成功。

設定
====

在產生報告之前，需先啟用測試記錄：

.. code-block:: python

   from je_auto_control import test_record_instance

   test_record_instance.init_record = True

.. important::

   記錄必須在執行動作 **之前** 啟用，否則不會擷取到任何資料。

產生報告
========

HTML 報告
---------

.. code-block:: python

   from je_auto_control import execute_action, generate_html_report, test_record_instance

   test_record_instance.init_record = True

   actions = [
       ["set_record_enable", {"set_enable": True}],
       ["AC_set_mouse_position", {"x": 500, "y": 500}],
       ["AC_click_mouse", {"mouse_keycode": "mouse_left"}],
       ["generate_html_report"],
   ]
   execute_action(actions)

產生的 HTML 報告中，成功的動作以 **青色** 顯示，失敗的動作以 **紅色** 顯示。

JSON 報告
---------

.. code-block:: python

   from je_auto_control import generate_json_report

   generate_json_report("test_report")  # -> test_report.json

XML 報告
--------

.. code-block:: python

   from je_auto_control import generate_xml_report

   generate_xml_report("test_report")  # -> test_report.xml

取得報告內容為字串
==================

如果需要報告內容而不儲存為檔案：

.. code-block:: python

   from je_auto_control import generate_html, generate_json, generate_xml

   html_string = generate_html()
   json_data = generate_json()
   xml_data = generate_xml()

報告內容
========

每筆報告記錄包含：

* **函式名稱** -- 被呼叫的自動化函式
* **參數** -- 傳遞給函式的引數
* **時間戳記** -- 動作執行的時間
* **例外資訊** -- 動作失敗時的錯誤詳情
