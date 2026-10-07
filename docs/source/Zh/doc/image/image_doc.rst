========
圖片辨識
========

AutoControl 優先使用 OpenCV 模板匹配技術在螢幕上定位 UI 元素。
可用於尋找按鈕、圖示或其他視覺元素並與之互動。

缺少 OpenCV 時，NumPy／Pillow 後端提供正規化灰階樣板比對、BGR 截圖陣列、
影像檔讀寫、預覽及固定畫面自愈。Windows arm64 的 Python 3.11+ 會安裝
NumPy 2.4.6；既有 Python、``AC_*``、GUI 與 MCP 呼叫沿用同一後端選擇。
畫面最多 16,777,216 像素，每個分塊 FFT 最多 4,194,304 格。
支援 uint8／float32 陣列與 8-bit 影像檔；不支援的操作或預算會拋出框架型別錯誤。
進階 OpenCV 處理與影片仍相依 OpenCV，cryptography 的安全下限不變。

定位所有匹配
============

尋找螢幕上所有符合模板圖片的位置：

.. code-block:: python

   import time
   from je_auto_control import locate_all_image, screenshot

   time.sleep(2)

   # detect_threshold: 0.0 ~ 1.0（1.0 = 完全匹配）
   image_data = locate_all_image(
       screenshot(),
       detect_threshold=0.9,
       draw_image=False
   )
   print(image_data)  # [[x1, y1, x2, y2], ...]

定位圖片中心
============

尋找模板圖片並回傳其中心座標：

.. code-block:: python

   import time
   from je_auto_control import locate_image_center, screenshot

   time.sleep(2)

   cx, cy = locate_image_center(
       screenshot(),
       detect_threshold=0.9,
       draw_image=False
   )
   print(f"找到位置: ({cx}, {cy})")

定位並點擊
==========

尋找模板圖片並自動點擊其中心：

.. code-block:: python

   import time
   from je_auto_control import locate_and_click, screenshot

   time.sleep(2)

   image_data = locate_and_click(
       screenshot(),
       "mouse_left",
       detect_threshold=0.9,
       draw_image=False
   )
   print(image_data)

參數說明
========

.. list-table::
   :header-rows: 1
   :widths: 25 15 60

   * - 參數
     - 型別
     - 說明
   * - ``image``
     - str / PIL Image
     - 要搜尋的模板圖片（檔案路徑或 PIL ``ImageGrab.grab()`` 結果）
   * - ``detect_threshold``
     - float
     - 偵測精確度，範圍 ``0.0`` 到 ``1.0``。``1.0`` 要求完全匹配。
   * - ``draw_image``
     - bool
     - 若為 ``True``，會在回傳的圖片上標記偵測到的區域。
