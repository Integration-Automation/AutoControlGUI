近似重複文字偵測(SimHash / MinHash)
====================================

``fuzzy.fuzzy_dedupe`` 是 O(n²) 的成對 ``SequenceMatcher``,沒有穩定指紋,而 ``image_dedup`` 只雜湊
像素。本功能加入文字指紋 —— SimHash(以 Hamming 距離找近似重複)與 MinHash(估計 Jaccard)—— 可擴展且
提供可重用的簽章,是感知式影像雜湊的文字對應。

純標準函式庫(``hashlib`` / ``re``);不匯入 ``PySide6``。使用固定雜湊(``blake2b``,而非加鹽的內建
``hash()``)讓指紋在不同執行與 CI 間具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        simhash, near_duplicates, minhash_signature, minhash_similarity,
    )

    h1 = simhash("the quick brown fox jumps over the lazy dog")
    h2 = simhash("the quick brown fox jumps over the lazy dogs")
    # Hamming 距離小 ⇒ 近似重複

    clusters = near_duplicates(docs, max_distance=12)   # 索引分群

    sig_a = minhash_signature(text_a)
    minhash_similarity(sig_a, minhash_signature(text_b))  # ~ Jaccard

``simhash`` 從詞 shingle 產生 ``bits`` 寬的指紋;``hamming_distance``(與 ``image_dedup`` 共用)量測位元
差異。``near_duplicates`` 把 SimHash 在 ``max_distance`` 位元內的文字分群,回傳索引的分割(含單例)。
``minhash_signature`` / ``minhash_similarity`` 提供 MinHash 簽章與 Jaccard 估計以做集合重疊式去重。可先執行
``normalize_text`` 取得對重音/形式不敏感的指紋。

執行器命令
----------

``AC_simhash`` 對 ``text`` 回傳 ``{simhash}``;``AC_near_duplicates`` 對 ``texts`` 在 ``max_distance`` 內
回傳 ``{clusters}``。兩者皆以 MCP 工具(``ac_simhash`` / ``ac_near_duplicates``)以及 Script Builder 中
**Data** 分類下的命令提供。
