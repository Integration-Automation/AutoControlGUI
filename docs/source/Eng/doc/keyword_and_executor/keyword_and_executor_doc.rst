Keyword & Executor
----

Keyword is a JSON file that contains many custom keywords and parameters.
Keywords are used in conjunction with the Executor.
The format of a keyword is as shown in the following example, and the same format is used in the JSON file.

.. code-block:: python

    [
        ["function_name_in_event_dict": {"param_name": param_value}],
        ["function_name_in_event_dict": {"param_name": param_value}],
        ["function_name_in_event_dict": {"param_name": param_value}],
        # many....
        # If you are using position param
        ["function_name_in_event_dict": {param_value1, param_value2....}]
    ]

The executor is an interpreter that can parse JSON files and execute automation scripts.
It can be easily transferred over the network to a remote server or computer,
which can then execute the automation scripts using the executor.

If we want to add a function to the executor, we can use the following code snippet.
This code will load all the built-in functions, methods, and classes of the time module into the executor.
To use the loaded functions, we need to use the package_function name, for example, time.sleep will become time_sleep.

.. code-block:: python

    from je_auto_control import package_manager
    package_manager.add_package_to_executor("time")



If you need to check the updated event_dict, you can use:

.. code-block:: python

    from je_auto_control import executor
    print(executor.event_dict)

If we want to execute a JSON file

.. code-block:: python

    from je_auto_control import execute_action, read_action_json
    execute_action(read_action_json(file_path))

If we want to execute all JSON files in a folder, we can use the following code snippet:

.. code-block:: python

    from je_auto_control import execute_files, get_dir_files_as_list
    execute_files(get_dir_files_as_list(dir_path))