以 OCR 文字填入框線網格(可定址表格)
======================================

``edge_lines.find_grid`` 能還原有框線表格的幾何——``{rows: [y…], cols: [x…], cells: […]}``
——但回傳的儲存格是*空的*(僅是框線之間的矩形)。OCR 提供文字卻無表格結構。兩者從未串接,
因此讀取有框線表格只能自行撰寫 box→cell 的指派。``table_grid_fill`` 把 OCR 文字框放入網格,
回傳可定址的 ``R x C`` 表格。

每個框依其中心落在哪個儲存格而被指派(以重疊比例把關,使橫跨細框線的框不被重複計入);
同一儲存格內的文字依閱讀順序串接;橫跨多個儲存格的框則回報為合併儲存格候選。結果可直接
轉成 records 或 CSV。

純標準函式庫幾何,作用於純字典(網格 + 框)——不需影像、不需 OCR 引擎、不需裝置。不匯入
``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (find_grid, find_text_lines,  # 產生來源
                                 populate_table, assign_text_to_grid,
                                 table_to_records, table_to_csv)

    grid = find_grid(region=[0, 0, 800, 400])      # 框線幾何
    boxes = [{"x": 10, "y": 5, "width": 60, "height": 20, "text": "Name"}, ...]

    table = assign_text_to_grid(grid, boxes)        # [["Name","Age"], ["Ann","30"]]
    records = table_to_records(table)               # [{"Name": "Ann", "Age": "30"}]
    csv_text = table_to_csv(table)

    full = populate_table(grid, boxes)              # {n_rows, n_cols, cells, spans}

``assign_text_to_grid`` 回傳二維文字表格;``populate_table`` 回傳更豐富的
``{n_rows, n_cols, cells:[{row, col, text}], spans:[{row, col, row_span, col_span, text}]}``。
``table_to_records`` 以第一列為標頭;``table_to_csv`` 輸出 CSV。框接受 ``{x, y, width, height}``
或 ``{left, top, right, bottom}`` 加上 ``text`` 欄位。

執行器指令
----------

``AC_populate_table``(``grid`` / ``text_boxes`` / ``overlap`` → ``{n_rows, n_cols, cells,
spans}``)以 MCP 工具 ``ac_populate_table``(唯讀)及 Script Builder 指令
**Fill Table From Grid + OCR**(位於 **OCR** 分類下)形式提供。
