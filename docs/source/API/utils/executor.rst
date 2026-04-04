============
Executor API
============

The executor is the JSON action interpreter that parses and executes automation scripts.

----

execute_action
==============

.. function:: execute_action(action_list)

   Executes all actions in the given action list.

   :param action_list: A list of actions to execute. Each action is a list of
      ``[function_name, {params}]``.
   :type action_list: list or dict
   :returns: Dictionary mapping each action to its return value.
   :rtype: dict

   **Example:**

   .. code-block:: python

      from je_auto_control import execute_action

      result = execute_action([
          ["AC_set_mouse_position", {"x": 100, "y": 200}],
          ["AC_click_mouse", {"mouse_keycode": "mouse_left"}]
      ])

----

execute_files
=============

.. function:: execute_files(execute_files_list)

   Executes all JSON action files in the given list.

   :param list execute_files_list: List of file paths to execute.
   :returns: List of execution results for each file.
   :rtype: list

   **Example:**

   .. code-block:: python

      from je_auto_control import execute_files, get_dir_files_as_list

      execute_files(get_dir_files_as_list("./actions/"))

----

add_command_to_executor
=======================

.. function:: add_command_to_executor(command_dict)

   Adds custom commands to the executor's event dictionary.

   :param dict command_dict: Dictionary of ``{"command_name": callable}`` to add.

   **Example:**

   .. code-block:: python

      from je_auto_control import executor

      def my_custom_function(message):
          print(f"Custom: {message}")

      executor.event_dict["my_func"] = my_custom_function
