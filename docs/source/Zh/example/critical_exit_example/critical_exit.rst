AutoControlGUI Critical Exit
==========================

| critical exit
| if you want to click keyboard key to exit program you can use this module
| when you click what you set on set_critical_key will make program exit
| this example is how to auto use CriticalExit

.. code-block:: python

    from je_auto_control import CriticalExit
    from je_auto_control import keys_table
    from je_auto_control import press_key
    try:
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
        while True:
            press_key("f2")
    except KeyboardInterrupt:
        pass



