=================
Callback Executor
=================

The Callback Executor allows you to execute an automation function and trigger a callback
function upon completion.

Basic Usage
===========

.. code-block:: python

   from je_auto_control import callback_executor

   result = callback_executor.callback_function(
       trigger_function_name="screen_size",
       callback_function=print,
       callback_param_method="args",
       callback_function_param={"": "Callback triggered!"}
   )
   print(f"Return value: {result}")

How It Works
============

1. The ``trigger_function_name`` function executes first.
2. After it completes, the ``callback_function`` is called.
3. The return value of the trigger function is returned after all callbacks finish.

Parameters
==========

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Parameter
     - Description
   * - ``trigger_function_name``
     - Name of the function to execute (must exist in ``event_dict``)
   * - ``callback_function``
     - The function to call after the trigger function completes
   * - ``callback_function_param``
     - Parameters to pass to the callback function (dict)
   * - ``callback_param_method``
     - ``"args"`` for positional or ``"kwargs"`` for keyword arguments
   * - ``**kwargs``
     - Additional keyword arguments passed to the trigger function

Extending the Callback Executor
================================

Load external package functions into the callback executor:

.. code-block:: python

   from je_auto_control import package_manager

   # Add all functions from the 'time' module
   package_manager.add_package_to_callback_executor("time")

To inspect the current event dictionary:

.. code-block:: python

   from je_auto_control import callback_executor

   print(callback_executor.event_dict)

.. note::

   The callback executor's ``event_dict`` should contain the same function mappings as the
   main executor. If they differ, it is a bug.
