重試預算——截止時間 + 抖動
==========================

:class:`resilience.RetryPolicy` 以固定次數搭配單純指數退避重試。有兩件它無法表達的事,正是不穩定、
高競爭的 UI 自動化所需:

* **掛鐘截止時間**——「持續重試,但總共超過 30 秒就放棄」,與嘗試了幾次無關;以及
* **抖動(jitter)**——隨機化退避,讓眾多重試中的工作者不會重新同步成驚群效應。

``retry_budget`` 兩者皆補上。:class:`RetryBudget` 由 ``max_attempts`` *與 / 或* ``deadline_s``
界定;:func:`run_with_budget` 以先達到者為準,且絕不會睡過截止時間。延遲採用有上限的指數退避,
搭配可選的抖動策略(``full`` / ``equal`` / ``none``)。隨機來源(``uniform``)、時鐘與睡眠器
皆可注入,故每個延遲與決策在測試中都是確定的。不匯入 ``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import RetryBudget, run_with_budget

    budget = RetryBudget(max_attempts=8, deadline_s=30.0,
                         base_delay_s=0.2, max_delay_s=5.0)

    # 重試點擊直到成功,上限為 8 次嘗試 或 總共 30 秒
    run_with_budget(lambda: click_and_verify("Save"), budget)

``RetryBudget`` 由嘗試次數與 / 或截止時間界定——把其一設為 ``None`` 即只以另一者界定。
:func:`backoff_delay`(純函式,無抖動)與 :meth:`RetryBudget.plan` 提供延遲排程以供檢視:

.. code-block:: python

    RetryBudget(jitter="none").plan(4)   # [0.1, 0.2, 0.4, 0.8]

確定性測試可注入 ``uniform`` / ``clock`` / ``sleep``:

.. code-block:: python

    run_with_budget(flaky, budget, clock=fake_clock, sleep=fake_sleep,
                    uniform=lambda lo, hi: lo)   # 永遠取下界

執行器指令
----------

``AC_retry_delay``(``attempt`` / ``base`` / ``max_delay`` / ``multiplier`` /
``jitter`` → ``{delay}``)與 ``AC_plan_retry_delays``(``attempts`` … →
``{delays}``)暴露純退避排程(``jitter`` 預設為 ``none`` 以得確定結果)。皆以對應的唯讀
``ac_*`` MCP 工具及 Script Builder 指令(位於 **Flow** 分類下)形式提供。
:func:`run_with_budget`(包裹一個 callable)則是 Python API 介面。
