=====================
Callback Function API
=====================

The Callback Executor runs a trigger function and then invokes a callback.

----

callback_function
=================

.. function:: callback_executor.callback_function(trigger_function_name, callback_function, callback_function_param=None, callback_param_method="kwargs", **kwargs)

   Executes a trigger function from the event dictionary, then calls a callback function.

   :param str trigger_function_name: Name of the function to trigger (must exist in ``event_dict``).
   :param callable callback_function: Function to call after the trigger completes.
   :param dict callback_function_param: Parameters for the callback function. Pass ``None`` for no parameters.
   :param str callback_param_method: How to pass parameters to the callback:

      - ``"args"`` -- unpack as positional arguments
      - ``"kwargs"`` -- unpack as keyword arguments

   :param kwargs: Keyword arguments passed to the trigger function.
   :returns: Return value of the trigger function.

   **Example:**

   .. code-block:: python

      from je_auto_control import callback_executor

      def on_complete(width, height):
          print(f"Screen size: {width}x{height}")

      result = callback_executor.callback_function(
          trigger_function_name="screen_size",
          callback_function=on_complete,
          callback_param_method="args"
      )
