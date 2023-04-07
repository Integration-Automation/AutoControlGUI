報告產生 文件
----

Generate Report 可以生成以下格式的報告
* HTML
* JSON
* XML
* Generate Report 主要用來記錄與確認有哪些步驟執行，執行是否成功，
* 如果要使用 Generate Report 需要先設定紀錄為 True，使用 test_record_instance.init_record = True
* 下面的範例有搭配 keyword and executor 如果看不懂可以先去看看 executor
以下是產生 HTML 的範例。
.. code-block:: python
    import sys

    from je_auto_control import execute_action
    from je_auto_control import test_record_instance

    test_list = None
    test_record_instance.init_record = True
    if sys.platform in ["win32", "cygwin", "msys"]:
        test_list = [
            ["set_record_enable", {"set_enable": True}],
            ["type_key", {"keycode": 65}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_key", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
            ["generate_html_report"],
        ]

    elif sys.platform in ["linux", "linux2"]:
        test_list = [
            ["set_record_enable", {"set_enable": True}],
            ["type_key", {"keycode": 38}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_key", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
            ["generate_html_report"],
        ]
    elif sys.platform in ["darwin"]:
        test_list = [
            ["set_record_enable", {"set_enable": True}],
            ["type_key", {"keycode": 0x00}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_key", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
            ["generate_html_report"],
        ]
    print("\n\n")
    execute_action(test_list)


以下是產生 JSON 的範例。
.. code-block:: python
    import sys

    from je_auto_control import execute_action
    from je_auto_control import test_record_instance

    test_list = None
    test_record_instance.init_record = True
    if sys.platform in ["win32", "cygwin", "msys"]:
        test_list = [
            ["set_record_enable", {"set_enable": True}],
            ["type_key", {"keycode": 65}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_key", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
            ["generate_json_report"],
        ]

    elif sys.platform in ["linux", "linux2"]:
        test_list = [
            ["set_record_enable", {"set_enable": True}],
            ["type_key", {"keycode": 38}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_key", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
            ["generate_json_report"],
        ]
    elif sys.platform in ["darwin"]:
        test_list = [
            ["set_record_enable", {"set_enable": True}],
            ["type_key", {"keycode": 0x00}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_key", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
            ["generate_json_report"],
        ]
    print("\n\n")
    execute_action(test_list)

以下是產生 XML 的範例。
.. code-block:: python
    import sys

    from je_auto_control import execute_action
    from je_auto_control import test_record_instance

    test_list = None
    test_record_instance.init_record = True
    if sys.platform in ["win32", "cygwin", "msys"]:
        test_list = [
            ["set_record_enable", {"set_enable": True}],
            ["type_key", {"keycode": 65}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_key", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
            ["generate_xml_report"]
        ]

    elif sys.platform in ["linux", "linux2"]:
        test_list = [
            ["set_record_enable", {"set_enable": True}],
            ["type_key", {"keycode": 38}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_key", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
            ["generate_xml_report"]
        ]
    elif sys.platform in ["darwin"]:
        test_list = [
            ["set_record_enable", {"set_enable": True}],
            ["type_key", {"keycode": 0x00}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_key", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
            ["generate_xml_report"]
        ]
    print("\n\n")
    execute_action(test_list)
