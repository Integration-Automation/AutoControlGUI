====================================
新功能 (2026-06-19) — Office 讀寫
====================================

Office 文件的 headless 讀寫——Excel(``.xlsx``)、Word(``.docx``)、
PowerPoint(``.pptx``)——讓流程不必驅動 GUI 就能吃進資料列或產出報表。
走完整五層(facade、``AC_*`` 執行器指令、MCP 工具、Script Builder)。

背後的函式庫(``openpyxl`` / ``python-docx`` / ``python-pptx``)是
**可選**相依::

    pip install je_auto_control[office]

缺少對應函式庫時,每個函式都會丟出清楚的 ``RuntimeError``,因此核心
套件維持精簡,``import je_auto_control`` 不會載入任何一個。

.. contents::
   :local:
   :depth: 2


Excel
=====

::

    from je_auto_control import read_workbook, write_workbook

    write_workbook("people.xlsx", [{"name": "Ada", "age": 36}], sheet="P")
    rows = read_workbook("people.xlsx", sheet="P")   # [{'name': 'Ada', ...}]

第一列作為 dict 的鍵;``sheet`` 預設為作用中工作表。指令:
``AC_read_workbook`` / ``AC_write_workbook``(以及 ``ac_read_workbook`` /
``ac_write_workbook``)。


Word
====

::

    from je_auto_control import read_document, write_document

    write_document("report.docx", ["標題", "第一行", "第二行"])
    paragraphs = read_document("report.docx")["paragraphs"]

指令:``AC_read_document`` / ``AC_write_document``。


PowerPoint
==========

::

    from je_auto_control import read_presentation, write_presentation

    write_presentation("deck.pptx", [
        {"title": "簡介", "body": ["重點一", "重點二"]},
    ])
    slides = read_presentation("deck.pptx")["slides"]   # 每張投影片的文字

每張投影片規格為 ``{title, body:[...]}``,採用「標題及內容」版面。指令:
``AC_read_presentation`` / ``AC_write_presentation``。
