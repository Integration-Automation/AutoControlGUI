Unicode 文字正規化與 Slug
========================

``fuzzy`` 與 ``search_index.tokenize`` 只做小寫化,OCR ``find_text_matches`` 只做 ``.lower()`` + 子字串
比對 —— 因此 ``"Café"``(NFC)、``"Café"``(NFD)與 OCR 的 ``"cafe"`` 會比對不相等。本功能補上它們在比對
前應執行的正規化層。

純標準函式庫(``unicodedata`` / ``re``);不匯入 ``PySide6``。每個函式皆為純函式(輸入文字、輸出文字),
因此在 CI 中完全具決定性。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        normalize_text, deaccent, slugify, normalize_quotes, fold_whitespace,
    )

    normalize_text("CAFÉ  Menu")          # "café menu"(NFKC + casefold + 空白)
    deaccent("résumé")                     # "resume"
    slugify("Café Menu! 2026")             # "cafe-menu-2026"
    normalize_quotes("“Hi” — it’s…")       # '"Hi" - it\'s...'

``normalize_text`` 套用 Unicode ``form``(預設 ``NFKC``)、選用 casefold 與空白折疊,讓不同碼點形式的相同
文字比對相等。``deaccent`` 去除組合附加符號;``fold_whitespace`` 把連續空白收成單一空格;``normalize_quotes``
把智慧引號、破折號、省略號與 NBSP 對應成 ASCII;``slugify`` 產生 ASCII slug(去重音、小寫、以分隔符連接
英數段)。在 fuzzy/search/OCR 比對前先執行 ``normalize_text`` 可讓比對對重音與形式不敏感。

執行器命令
----------

``AC_normalize_text`` 回傳 ``{text}``(可選 ``form`` / ``casefold`` / ``collapse_ws``);``AC_slugify`` 回傳
``{slug}``。兩者皆以 MCP 工具(``ac_normalize_text`` / ``ac_slugify``)以及 Script Builder 中 **Data** 分類下
的命令提供。
