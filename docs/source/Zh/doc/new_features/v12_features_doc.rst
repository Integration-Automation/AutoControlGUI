========================================
新功能 (2026-06-19) — 編寫與除錯
========================================

兩項編寫期工具,皆為純標準庫,並走完整五層(facade、``AC_*`` 執行器
指令、MCP 工具、Script Builder):原生 UI 的**元素庫**(object
repository)與動作清單的**步進除錯器 / 追蹤器**。

.. contents::
   :local:
   :depth: 2


元素庫
======

把原生 UI 定位器以友善名稱存一次、到處重用——這就是 RPA 經典的
*object repository*。流程改以 ``"login.submit"`` 引用,而不必在每個
呼叫點重複 ``name="Submit", role="button"``;UI 變動只需改一處::

    from je_auto_control import ElementRepository

    repo = ElementRepository("app.objects.json")
    repo.save("login.submit", name="Submit", role="button")
    repo.save("login.user", role="edit", app_name="MyApp")

    repo.click("login.submit")           # 解析並點擊實際元素
    info = repo.find_info("login.user")   # {found, name, role, center}

定位器是一組小的 accessibility 過濾條件(``name`` / ``role`` /
``app_name``);解析時透過 accessibility 後端找到實際元素。儲存為 JSON
檔、跨平台可用;解析需要平台的 accessibility 後端。

執行器 / MCP 指令:``AC_element_save`` / ``AC_element_find`` /
``AC_element_click`` / ``AC_element_remove`` / ``AC_element_list``
(以及對應的 ``ac_element_*`` MCP 工具)。


步進除錯器與追蹤器
==================

把動作清單一次跑一個指令,具備中斷點、單步與即時變數檢視。步進時重用
同一個執行器實例,因此腳本變數(``${name}`` 插值、``AC_set_var`` …)
會像正常執行一樣在各步之間保留::

    from je_auto_control import FlowDebugger

    dbg = FlowDebugger(actions, breakpoints=[3])
    dbg.continue_()          # 跑到中斷點
    dbg.variables()          # 檢視即時變數
    dbg.step()               # 一次一個指令
    dbg.run_to_end()

無狀態的一次性形式 :func:`trace_actions` 會跑完清單(或用 ``dry_run``
只做規劃),回傳每步的 ``{index, command, result}`` 追蹤——對應
``AC_debug_trace`` / ``ac_debug_trace``::

    from je_auto_control import trace_actions

    plan = trace_actions(actions, dry_run=True)   # 只規劃不執行
    trace = trace_actions(actions)                # 執行並追蹤
