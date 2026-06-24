穩定的失敗簽章
==============

兩次以*相同方式*失敗的執行,幾乎不會有逐位元組相同的錯誤文字——路徑、行號、記憶體位址、id 與
時間戳每次都不同。這使得「這和昨天是同一個失敗嗎?」或「哪些測試會*一起*失敗?」無從問起。
``failure_signature`` 把錯誤的變動部分剝離成標準形式並雜湊(SHA-256),於是*相同類型*的失敗在
不同執行間會得到相同的短簽章——即其餘 test-robustness 工具(執行比較、flaky 分群)所依據的
join key。

* :func:`normalize_error` ——把路徑 / 十六進位位址 / UUID / 時間戳 / 行號 / 裸整數收斂成佔位符,
* :func:`failure_signature` ——正規化訊息的短而穩定的 SHA-256,
* :func:`group_failures` ——把一組錯誤依簽章分組,最常見者在前。

純標準庫(``re`` + ``hashlib``);不涉及裝置,不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (normalize_error, failure_signature,
                                 group_failures)

    a = r"Timeout at C:\app\run.py line 42 (0x7ffab12c) at 2026-06-24 11:03:21"
    b = r"Timeout at C:\app\run.py line 88 (0x1234abcd) at 2026-06-25 09:15:00"
    normalize_error(a)          # "Timeout at <path> line <n> (0x<addr>) at <ts>"
    failure_signature(a) == failure_signature(b)        # True——同一個失敗

    group_failures([a, b, "Connection refused to /tmp/x.sock"])
    # [{"signature": "...", "normalized": "...", "count": 2, "examples": [...]},
    #  {"signature": "...", "count": 1, ...}]

Windows 與 POSIX 路徑、``0x`` 位址、UUID、ISO 時間戳、``line N`` 與任何殘留整數都會變成佔位符;
空白會被壓縮。``group_failures`` 每組最多保留三個不同的原始範例,並略過空 / ``None`` 訊息。

執行器指令
----------

``AC_failure_signature``(``error`` / ``length``)回傳 ``{signature, normalized}``;
``AC_group_failures``(``errors``)回傳分組清單。皆以唯讀 ``ac_*`` MCP 工具及 Script Builder
指令(位於 **Testing** 分類下)形式提供。
