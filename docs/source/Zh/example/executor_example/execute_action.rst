================================================
AutoControl 執行器範例
================================================

| 可以使用 write_action_json 來儲存指令檔
| 然後可以使用 read_action_json 來讀取指令檔
| 這個範例是 讀取 及 儲存 指令檔
.. code-block:: python

    import os
    import json


    from je_auto_control import read_action_json
    from je_auto_control import write_action_json
    test_list = [
        ["type_key", {"keycode": 0x00}],
        ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["position"],
        ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
    ]
    test_dumps_json = json.dumps(test_list)
    print(test_dumps_json)
    test_loads_json = json.loads(test_dumps_json)
    print(test_loads_json)
    list(test_loads_json)

    write_action_json(os.getcwd() + "/test.json", test_dumps_json)
    read_json = read_action_json(os.getcwd() + "/test.json")
    print(read_json)


| 可以直接使用 execute_action 加 list 含指令檔的方式
| 這個範例使用 execute_action + test_record
.. code-block:: python

    import sys

    from je_auto_control import execute_action
    from je_auto_control import test_record

    test_list = None
    if sys.platform in ["win32", "cygwin", "msys"]:
        test_list = [
            ["type_key", {"keycode": 65}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_key", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
        ]

    elif sys.platform in ["linux", "linux2"]:
        test_list = [
            ["type_key", {"keycode": 38}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_key", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
        ]
    elif sys.platform in ["darwin"]:
        test_list = [
            ["type_key", {"keycode": 0x00}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_key", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
        ]
    print("\n\n")
    execute_action(test_list)


.. code-block:: python

    """
    取得 當前資料夾所有指令檔並執行的範例
    get current dir all execute file(json file) list and execute list of file
    """
    import os

    from je_auto_control import get_dir_files_as_list
    from je_auto_control import execute_files
    files_list = get_dir_files_as_list(os.getcwd())
    print(files_list)
    if files_list is not None:
        execute_files(files_list)

