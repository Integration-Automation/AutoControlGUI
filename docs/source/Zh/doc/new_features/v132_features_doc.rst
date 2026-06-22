以邊緣 / 輪廓定位 UI 元素(免模板)
====================================

目前所有定位器都需要一個*尋找對象*:``match_template`` 與 ``feature_match`` 需要參考影像、``find_color_region``
需要顏色、``locate_text`` 需要文字。它們都無法回答結構性問題「這個畫面上可點擊的方框在哪裡?」。``find_shapes``
與 ``find_rectangles`` 執行 Canny 邊緣偵測加輪廓擷取,回傳各個形狀的邊界框——讓腳本能在從未見過的畫面上列舉
卡片、按鈕或輸入框,並對第 N 個操作,完全不需提供樣本。

兩者都在可注入的 ``haystack`` 影像(ndarray / 路徑 / PIL)上執行,因此可在無真實螢幕下對合成陣列做單元測試。
OpenCV + NumPy 透過 ``je_open_cv`` 引入。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import find_shapes, find_rectangles

    # 每個獨立形狀,由大到小。
    for shape in find_shapes(min_area=500):
        print(shape["x"], shape["y"], shape["width"], shape["height"])

    # 只取寬的按鈕形矩形,點擊第一個。
    buttons = find_rectangles(min_area=800, aspect_range=(1.5, 8.0))
    if buttons:
        click(*buttons[0]["center"])

``find_shapes`` 為每個輪廓回傳 ``{x, y, width, height, area, center, aspect}``(``area`` 為邊界框面積),由大到小;
``min_area`` / ``max_area`` 去除雜點與整框邊界。``find_rectangles`` 只保留近似凸四邊形的輪廓(``epsilon`` 是
``approxPolyDP`` 以周長比例表示的容差),並加上選用的 ``aspect_range``(min, max)寬高比過濾——``(1.5, 8)`` 取寬
按鈕、``(0.8, 1.2)`` 取方形圖示。

執行器命令
----------

``AC_find_shapes``(``region`` / ``min_area`` / ``max_area`` → ``{count, shapes}``)與 ``AC_find_rectangles``
(另有 ``aspect_range`` / ``epsilon`` → ``{count, rectangles}``)。它們以 MCP 工具 ``ac_find_shapes`` /
``ac_find_rectangles`` 以及 Script Builder 中 **Image** 分類下的命令提供。
