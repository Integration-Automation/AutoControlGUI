文字 Diff、套用與三方合併
========================

``difflib`` 會*產生* unified diff,但標準函式庫無法*套用*它,而且各處都沒有三方合併 —— 因此更新
``.received`` 產物、重播錄製的文字編輯,或合併對同一基底檔案的兩份編輯,都缺少無頭原語。本功能補上
缺少的部分,與 ``utils/json_patch``(結構化 JSON)互補;這裡處理以行為單位的文字。

純標準函式庫(``difflib`` + ``re``);不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import unified_diff, apply_unified, three_way_merge

    diff = unified_diff(original, edited)
    restored = apply_unified(original, diff)        # == edited

    merge = three_way_merge(base, ours, theirs)
    if merge.clean:
        save(merge.text)
    else:
        print(merge.conflicts, "個衝突")             # text 含 <<<<<<< 標記

``unified_diff`` 包裝 ``difflib``;``apply_unified`` 是缺少的套用器 —— 它逐一走訪每個 ``@@``
區塊,驗證 context/移除行是否相符,不符時拋出 ``PatchApplyError``。``three_way_merge`` 以行為單位
合併:兩側不重疊的編輯會乾淨合併;若兩側編輯同一區域(且不同),則產生帶有
``<<<<<<< / ======= / >>>>>>>`` 標記的衝突區塊並回報 ``clean=False``。瑣碎情況(一側未變動,或兩側
相同編輯)會自動解決。

執行器命令
----------

``AC_unified_diff``(``{diff}``)、``AC_apply_unified``(``{result}``)與
``AC_three_way_merge``(``{text, clean, conflicts}``)。每個亦以 MCP 工具(``ac_unified_diff`` /
``ac_apply_unified`` / ``ac_three_way_merge``)以及 Script Builder 中 **Data** 分類下的命令提供。
