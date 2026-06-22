表格 / 格線儲存格定位
====================

``anchor_locator`` 處理成對的空間關係(目標在錨點*附近* / *下方*),但無法定位二維格線——表格中「第 3 列、
第 2 欄的儲存格」。給定各儲存格的邊界框(來自影像或 OCR 列舉,例如 ``locate_all_image`` / ``find_text_matches``),
本功能將其分群為列與欄,並回傳所求儲存格的中心。

分群與查詢皆為純函式(框進、格線 / 儲存格出),完全可單元測試;框的列舉仍由呼叫端負責,因此此處不需真實螢幕。
不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import cluster_grid, locate_cell

    boxes = [(10, 100, 20, 10), (110, 100, 20, 10), (210, 100, 20, 10),
             (10, 200, 20, 10), (110, 200, 20, 10), (210, 200, 20, 10)]

    locate_cell(boxes, row=1, col=2)
    # {'found': True, 'center': [220, 205], 'box': [210, 200, 20, 10],
    #  'row': 1, 'col': 2, 'rows': 2, 'cols': 3}

    cluster_grid(boxes)   # 列由上到下、儲存格由左到右

``cluster_grid`` 依中心 y 排序框,當間距超過 ``row_tolerance`` 時開始新的一列,並將每列的儲存格依中心 x 排序。
``locate_cell`` 回傳 0 起算 ``(row, col)`` 儲存格的中心(可直接點擊),索引超出範圍時回傳
``{found: False, reason}``。

執行器命令
----------

``AC_grid_cell`` 接受 ``boxes``(JSON ``[[x, y, w, h], ...]`` 清單,例如來自前一個 ``AC_locate_all_image`` 步驟)
以及 ``row`` / ``col`` / ``row_tolerance``,並回傳儲存格 dict。它以 MCP 工具 ``ac_grid_cell`` 以及 Script Builder
中 **Mouse** 分類下的命令提供。
