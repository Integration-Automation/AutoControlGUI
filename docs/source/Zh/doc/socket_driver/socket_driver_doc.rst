==============================
Socket 伺服器（遠端 API）
==============================

.. warning::

   這是 **實驗性** 功能。

Socket 伺服器允許其他程式語言（或遠端機器）透過 TCP 傳送 JSON 指令來使用 AutoControl。

啟動伺服器
==========

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

伺服器在背景執行緒中執行，監聽 JSON 自動化指令。

傳送指令（客戶端）
==================

.. code-block:: python

   import socket
   import json

   sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
   sock.connect(("localhost", 9938))

   command = json.dumps([
       ["AC_set_mouse_position", {"x": 500, "y": 300}],
       ["AC_click_mouse", {"mouse_keycode": "mouse_left"}]
   ])
   sock.sendall(command.encode("utf-8"))

   response = sock.recv(8192).decode("utf-8")
   print(response)
   sock.close()

協定細節
========

.. list-table::
   :header-rows: 1
   :widths: 30 70

   * - 屬性
     - 值
   * - 編碼
     - UTF-8
   * - 回應結束標記
     - ``Return_Data_Over_JE``
   * - 關閉伺服器指令
     - 傳送 ``"quit_server"`` 以停止伺服器
   * - 預設連接埠
     - 9938
