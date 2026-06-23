欄位感知閱讀順序(XY-Cut)
==========================

``element_parse.reading_order`` 是平面的上到下 / 左到右排序——在任何多欄頁面都會交錯欄位
(眾所周知的 naive 排序失敗:它先讀 A 欄第 1 列、再讀 B 欄第 1 列、再讀 A 欄第 2 列…)。
``reading_flow`` 以遞迴 **XY-cut** 還原正確順序:在最寬的留白谷反覆切分(垂直 gutter → 欄、
水平 gutter → 列 / 區塊),因此兩欄版面會*完整讀完*A 欄,再讀 B 欄。

公開的展平函式命名為 ``flow_order``,以*並列*而非遮蔽 ``element_parse.reading_order``;它回傳
相同的 ``index`` 標記元素契約,因此是欄位感知的直接升級。純標準函式庫幾何,作用於純框字典
(不需影像、不需 OCR 引擎);重用 ``table_grid_fill`` 的框邊界讀取器。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import flow_order, xy_cut, to_blocks

    # 兩欄各兩列:讀作 A1, A2, B1, B2——而非 A1, B1, A2, B2
    for element in flow_order(ocr_boxes, min_gap=12):
        print(element["index"], element["text"])

    tree = xy_cut(ocr_boxes, min_gap=12)     # {type, axis, children|boxes}
    blocks = to_blocks(tree)                  # 依閱讀順序的葉區塊

``flow_order`` 以欄位感知閱讀順序回傳各框,每個帶 ``index``。``xy_cut`` 回傳遞迴區域樹
(每個節點為對 ``axis`` ``"x"`` / ``"y"`` 的 ``split`` 或框的 ``leaf``)。``to_blocks`` 把樹
展平為依序的葉區塊。``min_gap`` 為被視為欄 / 列分隔的最小留白谷。

執行器指令
----------

``AC_flow_order``(``boxes`` / ``min_gap`` → ``{count, elements}``)與 ``AC_xy_cut``
(``boxes`` / ``min_gap`` → ``{tree}``)。兩者以 MCP 工具 ``ac_flow_order`` / ``ac_xy_cut``
(唯讀)及 Script Builder 指令 **Reading Order (column-aware)** / **XY-Cut Region Tree**
(位於 **OCR** 分類下)形式提供。
