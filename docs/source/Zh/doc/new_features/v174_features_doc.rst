OCR 行的段落與清單分組
======================

``text_regions.find_text_lines`` 把字形併成行,但沒有任何功能把那些*行*分組成段落或偵測
清單——``ocr/structure`` 止於平面列。``text_blocks`` 補上這點:``group_paragraphs`` 在垂直
間距超過中位行高的某倍數處把行切成段落(標準的留白分組啟發法),而 ``detect_lists`` 以前導
標記與左縮排辨識項目符號 / 編號項目。

純標準函式庫,作用於純行字典(text + bbox);可在無影像、無 OCR 引擎下完整單元測試。重用
``table_grid_fill`` 的框邊界讀取器。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import group_paragraphs, detect_lists

    for para in group_paragraphs(ocr_lines, line_gap_factor=1.6):
        print(para["n_lines"], para["text"])

    for item in detect_lists(ocr_lines):
        print(item["marker"], item["indent"], item["text"])

``group_paragraphs`` 回傳段落字典(``left`` / ``top`` / ``right`` / ``bottom`` / ``text`` /
``n_lines``)——當與前一行底部的間距超過 ``line_gap_factor`` 乘以中位行高時,開始新段落。
``detect_lists`` 回傳文字以項目符號(``•`` / ``-`` / ``*``)或序號(``1.`` / ``2)`` /
``a.``)開頭的行,每個為 ``{text, marker, indent, box}``(``indent`` 為左 x,供巢狀用)。

執行器指令
----------

``AC_group_paragraphs``(``lines`` / ``line_gap_factor`` → ``{count, paragraphs}``)與
``AC_detect_lists``(``lines`` → ``{count, items}``)。兩者以 MCP 工具 ``ac_group_paragraphs`` /
``ac_detect_lists``(唯讀)及 Script Builder 指令 **Group Paragraphs** / **Detect Lists**
(位於 **OCR** 分類下)形式提供。
