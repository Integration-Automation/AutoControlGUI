========================
AutoControlGUI Record
========================

| record keyboard and mouse event

.. code-block:: python

    from time import sleep

    from je_auto_control import record
    from je_auto_control import stop_record
    from je_auto_control import type_key
    """
    this program will type test two time
    """
    record()
    type_key("t")
    type_key("e")
    type_key("s")
    type_key("t")
    sleep(1)
    stop_record()
    sleep(1)


| record your event 5s

.. code-block:: python

    from je_auto_control import record
    from je_auto_control import stop_record

    record()
    from time import sleep
    sleep(5)
    stop_record()
    sleep(2)