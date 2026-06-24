表頭 + 儲存格定址(UIA TablePattern)
====================================

``read_control_table``(GridPattern)輸出的是一份扁平的 2D 儲存格名稱清單,**沒有表頭標籤,也無法
以(表頭, 列)定址單一儲存格**——所以你能*傾印*一個格線,卻無法真正*測試*它。``table_pattern``
補上所缺的另一半:

* :func:`table_headers` ——列 / 欄的表頭標籤(TablePattern),
* :func:`table_cell` ——位於 ``(row, column)`` 的儲存格及其跨距
  (GridPattern.GetItem + GridItemPattern),
* :func:`cell_by_header` ——讀取位於 ``(row, "欄表頭")`` 的儲存格,於是你可以斷言「第 5 列的
  Status 欄是 Shipped」,而不必猜索引。

每個都是對可注入的 ``accessibility.backends.get_backend()`` 接縫的薄分派——可透過注入 fake backend
進行無頭測試;真正的 UIA 呼叫位於 Windows 後端。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import table_headers, table_cell, cell_by_header

    table_headers(name="Orders")
    # {"columns": ["Order", "Status", "Total"], "rows": [...]}

    table_cell(0, 1, name="Orders")
    # {"value": "Shipped", "row": 0, "column": 1, "row_span": 1, "column_span": 1}

    cell_by_header(0, "Status", name="Orders")          # "Shipped"

表格以 ``name`` / ``role`` / ``app_name`` / ``automation_id`` 定位(與 ``read_control_table``
相同)。``table_headers`` 回傳 ``{columns, rows}``(或 ``None``);``table_cell`` 回傳儲存格記錄
(或 ``None``);``cell_by_header`` 由表頭解析欄索引並回傳儲存格值(找不到表頭或儲存格則為
``None``)。

執行器指令
----------

``AC_table_headers``(``{found, headers}``)、``AC_table_cell``(``row`` / ``column`` →
``{found, cell}``)與 ``AC_cell_by_header``(``row`` / ``column_header`` → ``{found, value}``)。
皆以唯讀 ``ac_*`` MCP 工具及 Script Builder 指令(位於 **Native UI** 分類下)形式提供。
