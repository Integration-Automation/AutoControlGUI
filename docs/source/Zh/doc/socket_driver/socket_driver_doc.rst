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
   sock.sendall((command + "\n").encode("utf-8"))

   response = b""
   while b"Return_Data_Over_JE" not in response:
       chunk = sock.recv(8192)
       if not chunk:
           break
       response += chunk
   print(response.decode("utf-8"))
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
   * - 請求格式
     - 每個連線一個指令：JSON 動作清單加一個換行。可以縮排；指令在能完整解析的
       那個換行結束（或在客戶端關閉寫入端時結束）。
   * - 回應格式
     - 每個結果一行，最後是 ``Return_Data_Over_JE`` 與換行。請讀到這個標記為止；
       單次 ``recv`` 可能只拿到一部分。
   * - 預設連接埠
     - 9938
