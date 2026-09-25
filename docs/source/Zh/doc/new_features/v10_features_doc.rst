====================================
新功能 (2026-06-19) — 交易式工作佇列
====================================

把 AutoControl 從「跑一支腳本」升級成「跑一個機器人」。以 SQLite 為底的
工作佇列實作了標準生產級 RPA 的 dispatcher/performer 模式:*dispatcher*
把工作項目入列,*performer* 一次處理一項,具備每項狀態、去重與重試——
因此處理上千項的執行能在**當機後續跑**,並可由多個 worker 平行處理。

純標準庫、完全 headless,走完整五層(facade、``AC_*`` 執行器指令、
MCP 工具、Script Builder)。由競品研究指出為相對 UiPath Orchestrator
佇列 / REFramework 所缺的一塊。

.. contents::
   :local:
   :depth: 2


Dispatcher / performer
======================

::

    from je_auto_control import WorkQueue

    q = WorkQueue("run.db", name="invoices")

    # Dispatcher:把工作入列(依 live reference 去重)。
    for inv in invoices:
        q.add({"path": inv}, reference=inv)

    # Performer:把佇列處理完,可跨重啟續跑。
    item = q.get_next()
    while item is not None:
        try:
            process(item.data)
            q.complete(item.id, output={"ok": True})
        except BusinessError as exc:           # 資料有問題——不重試
            q.fail(item.id, str(exc), kind="business")
        except Exception as exc:               # 暫時性——重試
            q.fail(item.id, str(exc), kind="application")
        item = q.get_next()

``get_next`` 會原子性地認領最舊的 ``new`` 項目(標為 ``in_progress``),
因此多個 performer 不會重複處理。``complete`` 與 ``fail`` 只處理 ``in_progress`` 的項目;
不存在的 id 或其他狀態的項目會拋出例外,已完成的工作不會被重新排入佇列。


失敗語意
========

兩種失敗類型,對應 REFramework:

* **application**(暫時性——逾時、stale element):重試至 ``max_retries``
  (預設 3)次,然後標為 ``failed``。
* **business**(資料本身無效):永不重試——立即標為 ``failed``。請丟出
  :class:`BusinessError` 或傳 ``kind="business"``。

``stats()`` 回傳各狀態計數(``new`` / ``in_progress`` / ``success`` /
``failed``),供儀表板與執行報告使用。資料庫無法開啟或使用(不是 SQLite 檔、鎖定逾時)時丟出
``WorkQueueError``(屬於 ``AutoControlException``)。


執行器指令
==========

* ``AC_queue_add`` — 入列 ``data``(依 ``reference`` 去重)。
* ``AC_queue_next`` — 認領下一項(排空時回 null)。項目帶有認領編號 ``claim``;給了
  ``stale_after_s`` 時，被丟下的項目會被重新認領並算一次重試，被丟下 ``max_retries`` 次的標為 ``failed``。
* ``AC_queue_complete`` — 標記項目成功。傳回該項目的 ``claim``,項目在這段期間被別人重新認領時就會被拒絕。
* ``AC_queue_fail`` — 以 ``kind``(``application`` / ``business``)失敗;``claim`` 用法相同。
* ``AC_queue_stats`` — 各狀態計數。

同一個 ``db`` 檔 + ``name`` 識別一個佇列,因此 dispatcher 腳本與 performer
腳本(或多個平行 performer)可共用它。
