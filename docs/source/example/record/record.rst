========================
AutoControlGUI Record
========================

| macos can't use record but can use execute action
| record keyboard and mouse event

.. code-block:: python

    from time import sleep

    from je_auto_control import record
    from je_auto_control import stop_record
    from je_auto_control import type_key
    from je_auto_control import execute_action

    """
    this program will type test two time
    one time is type key one time is record
    """
    record()
    sleep(1)
    print(type_key("t"))
    print(type_key("e"))
    print(type_key("s"))
    print(type_key("t"))
    sleep(2)
    record_result = stop_record()
    print(record_result)
    execute_action(record_result)
    sleep(2)


| record your mouse & keyboard event 5s

.. code-block:: python

    from je_auto_control import record
    from je_auto_control import stop_record
    from je_auto_control import execute_action

    record()
    from time import sleep
    sleep(5)
    record_result = stop_record()
    print(record_result)
    execute_action(record_result)
    sleep(2)