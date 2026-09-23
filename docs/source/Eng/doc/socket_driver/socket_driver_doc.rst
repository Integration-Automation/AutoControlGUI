==========================
Socket Server (Remote API)
==========================

.. warning::

   This is an **experimental** feature.

The Socket Server allows other programming languages (or remote machines) to use AutoControl
by sending JSON commands over TCP.

Starting the Server
===================

.. code-block:: python

   import sys
   from je_auto_control import start_autocontrol_socket_server

   try:
       server = start_autocontrol_socket_server(host="localhost", port=9938)
       while not server.close_flag:
           pass
       sys.exit(0)
   except Exception as error:
       print(repr(error))

The server runs in a background thread and listens for JSON action commands.

Sending Commands (Client)
=========================

.. code-block:: python

   import socket
   import json

   sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
   sock.connect(("localhost", 9938))

   command = json.dumps([
       ["AC_set_mouse_position", {"x": 500, "y": 300}],
       ["AC_click_mouse", {"mouse_keycode": "mouse_left"}]
   ])
   sock.sendall((command + "\n").encode("utf-8"))

   response = b""
   while b"Return_Data_Over_JE" not in response:
       chunk = sock.recv(8192)
       if not chunk:
           break
       response += chunk
   print(response.decode("utf-8"))
   sock.close()

Protocol Details
================

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - Property
     - Value
   * - Encoding
     - UTF-8
   * - End-of-response marker
     - ``Return_Data_Over_JE``
   * - Shutdown command
     - Send ``"quit_server"`` to stop the server
   * - Request framing
     - One command per connection: the JSON action list followed by a
       newline. Indented JSON is fine; the command ends at the newline after
       which it parses (or at the client's half-close).
   * - Response framing
     - One line per result, then ``Return_Data_Over_JE`` and a newline. Read
       until the marker; one ``recv`` may return only part of the reply.
   * - Default port
     - 9938
