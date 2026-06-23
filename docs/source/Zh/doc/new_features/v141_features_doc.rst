線條 / 網格 / 分隔線偵測(Hough)
==================================

``grid_locator`` 把*已找到的*元素框分群成網格;它無法從原始像素找出表格 / 試算表的格線或 UI 分隔線,而
``shape_locator`` 只找封閉矩形。``find_lines``、``find_grid`` 與 ``find_separators`` 以 Canny + 機率 Hough 轉換
偵測直線段、分類為水平 / 垂直 / 斜向、還原表格的列與欄座標(及儲存格),並回傳長分隔線的位置——讓腳本能在無模板下
定址「第 3 列、第 2 欄」或在分隔處切分面板。

在可注入的 ``haystack``(ndarray / 路徑 / PIL)上執行,因此可對合成陣列做無頭測試。``cv2.HoughLinesP`` 屬於
OpenCV 核心;OpenCV + NumPy 透過 ``je_open_cv`` 引入。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import find_lines, find_grid, find_separators

    for seg in find_lines(min_length=80, orientation="vertical"):
        print(seg["x1"], seg["y1"], seg["x2"], seg["y2"], seg["length"])

    grid = find_grid(min_length=120)
    cell = grid["cells"][0]                     # 第 0 列、第 0 欄的 {x, y, width, height}
    click(cell["x"] + cell["width"] // 2, cell["y"] + cell["height"] // 2)

    dividers = find_separators(axis="horizontal")   # 各格線的 [y0, y1, ...]

``find_lines`` 為每段回傳 ``{x1, y1, x2, y2, angle, length, orientation}``,最長者優先;傳入非 ``any`` 的
``orientation`` 只保留該類。``find_grid`` 將水平格線分群為列座標、垂直格線分群為欄,回傳 ``{rows, cols, cells}``
(儲存格為相鄰格線之間的矩形)。``find_separators`` 回傳沿 ``axis`` 的長分隔線合併後座標。空白畫面不產生線條 / 儲存格。

執行器命令
----------

``AC_find_lines``(``min_length`` / ``max_gap`` / ``orientation`` / ``region`` → ``{count, lines}``)、
``AC_find_grid``(``min_length`` / ``tol`` / ``region`` → ``{rows, cols, cells}``)與 ``AC_find_separators``
(``axis`` / ``min_length`` / ``tol`` / ``region`` → ``{count, axis, coordinates}``)。它們以 MCP 工具
``ac_find_lines`` / ``ac_find_grid`` / ``ac_find_separators`` 以及 Script Builder 中 **Image** 分類下的命令提供。
