留白投影欄位偵測(無框線表格)
==============================

``ocr/structure`` 只有在*每一列*的儲存格左緣 x 都在容差內相符時才偵測得到表格——對 ragged
或無框線表格、右對齊數字欄、或任何缺格的列都會失敗。``edge_lines.find_grid`` 需要框線,
因此純以留白繪製的表格根本沒有網格。``column_layout`` 以版面分析文獻常用的穩健方法找欄位:
靠*間隙*。它把 OCR 框投影到 x 軸(墨水密度剖面),讀出持續為空的垂直帶作為欄間隙(gutter),
為每個框指派欄索引,並依垂直間距分群成列,輸出無框線表格。

純標準函式庫,作用於純框字典(差分陣列投影——不需 numpy),因此可在無影像、無 OCR 引擎下
完整單元測試。重用 ``table_grid_fill`` 的框邊界讀取器。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (detect_borderless_table, column_gutters,
                                 assign_columns, vertical_projection)

    table = detect_borderless_table(ocr_boxes)
    # {"n_rows": 3, "n_cols": 2, "rows": [["Name","Age"],["Ann","30"],["Bob","25"]],
    #  "columns": [{"start": 70, "end": 120, "width": 50}]}

    gutters = column_gutters(ocr_boxes, min_gap=8)   # 空白垂直帶
    tagged = assign_columns(ocr_boxes)               # 每個框 + "column" 索引
    profile = vertical_projection(ocr_boxes)         # 每個 x 的墨水密度

``vertical_projection`` 回傳每個 x 的墨水密度剖面;``column_gutters`` 回傳至少 ``min_gap`` 寬
的內部空白帶 ``[{start, end, width}]``;``assign_columns`` 為每個框標上 0 起算的 ``column``;
``detect_borderless_table`` 將欄(來自 gutter)與列(來自垂直間距)組合成
``{n_rows, n_cols, rows, columns}``,或在欄數少於 ``min_cols`` / 列數少於 ``min_rows`` 時回傳
``None``。框接受 ``{x, y, width, height}`` 或 ``{left, top, right, bottom}`` 加上可選 ``text``。

執行器指令
----------

``AC_detect_borderless_table``(``boxes`` / ``page_width`` / ``min_gap`` / ``min_cols`` /
``min_rows`` → ``{found, table}``)與 ``AC_column_gutters``(``boxes`` / ``page_width`` /
``min_gap`` → ``{count, gutters}``)。兩者以 MCP 工具 ``ac_detect_borderless_table`` /
``ac_column_gutters``(唯讀)及 Script Builder 指令 **Detect Borderless Table** /
**Column Gutters (whitespace)**(位於 **OCR** 分類下)形式提供。
