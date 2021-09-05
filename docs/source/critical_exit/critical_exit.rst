AutoControlGUI Critical Exit
==========================

| critical exit

.. code-block:: python

    from je_auto_control import CriticalExit
    from je_auto_control import keys_table
    from je_auto_control import press_key
    from je_auto_control import release_key
    """
    Create critical exit listener default exit key is keyboard f7
    """
    critical_exit_thread = CriticalExit()
    """
    set exit key you can use any key in keys_table
    """
    print(keys_table.keys())
    critical_exit_thread.set_critical_key("f2")
    """
    Start listener
    """
    critical_exit_thread.init_critical_exit()

    """
    now auto press f2 will stop this program
    """
    try:
        while True:
            press_key("f2")
    except KeyboardInterrupt:
        pass

| with exception

.. code-block:: python

    from time import sleep

    from je_auto_control import set_position
    from je_auto_control import size
    from je_auto_control import CriticalExit
    from je_auto_control import press_key
    from je_auto_control import AutoControlMouseException

    """
    print your screen width and height
    """
    print(size())

    """
    simulate you can't use your mouse because you use while true to set mouse position
    """
    try:
        while True:
            set_position(200, 400)
            set_position(400, 600)
            raise AutoControlMouseException
    except AutoControlMouseException:
        CriticalExit().init_critical_exit()
        press_key("f7")


