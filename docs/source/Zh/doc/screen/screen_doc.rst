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

``screen_region`` 用的是滑鼠座標。在 Windows 上它可以落在任何一個螢幕——位於
主螢幕左側或上方的螢幕座標是負的，例如 ``screen_region=[-1920, 0, -1720, 100]``
——回傳的影像一律是 ``x2 - x1`` 乘 ``y2 - y1``：區域超出桌面的部分是黑色，整個
區域都不在任何螢幕上則丟出 ``AutoControlScreenException``。不帶
``screen_region`` 時擷取主螢幕。

Windows 的座標與 DPI
--------------------

``import je_auto_control`` 會把行程設成 **per-monitor DPI 感知（v2）**；Windows
版本太舊，或行程的感知已經被決定（嵌入的 host 程式、manifest）時，退回系統感知。
per-monitor 的意思是每個螢幕都用自己的實體像素：一個 1920x1080 的螢幕，不論縮放
設定是多少，對滑鼠、對 ``screenshot``、對視窗函式都是 1920 寬，擷取到的影像也
不會被縮放。

在此之前行程是\ *系統*\ 感知，縮放比例與主螢幕不同的螢幕會被 Windows 虛擬化：
它看起來是實際大小的「主螢幕縮放 ÷ 該螢幕縮放」倍（主螢幕 100%、旁邊 125% 的
1920x1080 螢幕會變成 1536x864），截到的是縮過的模糊影像。在這種螢幕上錄下的
座標、從它裁出來的樣板影像，都是在虛擬化的空間裡取得的，必須重錄；距離該螢幕
左上角 ``(dx, dy)`` 的點，現在位於 ``(dx, dy) × 該螢幕縮放 ÷ 主螢幕縮放``。
主螢幕以及縮放與主螢幕相同的螢幕不受影響。

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
