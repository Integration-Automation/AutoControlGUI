========
鍵盤控制
========

AutoControl 提供模擬鍵盤輸入的功能，包括按鍵按下/釋放、輸入字串、
熱鍵組合及按鍵狀態偵測。

取得按鍵表
==========

取得可用的按鍵名稱：

.. code-block:: python

   from je_auto_control import keys_table, get_special_table

   # 取得所有可用按鍵
   print(keys_table)

   # 取得特殊按鍵（因平台而異）
   print(get_special_table())

.. tip::

   完整的鍵盤按鍵列表請參考 :doc:`/API/special/keyboard_keys`。

按下與釋放
==========

按住按鍵，延遲後釋放：

.. code-block:: python

   from time import sleep
   from je_auto_control import press_keyboard_key, release_keyboard_key

   press_keyboard_key("a")
   sleep(1)
   release_keyboard_key("a")

按下單一按鍵
============

按下並立即釋放一個按鍵：

.. code-block:: python

   from je_auto_control import type_keyboard

   type_keyboard("a")

檢查按鍵狀態
=============

檢查某個按鍵是否正被按住：

.. code-block:: python

   from je_auto_control import check_key_is_press

   is_pressed = check_key_is_press("a")
   print(f"按鍵 'a' 被按住: {is_pressed}")

輸入字串
========

逐字輸入一串字元：

.. code-block:: python

   from je_auto_control import write

   write("Hello World")

熱鍵組合
========

依序按下多個按鍵，再反向釋放：

.. code-block:: python

   import sys
   from je_auto_control import hotkey

   if sys.platform in ["win32", "cygwin", "msys"]:
       hotkey(["lcontrol", "a", "lcontrol", "c", "lcontrol", "v"])

   elif sys.platform == "darwin":
       hotkey(["command", "a", "command", "c", "command", "v"])

   elif sys.platform in ["linux", "linux2"]:
       hotkey(["ctrl", "a", "ctrl", "c", "ctrl", "v"])

.. warning::

   按鍵名稱在不同平台上有所不同，請務必查閱目標平台的按鍵表。
