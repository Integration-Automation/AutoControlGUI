========
專案管理
========

AutoControl 可以建立專案目錄架構與範本檔案，幫助你快速開始。

建立專案
========

使用 Python：

.. code-block:: python

   from je_auto_control import create_project_dir

   # 在目前工作目錄建立
   create_project_dir()

   # 在指定路徑建立
   create_project_dir("path/to/project")

   # 在指定路徑建立，並自訂目錄名稱
   create_project_dir("path/to/project", "My First Project")

使用 CLI：

.. code-block:: bash

   python -m je_auto_control --create_project "path/to/project"

產生的目錄結構
==============

.. code-block:: text

   my_project/
   └── AutoControl/
       ├── keyword/
       │   ├── keyword1.json          # 動作範本檔案
       │   ├── keyword2.json          # 動作範本檔案
       │   └── bad_keyword_1.json     # 錯誤處理範本
       └── executor/
           ├── executor_one_file.py   # 執行單一檔案範例
           ├── executor_folder.py     # 執行資料夾範例
           └── executor_bad_file.py   # 錯誤處理範例

``keyword/`` 目錄包含 JSON 動作檔案，``executor/`` 目錄包含示範如何執行的 Python 腳本。
