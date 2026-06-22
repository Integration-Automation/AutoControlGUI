錨點序數與全部定位
==================

``anchor_locate`` 依與錨點的空間關係尋找目標,但總是回傳單一*最近*的比對——先前無法選「標題下方的**第 2** 列」
或列舉每一個符合的列。本功能加入 ``ordinal`` 選擇器與回傳清單的 :func:`anchor_locate_all`。

兩者皆建立在共用的排序輔助函式上(純函式:依關係過濾、依距離排序),因此選擇邏輯可藉由注入候選框做單元測試。
無頭且不依賴 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        anchor_locate, anchor_locate_all, ocr_locator, image_locator,
    )

    header = ocr_locator("Name")
    row = image_locator("row_handle.png")

    anchor_locate(anchor=header, target=row, relation="below")             # 最近
    anchor_locate(anchor=header, target=row, relation="below", ordinal=2)  # 第 2 列
    rows = anchor_locate_all(anchor=header, target=row, relation="below")  # 所有列

``ordinal`` 為 1 起算(``ordinal=1`` 即最近,與先前行為相同,故向後相容);超出範圍的序數回傳未找到的結果。
``anchor_locate_all`` 回傳依距離排序的 found ``AnchorOutcome`` 清單——表格 / 清單列選取的基礎元件。

執行器命令
----------

``AC_anchor_locate`` 新增 ``ordinal`` 參數;``AC_anchor_locate_all`` 回傳 ``{count, matches}``。兩者皆以 MCP
工具(``ac_anchor_locate`` 含 ``ordinal`` / ``ac_anchor_locate_all``)提供。
