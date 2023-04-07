關鍵字與執行者
----

* Keyword 是一個 JSON 檔案裏面包含許多自定義的關鍵字與參數。
* Keyword 會與 Executor 搭配使用。
* Keyword 的格式是以下範例，且在 JSON 檔案裡面使用一樣格式。

.. code-block:: python

    [
        ["function_name_in_event_dict": {"param_name": param_value}],
        ["function_name_in_event_dict": {"param_name": param_value}],
        ["function_name_in_event_dict": {"param_name": param_value}],
        # many....
        # If you are using position param
        ["function_name_in_event_dict": {param_value1, param_value2....}]
    ]

executor 是一個會解析 JSON 檔案的直譯器，
可以簡單地透過網路傳輸到遠端伺服器或電腦，
再藉由遠端伺服器或電腦的 executor 執行自動化。

如果我們想要在 executor 裡面添加 function，可以使用如下:
這段程式碼會把所有 time module 的 builtin, function, method, class
載入到 executor，然後要使用被載入的 function 需要使用 package_function 名稱，
例如 time.sleep 會變成 time_sleep

.. code-block:: python

    from je_auto_control import package_manager
    package_manager.add_package_to_executor("time")



如果你需要查看被更新的 event_dict 可以使用

.. code-block:: python

    from je_auto_control import executor
    print(executor.event_dict)

如果我們想要執行 JSON 檔案

.. code-block:: python

    from je_auto_control import execute_action, read_action_json
    execute_action(read_action_json(file_path))

如果我們想要執行資料夾裡所有 JSON 檔案

.. code-block:: python

    from je_auto_control import execute_files, get_dir_files_as_list
    execute_files(get_dir_files_as_list(dir_path))