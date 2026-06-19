==========================================
新功能 (2026-06-19) — 檢查點與續跑
==========================================

長動作清單的耐久執行(durable execution),並新增 ``py.typed`` 標記讓
型別檢查器採用套件的內嵌型別註記。純標準庫;走完整五層(facade、
``AC_*`` 執行器指令、MCP 工具、Script Builder)。

.. contents::
   :local:
   :depth: 2


流程檢查點與續跑
================

跑了數小時、卻在第 400 步當掉的無人值守流程,不該從頭重來。
:func:`run_resumable` 在每執行完一步後,把 ``{run_id, step_index,
variables}`` 存入可抽換的儲存後端;之後以相同 ``run_id`` 再執行時,會
快轉略過已完成的步驟並還原腳本變數::

    from je_auto_control import run_resumable, CheckpointStore

    store = CheckpointStore("runs.db")
    result = run_resumable(actions, run_id="nightly-invoices", store=store)
    result["resumed_from"]   # 全新執行為 0;當機後續跑則為 N

正常完成後檢查點會被清除。儲存後端可注入,因此續跑邏輯可在不真的當機的
情況下做決定性單元測試:``CheckpointStore.save`` / ``load`` / ``clear``。

執行器 / MCP 指令:

* ``AC_run_resumable`` — 以 ``run_id`` 為鍵,帶檢查點/續跑執行 ``actions``
  (存到 ``db``)。
* ``AC_checkpoint_status`` — 某次執行已存的檢查點(或 null)。
* ``AC_checkpoint_clear`` — 刪除某次執行的檢查點。

(以及對應的 ``ac_run_resumable`` / ``ac_checkpoint_status`` /
``ac_checkpoint_clear`` MCP 工具)。


``py.typed`` 標記
=================

套件現在附帶 PEP 561 的 ``py.typed`` 標記,讓 Mypy / Pyright / Pylance
在下游程式碼中採用 AutoControl 的內嵌型別註記——讓型別化的公開 API 真正
發揮價值。呼叫端無需改動;開箱即享更好的編輯器自動完成與型別檢查。
