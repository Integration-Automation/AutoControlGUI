========================
AutoControlGUI Execute action
========================

| save action json
| you can use write_action_json to save action file
| and then use read_action_json to read action file to execute
.. code-block:: python

    import os
    import json
    from queue import Queue

    from je_auto_control import read_action_json
    from je_auto_control import write_action_json

    test_queue = Queue()
    test_queue.put(("test_action", 100, 100))
    test_queue.put(("test_action", 400, 400))
    test_queue.put(("test_action", 200, 200))
    test_list = list(test_queue.queue)
    test_dumps_json = json.dumps(test_list)
    print(test_dumps_json)
    test_loads_json = json.loads(test_dumps_json)
    print(test_loads_json)
    list(test_loads_json)

    write_action_json(os.getcwd() + "/test.json", test_dumps_json)
    read_json = read_action_json(os.getcwd() + "/test.json")
    print(read_json)

| execute action

.. code-block:: python

    import sys

    from je_auto_control import execute_action

    test_list = None
    if sys.platform in ["win32", "cygwin", "msys"]:
        test_list = [
            ("type_key", 65),
            ("mouse_left", 500, 500),
            ("position", "position"),
            ("press_mouse", "mouse_left", 500, 500),
            ("release_mouse", "mouse_left", 500, 500)
        ]
    elif sys.platform in ["linux", "linux2"]:
        test_list = [
            ("type_key", 38),
            ("mouse_left", 500, 500),
            ("position", "position"),
            ("press_mouse", "mouse_left", 500, 500),
            ("release_mouse", "mouse_left", 500, 500)
        ]
    elif sys.platform in ["darwin"]:
        test_list = [
            ("type_key", 0x00),
            ("mouse_left", 500, 500),
            ("position", "position"),
            ("press_mouse", "mouse_left", 500, 500),
            ("release_mouse", "mouse_left", 500, 500)
        ]
    execute_action(test_list)


