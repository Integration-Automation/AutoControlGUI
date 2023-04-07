命令列介面
----

我們可以使用 CLI 模式去執行 keyword.json 檔案或執行包含 Keyword.json files 的資料夾，
以下這個範例是去執行指定路徑的關鍵字 json 檔

.. code-block::

    python je_auto_control --execute_file "C:\Users\JeffreyChen\Desktop\Code_Space\AutoControl\test\unit_test\argparse\test1.json"



以下這個範例是去執行指定路徑資料夾下所有的 keyword json 檔

.. code-block::

    python je_auto_control --execute_dir "C:\Users\JeffreyChen\Desktop\Code_Space\AutoControl\test\unit_test\argparse"