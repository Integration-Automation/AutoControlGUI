軟性斷言——區塊結束時彙整所有失敗
====================================

``assertion.assert_all`` 接受**事先建好的規格字典清單**。沒有一個可以在交錯動作之間隨處呼叫 ``check()``、並在退出時
一次拋出全部的*作用域累加器*——也就是 JUnit5 ``assertAll`` / Playwright ``expect.soft`` / AssertJ ``SoftAssertions``
模式,是驗證表單眾多欄位而不在第一個失敗就停下的標準寫法。

純標準函式庫的 context manager;不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import SoftAssertions

    with SoftAssertions() as soft:
        soft.check(title == "Invoice", "wrong title")
        soft.check_equal(total, "$42.00", "wrong total")
        soft.check(date_field_is_visible(), "date field missing")
    # 退出時一次拋出列出每一個失敗的檢查(全部通過則不拋)

``check(condition, message)`` 記錄通過/失敗且永不拋出(回傳布林值,可據以分支);``check_equal(actual, expected,
message)`` 是相等捷徑。``failures`` 列出失敗訊息、``passed`` 計算通過數、``assert_all()`` 彙整後丟出
``AutoControlActionException``。context manager 在乾淨退出時呼叫 ``assert_all``(且永不遮蔽已在傳播的例外)。
傳入 ``raise_on_exit=False`` 可只收集不自動拋出。

執行器命令
----------

``AC_soft_assert`` 評估一串 ``checks``(每個為 ``{value, op, expected, message}``,``op`` =
``eq`` / ``ne`` / ``gt`` / ``lt`` / ``contains`` / ``truthy``)並回傳 ``{ok, passed, failures}``——回報*所有*失敗,
不只第一個;設 ``raise_on_fail`` 則改為拋出。它以 MCP 工具 ``ac_soft_assert`` 以及 Script Builder 中 **Flow**
分類下的命令提供。
