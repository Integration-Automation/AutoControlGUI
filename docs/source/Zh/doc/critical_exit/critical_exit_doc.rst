緊急退出
----

* Critical Exit 是提供故障保護的機制。
* Critical Exit 預設是關閉的。
* 如果開啟，預設按鍵是 F7。
* 開啟的方法是 CriticalExit().init_critical_exit() (開啟後會額外消耗系統資源)

以下這個範例是讓滑鼠不受控制的移動並拋出例外，
當接收到例外，初始化 Critical Exit 並自動按下 F7，
( 注意! 如果修改這個範例必須極度小心。 )
(你可能會失去對你電腦的控制，例如滑鼠不受控制)

.. code-block:: python

    import sys

    from je_auto_control import AutoControlMouseException
    from je_auto_control import CriticalExit
    from je_auto_control import press_key
    from je_auto_control import set_position
    from je_auto_control import size

    # print your screen width and height

    print(size())

    # simulate you can't use your mouse because you use while true to set mouse position

    try:
        from time import sleep
        # Or no sleep
        sleep(3)
        while True:
            set_mouse_position(200, 400)
            set_mouse_position(400, 600)
            raise AutoControlMouseException
    except Exception as error:
        print(repr(error), file=sys.stderr)
        CriticalExit().init_critical_exit()
        press_key("f7")