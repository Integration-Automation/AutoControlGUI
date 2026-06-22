融合並排序螢幕元素框
====================

``set_of_marks.mark_elements`` 為單一、已乾淨的元素清單編號——但沒有任何功能*產生*那份清單。真實的畫面解析會
產出三個彼此重疊的來源(OCR 文字框、圖示 / 形狀框、無障礙樹框),有大量重複且無一致順序。本模組是定位器
(``locate_text``、``find_shapes``、a11y 樹)與 ``set_of_marks`` 之間缺少的連接組織:依重疊去重、聯集各來源並
保留最可信的框、再排成閱讀順序並給予穩定索引。

每個框都是帶 ``x, y, width, height`` 的純 ``dict``(可附帶 ``text`` / ``source`` / ``score`` 等鍵),因此整個模組
皆為純標準函式庫且完全可單元測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import iou, merge_boxes, fuse_elements, reading_order

    iou(box_a, box_b)                          # 兩框的重疊度,0..1
    deduped = merge_boxes(raw_boxes, iou_threshold=0.9)

    # 聯集三個偵測器輸出;重疊時 a11y 框勝出,其次 OCR,再其次 icon。
    elements = fuse_elements(ocr_boxes=ocr, icon_boxes=icons, a11y_boxes=tree)

    # 由上到下、由左到右排序並為每個元素加上 "index"。
    for el in reading_order(elements):
        print(el["index"], el.get("text"), el["x"], el["y"])

``iou`` 回傳兩框的交集除以聯集。``merge_boxes`` 在任一群重疊超過 ``iou_threshold`` 時保留最大者。``fuse_elements``
為每個輸入標記 ``source``,再依 ``source_priority``(預設 ``a11y`` > ``ocr`` > ``icon``,其後較大面積)丟棄跨來源
重疊。``reading_order`` 將相距 ``row_tol`` 像素內的元素歸為同列、列內依 ``x`` 排序,並回傳帶有遞增 ``index`` 的新字典。

執行器命令
----------

``AC_fuse_elements``(``ocr`` / ``icon`` / ``a11y`` JSON 陣列 + ``iou_threshold`` → ``{count, elements}``)與
``AC_reading_order``(``elements`` + ``row_tol`` → ``{count, elements}``)。它們以 MCP 工具 ``ac_fuse_elements`` /
``ac_reading_order`` 以及 Script Builder 中 **Image** 分類下的命令提供。
