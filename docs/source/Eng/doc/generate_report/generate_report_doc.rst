Generate Report
----

* Generate Report can generate reports in the following formats:
 * HTML
 * JSON
 * XML

* Generate Report is mainly used to record and confirm which steps were executed and whether they were successful or not.
* If you want to use Generate Report, you need to set the recording to True by using test_record_instance.init_record = True.
* The following example is used with keywords and an executor. If you don't understand, please first take a look at the executor.

Here's an example of generating an HTML report.

.. code-block:: python

    import sys

    from je_auto_control import execute_action
    from je_auto_control import test_record_instance

    test_list = None
    test_record_instance.init_record = True
    if sys.platform in ["win32", "cygwin", "msys"]:
        test_list = [
            ["set_record_enable", {"set_enable": True}],
            ["type_keyboard", {"keycode": 65}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["get_mouse_position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_keyboard", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
            ["generate_html_report"],
        ]

    elif sys.platform in ["linux", "linux2"]:
        test_list = [
            ["set_record_enable", {"set_enable": True}],
            ["type_keyboard", {"keycode": 38}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["get_mouse_position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_keyboard", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
            ["generate_html_report"],
        ]
    elif sys.platform in ["darwin"]:
        test_list = [
            ["set_record_enable", {"set_enable": True}],
            ["type_keyboard", {"keycode": 0x00}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["get_mouse_position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_keyboard", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
            ["generate_html_report"],
        ]
    print("\n\n")
    execute_action(test_list)


Here's an example of generating an JSON report.

.. code-block:: python

    import sys

    from je_auto_control import execute_action
    from je_auto_control import test_record_instance

    test_list = None
    test_record_instance.init_record = True
    if sys.platform in ["win32", "cygwin", "msys"]:
        test_list = [
            ["set_record_enable", {"set_enable": True}],
            ["type_keyboard", {"keycode": 65}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["get_mouse_position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_keyboard", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
            ["generate_json_report"],
        ]

    elif sys.platform in ["linux", "linux2"]:
        test_list = [
            ["set_record_enable", {"set_enable": True}],
            ["type_keyboard", {"keycode": 38}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["get_mouse_position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_keyboard", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
            ["generate_json_report"],
        ]
    elif sys.platform in ["darwin"]:
        test_list = [
            ["set_record_enable", {"set_enable": True}],
            ["type_keyboard", {"keycode": 0x00}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["get_mouse_position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_keyboard", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
            ["generate_json_report"],
        ]
    print("\n\n")
    execute_action(test_list)

Here's an example of generating an XML report.

.. code-block:: python

    import sys

    from je_auto_control import execute_action
    from je_auto_control import test_record_instance

    test_list = None
    test_record_instance.init_record = True
    if sys.platform in ["win32", "cygwin", "msys"]:
        test_list = [
            ["set_record_enable", {"set_enable": True}],
            ["type_keyboard", {"keycode": 65}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["get_mouse_position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_keyboard", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
            ["generate_xml_report"]
        ]

    elif sys.platform in ["linux", "linux2"]:
        test_list = [
            ["set_record_enable", {"set_enable": True}],
            ["type_keyboard", {"keycode": 38}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["get_mouse_position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_keyboard", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
            ["generate_xml_report"]
        ]
    elif sys.platform in ["darwin"]:
        test_list = [
            ["set_record_enable", {"set_enable": True}],
            ["type_keyboard", {"keycode": 0x00}],
            ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["get_mouse_position"],
            ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
            ["type_keyboard", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}],
            ["generate_xml_report"]
        ]
    print("\n\n")
    execute_action(test_list)
