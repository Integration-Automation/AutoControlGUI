標題與內文分類 + 文件大綱
==========================

框架中沒有任何功能把行高對應到標題層級或建立章節大綱——``ocr/structure`` 與 ``element_parse``
純屬位置性,``text_blocks`` 把段落 / 清單分組但不對其排序。``heading_segment`` 補上標準啟發法:
行高超過 ``heading_ratio`` 乘以中位行高者為標題,且不同的標題高度成為標題*層級*(最高為第 1 級)。
由此輸出扁平的文件大綱。

純標準函式庫,作用於純行字典(text + bbox);可在無影像、無 OCR 引擎下完整單元測試。重用
``table_grid_fill`` 的框邊界讀取器。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import classify_lines, outline

    for item in classify_lines(ocr_lines, heading_ratio=1.2):
        print(item["role"], item["level"], item["text"])

    for heading in outline(ocr_lines):
        print("  " * (heading["level"] - 1) + heading["text"])

``classify_lines`` 為每行標記 ``{box, text, role, level}``——``role`` 為 ``"heading"`` 或
``"body"``,``level`` 為標題層級(1 = 最高,內文為 0)。``outline`` 只回傳依上到下順序的標題,
為 ``{level, text, top}``——即文件目錄。

執行器指令
----------

``AC_classify_lines``(``lines`` / ``heading_ratio`` → ``{count, lines}``)與 ``AC_outline``
(``lines`` / ``heading_ratio`` → ``{count, headings}``)。兩者以 MCP 工具 ``ac_classify_lines`` /
``ac_outline``(唯讀)及 Script Builder 指令 **Classify Headings vs Body** / **Document Outline**
(位於 **OCR** 分類下)形式提供。
