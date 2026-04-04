========
緊急退出
========

緊急退出是一種安全機制，允許你透過按下熱鍵（預設：**F7**）來強制停止自動化腳本。

.. warning::

   緊急退出 **預設為關閉**。啟用後會額外消耗系統資源，
   因為會在背景執行緒中持續監控鍵盤。

啟用緊急退出
============

.. code-block:: python

   from je_auto_control import CriticalExit

   CriticalExit().init_critical_exit()

呼叫 ``init_critical_exit()`` 後，按下 **F7** 會中斷主執行緒並終止程式。

更改熱鍵
========

.. code-block:: python

   from je_auto_control import CriticalExit

   critical = CriticalExit()
   critical.set_critical_key("escape")  # 使用 Escape 取代 F7
   critical.init_critical_exit()

範例：從失控的滑鼠恢復
======================

.. code-block:: python

   import sys
   from je_auto_control import (
       CriticalExit, AutoControlMouseException,
       set_mouse_position, screen_size, press_keyboard_key
   )

   print(screen_size())

   try:
       while True:
           set_mouse_position(200, 400)
           set_mouse_position(400, 600)
           raise AutoControlMouseException
   except Exception as error:
       print(repr(error), file=sys.stderr)
       CriticalExit().init_critical_exit()
       press_keyboard_key("f7")

.. danger::

   測試持續移動滑鼠的自動化迴圈時請極度小心。
   務必啟用緊急退出或準備其他方式來重新取得控制。
