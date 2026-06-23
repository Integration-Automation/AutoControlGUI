局部動態 / 活動偵測
====================

三個相近鄰居,各有區別:``wait_until_screen_stable`` 在即時輪詢迴圈上回傳*布林值*(不是對可注入配對的局部方框);
``ssim_changed_regions`` 是*結構性*的(高斯視窗 SSIM、耐光照——刻意忽略你想抓的快速像素動態);``diff_screenshots``
標示像素差但不以活動區塊 + 分數呈現。``changed_regions`` / ``has_motion`` / ``activity_score`` 是便宜的 absdiff
路徑:兩幀之間哪些子區域在*移動*,讓腳本能挑選安靜區域或定位忙碌的轉圈動畫。

它們在兩個可注入的幀(ndarray / 路徑 / PIL)上運作,因此可對合成陣列做無頭測試,並沿用共用的連通元件輔助函式。
OpenCV + NumPy 透過 ``je_open_cv`` 引入。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import changed_regions, has_motion, activity_score

    before = screenshot_to_array()
    # ... 經過一段時間 ...
    for box in changed_regions(before, after):     # 移動的方框,由大到小
        print(box["x"], box["y"], box["width"], box["height"])

    if has_motion(before, after):
        print("still animating, activity =", activity_score(before, after))

``changed_regions`` 對絕對差做門檻(``threshold``)、去噪(``blur``)、膨脹,回傳至少 ``min_area`` 的
``{x, y, width, height, area, center}`` 區塊,由大到小。``has_motion`` 是布林形式;``activity_score`` 是移動像素的
比例(0..1)。不同尺寸的幀會丟出 ``ValueError``。

執行器命令
----------

``AC_changed_regions``(``before`` / ``after`` / ``threshold`` / ``min_area`` / ``blur`` → ``{count, regions}``)與
``AC_has_motion``(``before`` / ``after`` / ``threshold`` / ``min_area`` → ``{moved, activity}``);``after`` 預設為
即時螢幕擷取。它們以 MCP 工具 ``ac_changed_regions`` / ``ac_has_motion`` 以及 Script Builder 中 **Image** 分類下的
命令提供。
