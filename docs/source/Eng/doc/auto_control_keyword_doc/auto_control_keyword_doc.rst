AutoControl Keyword Doc
==========================


.. code-block:: python

   this doc show all keyword can use on keyword json or execute keyword

    format like this : ["keyword": actually_execute_function_name]

    write on json like this:
    [
        ["keyword", {"param_name": param_value}],
        ["keyword", {"param_name": param_value}]
    ]

    # mouse
    "mouse_left": click_mouse,
    "mouse_right": click_mouse,
    "mouse_middle": click_mouse,
    "click_mouse": click_mouse,
    "mouse_table": get_mouse_table,
    "position": position,
    "press_mouse": press_mouse,
    "release_mouse": release_mouse,
    "scroll": scroll,
    "set_position": set_position,
    "special_table": get_special_table,
    # keyboard
    "keys_table": get_keys_table,
    "type_key": type_key,
    "press_key": press_key,
    "release_key": release_key,
    "check_key_is_press": check_key_is_press,
    "write": write,
    "hotkey": hotkey,
    # image
    "locate_all_image": locate_all_image,
    "locate_image_center": locate_image_center,
    "locate_and_click": locate_and_click,
    # screen
    "size": size,
    "screenshot": screenshot,
    # test record
    "set_record_enable": test_record_instance.set_record_enable,
    # generate html
    "generate_html": generate_html,
    # record
    "record": record,
    "stop_record": stop_record,