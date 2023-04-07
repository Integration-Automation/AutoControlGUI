Callback Function
----

In AutoControl, callback functions are supported by the Callback Executor.
Below is a simple example of using the Callback Executor:

.. code-block:: python

    from je_auto_control import callback_executor
    # trigger_function will first to execute, but return value need to wait everything done
    # so this test will first print("test") then print(size_function_return_value)
    print(
        callback_executor.callback_function(
            trigger_function_name="size",
            callback_function=print,
            callback_param_method="args",
            callback_function_param={"": "test"}
        )
    )

* Note that if the "name: function" pair in the callback_executor event_dict is different from the executor, it is a bug.
* Of course, like the executor, it can be expanded by adding external functions. Please see the example below.

In this example, we use callback_executor to execute the "size" function defined in AutoControl.
After executing the "size" function, the function passed to callback_function will be executed.
The delivery method can be determined by the callback_param_method parameter.
If it is "args", please pass in {"value1", "value2", ...}.
Here, the ellipsis (...) represents multiple inputs.
 If it is "kwargs", please pass in {"actually_param_name": value, ...}.
Here, the ellipsis (...) again represents multiple inputs.
 If you want to use the return value,
since the return value will only be returned after all functions are executed,
you will actually see the "print" statement
before the "print(size_function_return_value)" statement in this example,
even though the order of size -> print is correct.
This is because the "size" function only returns the value itself without printing it.

This code will load all built-in functions, methods, and classes of the time module into the callback executor.
To use the loaded functions, we need to use the package_function name,
for example, time.sleep will become time_sleep.

If we want to add functions in the callback_executor, we can use the following code:

.. code-block:: python

    from je_auto_control import package_manager
    package_manager.add_package_to_callback_executor("time")

If you need to check the updated event_dict, you can use:

.. code-block:: python

    from je_auto_control import callback_executor
    print(callback_executor.event_dict)