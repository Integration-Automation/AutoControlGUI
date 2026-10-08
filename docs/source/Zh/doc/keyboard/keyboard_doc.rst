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

Windows 的按鍵表也收常見的別名（``ctrl``、``alt``、``enter``、``esc``、``win``、``backspace``、
``del``、``pgup``、``capslock``、``prtsc``、``numpad0``……）。要把錄到的鍵碼換回名字，用
``keyboard_key_name``；它一律回標準名稱，不會回別名：

.. code-block:: python

   from je_auto_control import keyboard_key_name

   keyboard_key_name(27)     # Windows 上是 "escape"
   keyboard_key_name(0xBB)   # "oem_plus"

Windows 上有八個名字代表的是\ *字元*\ 而不是按鍵位置：``slash``\ （``/``\ ）、
``backslash``\ （``\``\ ）、``semicolon``\ （``;``\ ）、``quote``\ （``'``\ ）、
``backquote``\ （反引號）、``bracketleft``\ （``[``\ ）、``bracketright``\ （``]``\ ）
與 ``equal``\ （``=``\ ）。它們在查表的當下才解析：向前景視窗的鍵盤配置詢問哪個鍵
打得出該字元（``VkKeyScanExW``\ ），所以在 ``;`` 不在美式位置的配置上，
``press_keyboard_key("semicolon")`` 仍會按到正確的鍵。配置上沒有不加修飾鍵就能
打出該字元的鍵時——德文鍵盤的 ``/`` 是 Shift+7——這個名字退回美式位置的鍵。
``oem_1`` … ``oem_8`` 仍然是固定位置；``keys_table`` 列出這八個名字時顯示的是
美式位置的鍵碼。

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

大寫字母會打成大寫：``write`` 在 Windows 與 X11 會在那個鍵外面按住 Shift（以前會
打成小寫）。Windows 換行（CR LF）是一個換行，只按一次 Enter，不是兩次。
``is_shift=True`` 會在每個鍵外面按住 Shift，而且每個平台都有效；``type_keyboard``、
``press_keyboard_key`` 與 ``hotkey`` 也一樣，以前在 macOS 以外會被忽略。

``write`` 會把文字寫進 log、記進測試紀錄並回傳。密碼或 token 請用
``write_secret``\ （命令是 ``AC_write_secret``，參數 ``secret``）：log 只記長度、
紀錄只留遮蔽值、不回傳任何東西，錯誤訊息也不會帶出任何字元。它把每個字元都以
Unicode 按鍵事件送出，所以不論鍵盤配置與 Caps Lock 狀態，送到的文字一字不差
（換行、Tab 與 Backspace 以按鍵送出）；鍵盤後端不支援 Unicode 輸入時（目前只有
Windows 支援），在打任何字之前就拒絕。

.. code-block:: python

   import os
   from je_auto_control import write_secret

   write_secret(os.environ["APP_PASSWORD"])

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
