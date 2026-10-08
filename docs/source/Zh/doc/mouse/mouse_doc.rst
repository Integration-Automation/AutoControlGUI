========
滑鼠控制
========

AutoControl 提供模擬滑鼠操作的功能，包括點擊、定位、捲動及拖曳操作。

取得滑鼠按鍵表
==============

取得所有可用的滑鼠按鍵名稱：

.. code-block:: python

   from je_auto_control import mouse_table

   print(mouse_table)

.. tip::

   完整的滑鼠按鍵列表請參考 :doc:`/API/special/mouse_keys`。

按下與釋放
==========

按住滑鼠按鍵，延遲後釋放：

.. code-block:: python

   from time import sleep
   from je_auto_control import press_mouse, release_mouse

   press_mouse("mouse_right")
   sleep(1)
   release_mouse("mouse_right")

點擊
====

按下並立即釋放滑鼠按鍵：

.. code-block:: python

   from je_auto_control import click_mouse

   # 在目前位置右鍵點擊
   click_mouse("mouse_right")

   # 在指定座標左鍵點擊
   click_mouse("mouse_left", x=500, y=300)

   # 雙擊：在同一點連點兩下，間隔 60 毫秒
   click_mouse("mouse_left", x=500, y=300, clicks=2, interval=0.06)

Windows 與 X11 依兩次點擊的時間差與位移判定雙擊，所以 ``interval`` 要小於系統的雙擊判定時間
（Windows 預設 500 毫秒）。macOS 的應用程式讀的是事件上帶的點擊次數，所以在 macOS 上第 n 次點擊的
點擊次數欄位（``kCGMouseEventClickState``）會設成 n；``interval`` 比系統的雙擊間隔還長時，每一下都當成
單擊送出。

游標位置
========

取得及設定滑鼠游標位置：

.. code-block:: python

   from je_auto_control import get_mouse_position, set_mouse_position

   # 取得目前位置
   x, y = get_mouse_position()
   print(f"滑鼠位置: ({x}, {y})")

   # 移動滑鼠到 (100, 100)
   set_mouse_position(100, 100)

捲動
====

捲動滑鼠滾輪：

.. code-block:: python

   from je_auto_control import mouse_scroll

   # 向上捲動 5 格；負值向下
   mouse_scroll(scroll_value=5)
   mouse_scroll(scroll_value=-5)

每個平台都一樣：正值往上、負值往下。要在指定位置捲動就傳 ``x``／``y``：帶小數的
座標會四捨五入到最近的像素，不是有限數值的座標會在游標移動之前丟出
``AutoControlMouseException``。

.. note::

   在 X11 與 Wayland 上，``scroll_direction`` 指定「正值」的方向：
   ``"scroll_up"``\ （預設）、``"scroll_down"``、``"scroll_left"``、``"scroll_right"``。
   預設值原本是 ``"scroll_down"``，所以 ``mouse_scroll(5)`` 在那裡往下、在 Windows 與
   macOS 往上；要維持舊行為請明確傳 ``scroll_direction="scroll_down"``。
