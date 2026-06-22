地區感知字串排序(Collation)
============================

``text_normalize`` 正規化文字、``locale_parse`` 格式化數字,但沒有任何功能能依某語言讀者的期望排序字串。
Python 預設的 ``sorted`` 是碼位順序,因此 ``"Z" < "a"``,而 ``"ä"`` 會離 ``"a"`` 很遠。真正的排序會先依
*基底字母*、再依*變音符號*、再依*大小寫*,並讓地區得以調整字母表(瑞典文將 ``å ä ö`` 排在 ``z`` 之後)。

本功能建立一個 Unicode-Collation-lite 排序鍵,含三個層級——主層(基底字母)、次層(變音符號)、三層(大小寫)
——以及選用的字母表 ``tailoring``。純標準函式庫(``unicodedata``);不匯入 ``PySide6``。每個函式皆為純函式,
因此跨平台完全具決定性(不像 ``locale.strxfrm`` 取決於主機已安裝的地區設定)。

無頭 API
--------

.. code-block:: python

    from je_auto_control import sort_strings, collation_compare, collation_key

    sort_strings(["résumé", "rest", "resume"])
    # ['rest', 'resume', 'résumé']   (變音符號為次層差異)

    swedish = "abcdefghijklmnopqrstuvwxyzåäö"
    sort_strings(["zebra", "äpple", "apple"], tailoring=swedish)
    # ['apple', 'zebra', 'äpple']    (å ä ö 排在 z 之後)

    collation_compare("apple", "Apple")        # -1  (小寫在大寫之前)
    sort_strings(rows, key=lambda r: r["name"])  # 依欄位排序字典

``strength``(``primary`` / ``secondary`` / ``tertiary``)限制比較的層級,因此 ``strength="primary"`` 為
不分變音符號與大小寫。``tailoring`` 是有序字母表,所列字元依給定順序排序,且排在任何未列字元之前;像 ``"å"``
這類預組字元會保有其字母表排名,而非分解為 ``a`` + 分音符。``collation_key`` 回傳可比較的原始 tuple,供作
``sorted`` 的 key 使用。

執行器命令
----------

``AC_collation_sort`` 接受 JSON 列表並回傳 ``{sorted}``;``AC_collation_compare`` 回傳 ``{order: -1|0|1}``。
兩者皆接受 ``strength`` 與 ``tailoring``,並以 MCP 工具(``ac_collation_sort`` / ``ac_collation_compare``)
以及 Script Builder 中 **Data** 分類下的命令提供。
