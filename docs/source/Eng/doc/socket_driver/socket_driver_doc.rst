Socket Driver 文件
----

* 實驗性的功能。
* Socket Server 主要用來讓其他程式語言也可以使用 AutoControl。
* 透過底層的 executor 處理接收到字串並進行執行動作。
* 可以透過遠端來執行測試的動作。

* 目前有實驗性的 Java 與 C# 支援。
* 每個段落結束都應該傳輸 Return_Data_Over_JE。
* 使用 UTF-8 encoding。
* 傳送 quit_server 將會關閉伺服器。

.. code-block:: python

    import sys

    from je_auto_control import start_autocontrol_socket_server

    try:
        server = start_autocontrol_socket_server()
        while not server.close_flag:
            pass
        sys.exit(0)
    except Exception as error:
        print(repr(error))