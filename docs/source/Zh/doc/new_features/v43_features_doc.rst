區域設定感知的數字、貨幣與日期解析
==================================

從在地化 UI 或 OCR 擷取的文字,鮮少能直接通過 Python 的 ``float()``:``"1.234,56"``
在 ``de_DE`` 是一千二百多,但對 ``float`` 卻是格式錯誤。這些輔助函式以 **Babel** 的
CLDR 資料解析這類字串(並可反向格式化值),讓流程能跨區域設定讀取並斷言數字、貨幣與日
期。

``babel`` 為**選用**相依(``pip install je_auto_control[locale]``),採延遲匯入,因此套
件在沒有它時仍可匯入;函式僅在未安裝 Babel 而被呼叫時才拋出明確錯誤。不匯入
``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        parse_decimal, parse_number, format_decimal, format_currency,
        format_date)

    parse_decimal("1.234,56", locale="de_DE")    # -> 1234.56
    parse_number("1,234", locale="en_US")        # -> 1234

    format_decimal(1234.5, locale="en_US")       # -> "1,234.5"
    format_currency(1234.5, "USD", locale="en_US")   # -> "$1,234.50"
    format_date("2026-06-20", locale="de_DE", fmt="short")   # -> "20.06.26"

``format_date`` 接受 ISO ``YYYY-MM-DD`` 字串或 ``date`` 物件,``fmt`` 可為 ``short`` /
``medium`` / ``long`` / ``full``。同一區域設定內解析 + 格式化可往返一致。

.. note::

   功能路徑需要 Babel;CI 以 ``importorskip`` 執行這些測試,因此在有安裝 Babel 處執
   行、否則跳過。wiring/facade 則一律驗證。

執行器指令
----------

================================ ===================================================
指令                             效果
================================ ===================================================
``AC_parse_decimal``             由區域設定小數字串得到 ``{value}`` float。
``AC_parse_number``              由區域設定整數字串得到 ``{value}`` int。
``AC_format_decimal``            依區域設定格式化數字的 ``{text}``。
``AC_format_currency``           依區域設定的貨幣(ISO 4217)``{text}``。
``AC_format_date``               依區域設定格式化 ISO 日期的 ``{text}``。
================================ ===================================================

相同操作亦提供為 MCP 工具(``ac_parse_decimal`` / ``ac_parse_number`` /
``ac_format_decimal`` / ``ac_format_currency`` / ``ac_format_date``),以及 Script
Builder 中 **Data** 分類下的指令。
