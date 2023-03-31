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
