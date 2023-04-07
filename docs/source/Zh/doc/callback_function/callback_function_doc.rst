回調函數 文件
----

在 AutoControl 裡，Callback function 是由 Callback Executor 提供支援，
以下是簡易的使用 Callback Executor 的範例，
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

* ( 注意!，如果 callback_executor event_dict 裡面包含的 name: function 需與 executor 一樣，不一樣則是 Bug)
* (當然跟 executor 一樣可以藉由添加外部 function 來擴充，請看下面例子)

在這個範例裡，我們使用 callback_executor 執行定義在 AutoControl 的 size function，
然後執行完 size function 後，會去執行傳遞給 callback_function 的 function，
可以由 callback_param_method 參數來決定要使用的傳遞方法，
如果是 "args" 請傳入 {"any_name_but_not_duplicate": value, ...} 這裡 ... 代表可以複數傳入，
如果是 "kwargs" 請傳入 {"actually_param_name": value, ...} 這裡 ... 代表可以複數傳入，
然後如果要使用回傳值的話，由於回傳值會在所有 function 執行完後才回傳，
實際上 size -> print 順序沒錯，但此例會先看到 print 之後才是 print(size_function_return_value)，
因為 size function 只有回傳值本身沒有 print 的動作。

如果我們想要在 callback_executor 裡面添加 function，可以使用如下:
這段程式碼會把所有 time module 的 builtin, function, method, class
載入到 callback executor，然後要使用被載入的 function 需要使用 package_function 名稱，
例如 time.sleep 會變成 time_sleep
.. code-block:: python
    from je_auto_control import package_manager
    package_manager.add_package_to_callback_executor("time")

如果你需要查看被更新的 event_dict 可以使用
.. code-block:: python
    from je_auto_control import callback_executor
    print(callback_executor.event_dict)