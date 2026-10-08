============
命令列介面
============

AutoControl 可以直接從命令列執行自動化腳本。

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
從命令列放行的方式有兩種：環境變數 ``JE_AUTOCONTROL_ALLOWED_PACKAGES``（以逗號分隔的套件名稱，含子模組），
對上面的旗標、``start-server``、``start-rest`` 與 MCP server 等所有入口都適用；以及 ``je_auto_control run``
的 ``--allow-package NAME``（可重複），只對該次執行有效。

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
