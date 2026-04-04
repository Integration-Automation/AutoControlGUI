=================
Socket Server API
=================

TCP server for receiving and executing JSON automation commands remotely.

----

start_autocontrol_socket_server
===============================

.. function:: start_autocontrol_socket_server(host="localhost", port=9938)

   Starts a threaded TCP server that accepts JSON automation commands.

   :param str host: Server hostname. Defaults to ``"localhost"``.
   :param int port: Server port. Defaults to ``9938``.
   :returns: The server instance. Check ``server.close_flag`` to detect shutdown.
   :rtype: TCPServer

   The server can also read ``host`` and ``port`` from command-line arguments
   (``sys.argv[1]`` and ``sys.argv[2]``).

----

TCPServer
=========

.. class:: TCPServer(server_address, RequestHandlerClass)

   Threaded TCP server (extends ``socketserver.ThreadingMixIn`` and ``socketserver.TCPServer``).

   .. attribute:: close_flag
      :type: bool

      Set to ``True`` when the server receives a ``"quit_server"`` command.

----

TCPServerHandler
================

.. class:: TCPServerHandler

   Request handler for the TCP server.

   Receives up to 8192 bytes per request, decodes as UTF-8, and processes:

   - ``"quit_server"`` -- shuts down the server.
   - Any other string -- parsed as JSON and passed to ``execute_action()``.
     Results are sent back to the client, terminated by ``"Return_Data_Over_JE"``.
