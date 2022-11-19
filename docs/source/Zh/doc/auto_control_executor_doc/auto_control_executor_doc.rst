AutoControlGUI Executor Doc
==========================

.. code-block:: python

    def execute_action(action_list: list):
        """
        use to execute all action on action list(action file or python list)
        :param action_list the list include action
        for loop the list and execute action
        """

    """
    Executor example
    on program or action file
    use format like bottom
    [function_name, {param: value,...}]
    if no param use [function_name]
    """
    from je_auto_control import execute_action
    from je_auto_control import test_record
    "windows"
    example_list = [
        ["type_key", {"keycode": 65}],
        ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["position"],
        ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}]
    ]
    "macos"
    example_list = [
        ["type_key", {"keycode": 0x00}],
        ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["position"],
        ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["type_key", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}]
    ]
    "linux"
    example_list = [
        ["type_key", {"keycode": 38}],
        ["mouse_left", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["position"],
        ["press_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["release_mouse", {"mouse_keycode": "mouse_left", "x": 500, "y": 500}],
        ["type_key", {"mouse_keycode": "dwadwawda", "dwadwad": 500, "wdawddwawad": 500}]
    ]
    execute_action(example_list)

    def read_action_json(json_file_path: str):
    """
    use to read action file
    :param json_file_path json file's path to read
    """

    def write_action_json(json_save_path: str, action_json: list):
    """
    use to save action file
    :param json_save_path  json save path
    :param action_json the json str include action to write
    """

.. code-block:: python

    def execute_files(execute_files_list: list):
    """
    :param execute_files_list: list include execute files path
    :return: every execute detail as list
    """
