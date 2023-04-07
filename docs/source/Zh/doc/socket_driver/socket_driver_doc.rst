Socket Driver
----

* This is an experimental feature.
* The Socket Server is mainly used to allow other programming languages to use AutoControl.
* It processes received strings and performs actions through the underlying executor.
* Tests can be performed remotely through this feature.
* Currently, Java and C# support are experimental.
* Return_Data_Over_JE should be transmitted at the end of each paragraph.
* UTF-8 encoding is used.
* Sending quit_server will shut down the server.

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