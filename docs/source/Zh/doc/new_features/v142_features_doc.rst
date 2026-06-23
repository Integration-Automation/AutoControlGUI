重試式數值斷言(expect.poll)
==============================

``assert_eventually`` 只能輪詢框架固定的字典規格分派表(文字 / 影像 / 像素 / 視窗 / 剪貼簿 / 行程 / 檔案 / http),
無法重試*任意*值——OCR 出的總額等於 ``"$42.00"``、列數穩定下來、或自訂判斷式。``expect_poll`` 接受任何零參數
``getter`` 與任何 ``matcher`` 判斷式,輪詢直到通過或逾時,並可注入 ``clock`` / ``sleep`` 讓測試具決定性(既有
輔助函式呼叫真實 ``time.sleep``)。它對應 Playwright 的 ``expect.poll`` / web-first 重試式斷言。

純標準函式庫,不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (expect_poll, assert_poll, to_equal, to_contain,
                                 to_be_greater_than, to_match_regex, to_be_stable)

    # 輪詢任意 getter 直到符合。
    result = expect_poll(lambda: read_cart_total(), to_equal("$42.00"),
                         timeout_s=8.0, interval_s=0.5)
    if result.ok:
        print("settled after", result.attempts, "tries")

    # 失敗時拋例外(斷言風格)。
    assert_poll(lambda: row_count(), to_be_greater_than(0))

    # 等待某值不再變動。
    expect_poll(lambda: ocr_value(), to_be_stable(3))

``expect_poll`` 回傳 ``PollResult``(``ok``、``value``、``attempts``、``waited_s``、``description``);
``assert_poll`` 在始終不符時丟出 ``AutoControlActionException``。matcher 工廠有 ``to_equal``、``to_contain``、
``to_be_greater_than``、``to_match_regex``、``to_be_truthy`` 與 ``to_be_stable(n)``(值重複 ``n`` 次後符合)。

執行器命令
----------

``AC_expect_poll`` 重複執行巢狀 ``action``(例如 ``["AC_get_clipboard"]``),直到其結果的 ``key`` 以 ``op``
(``truthy`` / ``equals`` / ``contains`` / ``gt`` / ``regex``)對 ``expected`` 符合,或 ``timeout_s`` 逾時——
回傳 ``{ok, value, attempts, waited_s}``。它以 MCP 工具 ``ac_expect_poll`` 以及 Script Builder 中 **Flow**
分類下的命令提供。
