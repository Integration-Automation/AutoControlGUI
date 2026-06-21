字串距離相似度量
==============

``fuzzy`` 只提供 difflib 的 gestalt ratio。本功能補上它缺少的編輯距離與 token 集合度量 ——
Levenshtein / Damerau-Levenshtein、Jaro 與 Jaro-Winkler(短名稱/標籤的標準),以及字元 n-gram 的
Jaccard / Dice —— 更適合比對打字錯誤與重排 token,尤其來自 OCR。

純標準函式庫;不匯入 ``PySide6``。每個函式皆為純函式(輸入兩個字串、輸出數字),因此在 CI 中完全
具決定性。可先搭配 ``normalize_text`` 讓比對對重音與形式不敏感。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        levenshtein, damerau_levenshtein, jaro_winkler, jaccard, dice,
        similarity, normalize_text,
    )

    levenshtein("kitten", "sitting")            # 3
    damerau_levenshtein("ab", "ba")             # 1(轉置)
    jaro_winkler("MARTHA", "MARHTA")            # ~0.961
    jaccard("night", "nacht", n=2)              # 字元 bigram 重疊

    # 任一度量的正規化 [0, 1] 分數(編輯距離 → 1 - d/max_len):
    similarity(normalize_text(a), normalize_text(b), metric="jaro_winkler")

``levenshtein`` / ``damerau_levenshtein`` 回傳整數編輯距離(後者把相鄰轉置算作一次編輯)。``jaro`` /
``jaro_winkler`` 與 ``jaccard`` / ``dice`` 回傳 ``[0, 1]`` 相似度。``similarity`` 是統一入口 —— 直接回傳
Jaro/Jaccard/Dice,並把編輯距離轉成 ``1 - distance / max_len``,讓所有度量在同一尺度上可比較。

執行器命令
----------

``AC_text_similarity`` 對兩個字串 ``a`` / ``b`` 與選用的 ``metric`` 回傳 ``{score}``。它以 MCP 工具
``ac_text_similarity`` 以及 Script Builder 中 **Data** 分類下的命令提供。
