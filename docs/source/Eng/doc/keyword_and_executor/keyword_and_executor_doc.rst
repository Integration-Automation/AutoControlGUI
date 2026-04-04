====================
Keywords & Executor
====================

The Keyword/Executor system is AutoControl's JSON-based scripting engine. You define automation
steps as JSON arrays (keywords), and the executor interprets and runs them.

Keyword Format
==============

Keywords are JSON arrays where each element is an action:

.. code-block:: json

   [
       ["function_name", {"param_name": "param_value"}],
       ["function_name", {"param_name": "param_value"}]
   ]

For example:

.. code-block:: json

   [
       ["AC_set_mouse_position", {"x": 500, "y": 300}],
       ["AC_click_mouse", {"mouse_keycode": "mouse_left"}],
       ["AC_write", {"write_string": "Hello"}]
   ]

Available Action Commands
=========================

.. list-table::
   :header-rows: 1
   :widths: 20 80

   * - Category
     - Commands
   * - Mouse
     - ``AC_click_mouse``, ``AC_set_mouse_position``, ``AC_get_mouse_position``, ``AC_press_mouse``, ``AC_release_mouse``, ``AC_mouse_scroll``
   * - Keyboard
     - ``AC_type_keyboard``, ``AC_press_keyboard_key``, ``AC_release_keyboard_key``, ``AC_write``, ``AC_hotkey``, ``AC_check_key_is_press``
   * - Image
     - ``AC_locate_all_image``, ``AC_locate_image_center``, ``AC_locate_and_click``
   * - Screen
     - ``AC_screen_size``, ``AC_screenshot``
   * - Record
     - ``AC_record``, ``AC_stop_record``
   * - Report
     - ``AC_generate_html``, ``AC_generate_json``, ``AC_generate_xml``, ``AC_generate_html_report``, ``AC_generate_json_report``, ``AC_generate_xml_report``
   * - Project
     - ``AC_create_project``
   * - Shell
     - ``AC_shell_command``
   * - Executor
     - ``AC_execute_action``, ``AC_execute_files``

Executing a JSON File
=====================

.. code-block:: python

   from je_auto_control import execute_action, read_action_json

   execute_action(read_action_json("actions.json"))

Executing All JSON Files in a Directory
=======================================

.. code-block:: python

   from je_auto_control import execute_files, get_dir_files_as_list

   execute_files(get_dir_files_as_list("./action_files/"))

Extending the Executor
======================

You can dynamically load external Python packages into the executor:

.. code-block:: python

   from je_auto_control import package_manager

   # Load all functions from the 'time' module
   package_manager.add_package_to_executor("time")

After loading, functions are available with the ``package_function`` naming convention.
For example, ``time.sleep`` becomes ``time_sleep``:

.. code-block:: json

   [
       ["time_sleep", {"secs": 2}]
   ]

To inspect the current executor command dictionary:

.. code-block:: python

   from je_auto_control import executor

   print(executor.event_dict)
