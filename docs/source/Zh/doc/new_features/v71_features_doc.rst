混沌實驗(Chaos Experiments)
============================

``resilience`` 從失敗中*復原*(retry、circuit breaker);這是相反的一面 —— 它*製造*受控的失敗,
並檢查穩態假設是否仍成立。仿照 Chaos Toolkit 生命週期:**之前**驗證穩態、執行**方法**(故障活動)、
**之後**再驗證穩態,然後永遠執行**回滾**(LIFO)。它回傳一份 journal。

探針、故障與回滾皆為呼叫端提供的 callable,且時鐘 / RNG / sleep 可注入,因此實驗在測試中以假物件
具決定性地執行 —— 沒有真正的失敗、沒有真正的睡眠。純標準函式庫(``random`` + ``time``);不匯入
``PySide6``。

無頭 API
--------

.. code-block:: python

    from je_auto_control import (
        ChaosExperiment, Probe, run_experiment, latency_fault)

    experiment = ChaosExperiment(
        title="checkout survives slow payments",
        probes=[Probe("service_up", check_health, tolerance=True),
                Probe("p95_latency", measure_p95, tolerance=[0, 500])],
        method=[latency_fault("payment_delay", delay_s=2.0, rate=0.5)],
        rollbacks=[restore_network])

    journal = run_experiment(experiment)
    if journal["deviated"]:
        print("假設在故障下被打破:", journal["status"])

``Probe`` 回傳一個值,並以其 ``tolerance``(字面值、``[low, high]`` 範圍,或述詞 callable)檢查。
``run_experiment`` 先驗證假設 —— 若失敗,狀態為 ``failed-before-method`` 且方法不會執行 —— 接著
套用每個故障、再次驗證(若不再成立則設定 ``deviated`` 與狀態 ``deviated``),並在 ``finally`` 中
永遠以 LIFO 執行回滾。探針/故障/回滾的錯誤會被捕捉並記錄在 journal,而非讓執行崩潰。
``latency_fault`` 與 ``exception_fault`` 是現成的故障工廠,具可注入的 RNG(rate)與 sleep。

執行器命令
----------

``AC_run_chaos`` 接受一份 ``spec``(物件或 JSON 字串),其探針、方法與回滾皆為**動作清單** ——
``{title, probes:[{name, action:[AC...]}], method:[{name, action:[AC...]}], rollbacks:[[AC...]]}``
—— 並回傳 journal。當探針的動作執行而無錯誤時,其穩態即成立。同一操作亦以 MCP 工具
``ac_run_chaos`` 以及 Script Builder 中 **Flow** 分類下的命令提供。
