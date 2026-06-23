幾何感知的元素差異與穩定 ID
============================

``screen_state.diff_snapshots`` 嚴格以 ``(role, name)`` 作為元素識別——因此無法比對標籤變了但位置穩定的元素、無法
追蹤改名的控制項,也無法跨影格產生持久 ID。幾何感知比對(交集除以聯集,沿用 :doc:`v138_features_doc` 的 ``iou``)
是 agent 能跨回合引用穩定元素 ID 的基礎:移動幾像素的按鈕保留其 id、改名但未移動的控制項以重疊比對到、真正
新增的元素取得新 id。

純標準函式庫,作用於純元素字典(``x`` / ``y`` / ``width`` / ``height``),因此完全可單元測試。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import match_elements, assign_stable_ids

    diff = match_elements(before_boxes, after_boxes, iou_threshold=0.5)
    for pair in diff["matched"]:
        print("moved/kept:", pair["before"], "->", pair["after"], pair["iou"])
    print("appeared:", diff["added"], "disappeared:", diff["removed"])

    # 跨影格延續穩定 ID,讓 agent 能可靠地說「click element 7」。
    frame1 = assign_stable_ids(boxes1)
    frame2 = assign_stable_ids(boxes2, prior=frame1)

``match_elements`` 以重疊貪婪配對 ``before`` ↔ ``after``,回傳 ``{matched: [{before, after, iou}], added, removed}``。
``assign_stable_ids`` 為每個元素標上 ``id``;給定 ``prior`` 影格時,每個元素繼承其最重疊(超過 ``iou_threshold``)
之 prior 框的 id,未配對者取得超過最大 prior id 的新 id。

執行器命令
----------

``AC_match_elements``(``before`` / ``after`` / ``iou_threshold`` → ``{matched, added, removed}``)與
``AC_assign_stable_ids``(``elements`` / ``prior`` / ``iou_threshold`` → ``{count, elements}``)。它們以 MCP 工具
``ac_match_elements`` / ``ac_assign_stable_ids`` 以及 Script Builder 中 **Native UI** 分類下的命令提供。
