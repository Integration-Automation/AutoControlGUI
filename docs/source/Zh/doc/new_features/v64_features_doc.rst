全文搜尋(BM25)
===============

``fuzzy`` 做成對的字串相似度,``skill_library`` 做字母序的子字串比對,但兩者都無法依相關性對
*文件語料*排名 —— 罕見的獨特詞與隨處可見的詞權重相同。本功能補上以倒排索引、用 Okapi **BM25**
(或 TF-IDF)排名文件的搜尋,讓流程與 agent 不需資料庫即可搜尋日誌、爬取紀錄或知識片段。

純標準函式庫(``math`` + ``collections`` + ``re``);具決定性;不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import SearchIndex, search_documents

    corpus = {
        "d1": "the quick brown fox jumps over the lazy dog",
        "d2": "a quick brown dog runs fast",
        "d3": "the database stores quick query results",
    }

    index = SearchIndex.build(corpus)          # 或 SearchIndex(); index.add(id, text)
    for hit in index.search("quick dog", top_k=5):
        print(hit.doc_id, hit.score)

    # 一次性便利函式
    hits = search_documents(corpus, "database", mode="bm25")

``SearchIndex.add`` / ``remove`` 以增量方式維護索引;``build`` 索引一個 ``{doc_id: text}`` 對映
(或 ``(id, text)`` 配對)。``search`` 回傳排名後的 ``SearchHit(doc_id, score)`` 結果 —— 預設
為 BM25(``k1=1.5``、``b=0.75``),或 ``mode="tfidf"``。評分採標準 Okapi 公式,
``IDF = ln(1 + (N − df + 0.5) / (df + 0.5))``,因此罕見詞勝過常見詞、詞頻會飽和(``k1``)、長
文件被正規化下調(``b``)。可提供 ``stop_words`` 集合以濾除雜訊詞。結果具決定性(平手以
``doc_id`` 決定)。

執行器命令
----------

``AC_search_documents`` 接受 ``docs``(``{doc_id: text}`` 對映或 JSON 字串)、``query`` 與選用
的 ``top_k`` / ``mode``,回傳 ``{hits: [{doc_id, score}]}``。同一操作亦以 MCP 工具
``ac_search_documents`` 以及 Script Builder 中 **Data** 分類下的命令提供。
