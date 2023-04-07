緊急退出
----

* Critical Exit is a mechanism that provides fault protection.
* Critical Exit is disabled by default.
* If enabled, the default hotkey is F7.
* To enable Critical Exit, call CriticalExit().init_critical_exit()
* (enabling it will consume additional system resources).

The following example is to make the mouse move uncontrollably and throw an exception.
When the exception is caught, initialize the Critical Exit and automatically press F7.
(Note! If you modify this example, you must be extremely careful.
You may lose control of your computer, such as the mouse being out of control.)

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