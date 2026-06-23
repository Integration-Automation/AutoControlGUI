表單欄位關聯(多方向)+ 核取方塊狀態
======================================

``ocr/structure`` 只有在框文字以 ``:`` 結尾時才視為標籤,並只與*緊接的下一格*配對——無法
處理標籤在值*上方*、雙欄 key/value 版面、右對齊值,或任何非文字格的 widget,且完全沒有
核取方塊 / 單選鈕狀態的概念。``form_fields`` 將其一般化:把每個標籤與多個*方向*(右、下)中
最近的對齊值配對,把獨立的 widget(核取方塊、單選鈕、輸入框)配到最近的標籤,並由填充比例
讀取核取方塊的勾選狀態。

關聯部分為純標準函式庫,作用於純框字典(可完整單元測試、不需影像);只有 ``checkbox_state``
觸及像素,且隔離在共用的 ``visual_match`` 灰階載入器之後,讓測試可傳入合成陣列。重用
``table_grid_fill`` 的框邊界讀取器。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (associate_fields, match_labels_to_widgets,
                                 checkbox_state)

    fields = associate_fields(ocr_boxes, directions=("right", "below"))
    # [{"label": "Name", "value": "Ann", "direction": "right", "gap": 20, ...}]

    pairs = match_labels_to_widgets(label_boxes, checkbox_boxes)
    # [{"widget": {...}, "label": "Accept terms", "distance": 22}]

    state = checkbox_state(screenshot, checkbox_box)   # "checked" | "unchecked"

``associate_fields`` 把文字以 ``:`` 結尾的框視為標籤,並在指定方向中(``max_gap`` 內)配到
最近的值框,回傳 ``{label, value, direction, gap, label_box, value_box}``。
``match_labels_to_widgets`` 依中心距離把每個 widget 配到最近標籤。``checkbox_state`` 由框內
暗像素填充比例回傳 ``"checked"`` / ``"unchecked"``(image 可注入——路徑 / ndarray / PIL)。

執行器指令
----------

``AC_associate_fields``(``text_boxes`` / ``directions`` / ``max_gap`` → ``{count, fields}``)
與 ``AC_match_labels_to_widgets``(``labels`` / ``widgets`` → ``{count, pairs}``)。兩者以
MCP 工具 ``ac_associate_fields`` / ``ac_match_labels_to_widgets``(唯讀)及 Script Builder 指令
**Associate Form Fields** / **Match Labels To Widgets**(位於 **OCR** 分類下)形式提供。
