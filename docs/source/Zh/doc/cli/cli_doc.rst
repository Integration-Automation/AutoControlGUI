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

直接執行 JSON 字串
==================

.. code-block:: bash

   python -m je_auto_control --execute_str '[["AC_screenshot", {"file_path": "test.png"}]]'

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
