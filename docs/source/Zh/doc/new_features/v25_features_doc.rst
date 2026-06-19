==========================================
新功能 (2026-06-19) — 韌性原語
==========================================

可重用的韌性原語——retry-with-backoff 策略與斷路器(circuit breaker)
——並提供一個執行器指令,讓動作清單透過具名斷路器執行。純標準庫;兩個
原語都接受可注入的 ``sleep`` / ``clock``,因此能做決定性單元測試。

(既有的 ``AC_retry`` 流程指令已能對動作 *body* 重試;本功能新增可重用的
:class:`RetryPolicy` 可呼叫包裝器與全新的 :class:`CircuitBreaker`。)

.. contents::
   :local:
   :depth: 2


RetryPolicy
===========

::

    from je_auto_control import RetryPolicy, retry_call

    RetryPolicy(max_attempts=5, backoff=0.1, multiplier=2.0).run(flaky_fn)
    retry_call(flaky_fn, max_attempts=3)     # 便利函式

在設定的 ``exceptions`` 上以指數退避重試 ``func``(``backoff *
multiplier**n``,可用 ``max_backoff`` 上限夾限),嘗試耗盡後重新拋出最後
一個錯誤。


CircuitBreaker
==============

::

    from je_auto_control import CircuitBreaker, CircuitOpenError

    breaker = CircuitBreaker(failure_threshold=5, reset_timeout=30.0)
    try:
        breaker.call(call_remote_service)
    except CircuitOpenError:
        ...   # 已短路——依賴掛了

連續失敗達 ``failure_threshold`` 次後開啟並短路(拋出
:class:`CircuitOpenError`),直到 ``reset_timeout`` 過去後半開試一次;成功
即關閉。可避免重試風暴持續打掛已故障的依賴。

``AC_circuit_call`` / ``ac_circuit_call`` 讓動作清單透過**具名**斷路器
執行(狀態跨呼叫共享),回傳 ``{state, record}``。
