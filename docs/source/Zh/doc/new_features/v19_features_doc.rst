========================================
新功能 (2026-06-19) — 資料品質
========================================

來自資料/驗證研究角度的三項純標準庫資料品質輔助工具——介於資料匯入
(``load_rows`` / OCR)與下游輸入之間的品質閘。走完整五層(facade、
``AC_*`` 執行器指令、MCP 工具、Script Builder)。

.. contents::
   :local:
   :depth: 2


資料列 schema 驗證
==================

在抓取/載入的資料列進入 ERP 或表單前,依宣告式 schema 驗證——在此攔下的
壞資料就不會汙染下游::

    from je_auto_control import validate_rows

    report = validate_rows(rows, {
        "name": {"type": "str", "required": True},
        "age": {"type": "int", "min": 0, "max": 130},
        "email": {"regex": r".+@.+\..+"},
        "id": {"unique": True},
        "tier": {"allowed": ["gold", "silver"]},
    })
    report["ok"]          # 任何列失敗則為 False
    report["valid"]       # 通過的資料列
    report["errors"]      # [{"row": 1, "field": "age", "error": "above max 130"}]

規則:``type`` / ``required`` / ``regex`` / ``min`` / ``max`` /
``min_len`` / ``max_len`` / ``allowed`` / ``unique``。對應
``AC_validate_rows`` / ``ac_validate_rows``。


欄位擷取
========

用具名的 regex 預設(也可加自訂 ``patterns``)從自由文字 / OCR 文字塊中
擷取結構化值::

    from je_auto_control import extract_fields

    out = extract_fields("Mail ada@x.io on 2026-06-19",
                         fields=["email", "date_iso"])
    # {"email": ["ada@x.io"], "date_iso": ["2026-06-19"]}

預設:``email`` / ``url`` / ``ipv4`` / ``phone`` / ``date_iso`` /
``amount`` / ``hashtag``。對應 ``AC_extract_fields`` /
``ac_extract_fields``。


資料列遮罩
==========

在匯出資料列 / 報告前遮罩敏感欄位(既有的遮罩僅針對截圖)::

    from je_auto_control import mask_rows

    safe = mask_rows(rows, {"ssn": "partial", "token": "redact",
                            "name": "hash"})
    # ssn -> "*****6789"、token -> "***"、name -> sha256 hex

模式:``redact``(``***``)、``hash``(SHA-256 hex)、``partial``(保留末 4
字)。對應 ``AC_mask_rows`` / ``ac_mask_rows``。
