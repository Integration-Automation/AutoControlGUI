============
命令列介面
============

AutoControl 可以直接從命令列執行自動化腳本。

子命令 ``python -m je_auto_control.cli run script.json`` 可加上 ``--var name=value``
與 ``--dry-run``。每次呼叫都有獨立變數範圍，不論是否傳入 ``--var``；種子與動作寫入的
變數在成功或出錯後都會捨棄，包含在同一個 Python 行程中重複呼叫與預演。

擷取與查閱動作日誌
==================

.. code-block:: bash

   python -m je_auto_control.cli run script.json --journal run.jsonl --journal-run-id example
   python -m je_auto_control.cli journal run.jsonl --run-id example --limit 100

``run --journal PATH`` 附加結構化生命週期快照，保留原有 stdout 紀錄與動作失敗的退出碼，
也支援 ``--dry-run`` 與 ``--var``。未傳入 ``--journal-run-id ID`` 時會產生新的 run ID；
該選項必須搭配 ``--journal``。此操作不會自動建立 history 列或資料庫。

``journal PATH`` 驗證整份檔案，再以 JSON 陣列按附加順序輸出遮罩後的快照。
``--run-id`` 篩選指定執行；``--limit`` 在篩選後限制輸出筆數，允許 1–10,000，預設 100。
驗證仍會讀取整份檔案。開始與結束快照分開呈現，未完成項目不會被推定成功。
檔案不存在時回傳空陣列且不建立檔案；已提交的資料損壞時在任何 JSON 輸出前報錯。
查閱會再次套用日誌遮罩規則，不修改來源檔。兩個入口皆沿用既有的允許根目錄檢查；
預設範圍以外的位置可透過 ``AUTOCONTROL_ALLOWED_PATH_ROOTS`` 設定。

執行單一動作檔案
================

.. code-block:: bash

   python -m je_auto_control --execute_file "path/to/actions.json"

   # 簡寫
   python -m je_auto_control -e "path/to/actions.json"

執行資料夾內所有檔案
====================

.. code-block:: bash

   python -m je_auto_control --execute_dir "path/to/action_files/"

   # 簡寫
   python -m je_auto_control -d "path/to/action_files/"

資料夾（含子資料夾）裡每個 ``.json`` 檔都會執行，依路徑排序；指向資料夾外的連結不會跟進。

直接執行 JSON 字串
==================

.. code-block:: bash

   python -m je_auto_control --execute_str '[["AC_screenshot", {"file_path": "test.png"}]]'

放行動作檔要載入的套件
======================

``AC_add_package_to_executor`` 與 ``AC_add_package_to_callback_executor`` 會拒絕沒有被放行的套件。
從命令列放行的方式有兩種：環境變數 ``JE_AUTOCONTROL_ALLOWED_PACKAGES`` （以逗號分隔的套件名稱，含子模組），
對上面的旗標、 ``start-server`` 、 ``start-rest`` 與 MCP server 等所有入口都適用；以及 ``je_auto_control run``
的 ``--allow-package NAME`` （可重複），只對該次執行有效。

.. code-block:: bash

   JE_AUTOCONTROL_ALLOWED_PACKAGES=time,my_plugins python -m je_auto_control -e "path/to/actions.json"

   python -m je_auto_control.cli run script.json --allow-package time --allow-package my_plugins

建立專案範本
============

.. code-block:: bash

   python -m je_auto_control --create_project "path/to/my_project"

   # 簡寫
   python -m je_auto_control -c "path/to/my_project"

啟動 GUI
========

.. code-block:: bash

   python -m je_auto_control

.. note::

   啟動 GUI 需要安裝 ``[gui]`` 額外套件：
   ``pip install je_auto_control[gui]``
