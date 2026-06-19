模糊字串比對與去重
==================

當文字來自 OCR 或時常變動的 UI 文案時,精確字串比對很脆弱。這些輔助函式為相似度評分、
從清單中挑出最佳候選,並收合近似重複項 —— 讓流程可以針對「*看起來像* Submit 的按鈕」
動作,而非精確標籤。

預設後端為標準函式庫 :mod:`difflib`,因此本功能**無需任何額外相依**即可運作。若安裝了
選用的 ``rapidfuzz`` 套件(``pip install je_auto_control[fuzzy]``)則改用其以加速;無論
何者,分數皆正規化為 ``0.0..1.0``,故呼叫端永不依賴實際執行的後端。``BACKEND`` 標示目
前作用中的後端。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        fuzzy_ratio, fuzzy_best_match, fuzzy_matches, fuzzy_dedupe)

    fuzzy_ratio("Sumbit", "Submit")          # ~0.83(預設不分大小寫)

    fuzzy_best_match("Sve", ["Cancel", "Save", "Submit"])
    # -> ("Save", 0.86, 1)   (choice, score, index) —— 低於 score_cutoff 則為 None

    fuzzy_matches("login", ["login", "logon", "logout"], limit=2)
    # -> [("login", 1.0, 0), ("logon", 0.8, 1)]  由高分至低分排序

    fuzzy_dedupe(["Invoice", "invoice ", "Receipt"], threshold=0.85)
    # -> ["Invoice", "Receipt"]   近似重複收合,保留第一個

所有函式皆接受 ``ignore_case``(預設 ``True``);``fuzzy_best_match`` /
``fuzzy_matches`` 接受 ``score_cutoff`` 以濾除弱候選。

執行器指令
----------

================================ ===================================================
指令                             效果
================================ ===================================================
``AC_fuzzy_ratio``               兩字串相似度的 ``{score}``。
``AC_fuzzy_best_match``          從候選中取 ``{match, score, index}``(或 null)。
``AC_fuzzy_dedupe``              收合近似重複後的 ``{unique}``。
================================ ===================================================

``choices`` / ``items`` 接受清單或 JSON 字串清單(因此視覺化建構器可用)。相同操作亦提供
為 MCP 工具(``ac_fuzzy_ratio`` / ``ac_fuzzy_best_match`` / ``ac_fuzzy_dedupe``),以及
Script Builder 中 **Data** 分類下的指令。
