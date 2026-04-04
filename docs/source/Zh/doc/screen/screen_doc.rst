========
螢幕操作
========

AutoControl 提供截圖與取得螢幕資訊的功能。

截圖
====

擷取目前螢幕畫面並儲存為檔案：

.. code-block:: python

   from je_auto_control import screenshot

   # 全螢幕截圖
   screenshot("my_screenshot.png")

   # 擷取特定區域 [x1, y1, x2, y2]
   screenshot("region.png", screen_region=[100, 100, 500, 400])

螢幕尺寸
========

取得目前螢幕解析度：

.. code-block:: python

   from je_auto_control import screen_size

   width, height = screen_size()
   print(f"螢幕解析度: {width} x {height}")

取得像素顏色
============

取得指定座標的像素顏色：

.. code-block:: python

   from je_auto_control import get_pixel

   color = get_pixel(500, 300)
   print(f"(500, 300) 的像素顏色: {color}")
